"""Orkestrator T3-T6 (rancangan bagian 6.3): menjalankan Master + Worker
sebagai subprocess dan mengumpulkan summary tiap run.

- T3 Distributed : skala worker --workers 1,2,4,6,9, tiap konfigurasi --repeat.
- T4 Dynamic LB  : static vs dynamic dengan worker "lemah" (--weak-workers:
                   jumlah proses dibatasi 1 — kondisi nyata, bukan sleep buatan, 4.6).
- T5 Fault       : kill satu worker di tengah run (--kill-delay), detection/
                   recovery diambil dari summary Master (definisi 7.2).
- T6 Scalability : agregasi hasil T3 -> speedup/efficiency vs baseline T1.

Target simulator harus sudah berjalan sebelum skrip ini (lihat README).
"""

import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.utils import load_config, setup_logger

log = setup_logger("bench")
ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

T1_CSV = RESULTS / "t1_sequential.csv"
T3_CSV = RESULTS / "t3_distributed.csv"
T6_CSV = RESULTS / "t6_scalability.csv"
T4_CSV = RESULTS / "t4_load_balance.csv"
T5_CSV = RESULTS / "t5_fault_tolerance.csv"


# ---------- util ----------
def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        log.warning("Tidak ada baris untuk %s", path)
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    log.info("Tersimpan: %s (%d baris)", path, len(rows))


def wait_port(host, port, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with __import__("socket").create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def load_t1_mean():
    if not T1_CSV.exists():
        return None
    with open(T1_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return statistics.mean(float(r["exec_time_s"]) for r in rows) if rows else None


def ensure_t1(args):
    if T1_CSV.exists():
        return
    log.info("T1 belum ada — menjalankan run_sequential.py dulu ...")
    cmd = [sys.executable, str(ROOT / "bench" / "run_sequential.py"),
           "--targets", args.targets, "--repeat", str(max(1, args.repeat))]
    if args.config:
        cmd += ["--config", args.config]
    if args.gt:
        cmd += ["--gt", args.gt]
    subprocess.run(cmd, check=True, cwd=str(ROOT))


def read_t3_rows():
    if not T3_CSV.exists():
        return []
    with open(T3_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------- satu run terdistribusi ----------
def run_once_distributed(cfg, args, n_workers, mode, run_dir,
                         weak_workers=0, kill_idx=None, kill_delay=None):
    """Spawn master + N worker, tunggu selesai. Return (summary, t_kill)."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    bind = args.bind
    connect_host = args.connect_host or args.bind
    port = args.port or cfg["master_port"]
    cpu = os.cpu_count() or 4

    master_log = open(run_dir / "master.log", "w", encoding="utf-8")
    master_cmd = [sys.executable, str(ROOT / "master" / "master.py"),
                  "--targets", args.targets, "--allowlist", args.allowlist,
                  "--host", bind, "--port", str(port), "--mode", mode,
                  "--results-dir", str(run_dir)]
    if args.config:
        master_cmd += ["--config", args.config]
    if args.gt:
        master_cmd += ["--gt", args.gt]
    if mode == "static":
        master_cmd += ["--expected-workers", str(n_workers)]

    procs = []
    t_kill_holder = {"ts": None}
    master_proc = None
    try:
        master_proc = subprocess.Popen(master_cmd, stdout=master_log,
                                       stderr=subprocess.STDOUT, cwd=str(ROOT))
        procs.append(master_proc)
        if not wait_port(connect_host, port):
            raise RuntimeError(f"Master tidak merespons di {connect_host}:{port}")

        for i in range(n_workers):
            procs_i = 1 if i < weak_workers else cpu  # worker lemah = proses dibatasi (4.6)
            wlog = open(run_dir / f"worker_{i}.log", "w", encoding="utf-8")
            wcmd = [sys.executable, str(ROOT / "worker" / "worker.py"),
                    "--master", f"{connect_host}:{port}", "--id", f"w{i}",
                    "--processes", str(procs_i), "--max-retries", "3"]
            if args.config:
                wcmd += ["--config", args.config]
            procs.append(subprocess.Popen(wcmd, stdout=wlog,
                                          stderr=subprocess.STDOUT, cwd=str(ROOT)))
            log.info("  worker w%d start (proses=%d)", i, procs_i)

        if kill_idx is not None:
            def kill_worker():
                proc = procs[1 + kill_idx]  # procs[0] = master
                if proc.poll() is None:
                    proc.kill()
                    t_kill_holder["ts"] = time.time()
                    log.info("  >>> worker w%d di-kill pada t=%.2f (T5)", kill_idx, t_kill_holder["ts"])
            threading.Timer(kill_delay, kill_worker).start()

        master_proc.wait(timeout=args.run_timeout)
        time.sleep(0.5)
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        master_log.close()

    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise RuntimeError(f"summary.json tidak ditemukan di {run_dir} — cek master.log")
    return json.loads(summary_path.read_text(encoding="utf-8")), t_kill_holder["ts"]


def summary_row(test, scale, repeat, summary, t_kill=None):
    fails = summary.get("failures") or [{}]
    gt = summary.get("ground_truth") or {}
    row = {
        "test": test,
        "workers": scale,
        "repeat": repeat,
        "mode": summary.get("mode"),
        "exec_time_s": summary.get("execution_time_s"),
        "throughput": summary.get("throughput_ports_per_s"),
        "ports": summary.get("total_ports"),
        "imbalance": summary.get("load_imbalance_ratio"),
        "requeued_total": summary.get("tasks", {}).get("requeued_total"),
        "failed_total": summary.get("tasks", {}).get("failed_total"),
        "duplicates": summary.get("results", {}).get("duplicates"),
        "matched_gt": gt.get("matched"),
        "mismatched_gt": gt.get("mismatched"),
        "detection_s": fails[0].get("detection_s"),
        "recovery_s": fails[0].get("recovery_s"),
        "t_kill": round(t_kill, 3) if t_kill else None,
    }
    return row


# ---------- tes ----------
def test_t3(args, cfg):
    scales = [int(x) for x in args.workers.split(",")]
    rows = []
    for n in scales:
        for rep in range(1, args.repeat + 1):
            log.info("=== T3: %d worker, repeat %d ===", n, rep)
            run_dir = RESULTS / f"t3_w{n}_r{rep}"
            summary, _ = run_once_distributed(cfg, args, n, "dynamic", run_dir)
            row = summary_row("t3", n, rep, summary)
            rows.append(row)
            log.info("T3 w=%d r=%d: exec=%ss throughput=%s",
                     n, rep, row["exec_time_s"], row["throughput"])
    write_csv(T3_CSV, rows)
    return rows


def test_t4(args, cfg):
    rows = []
    for mode in ("static", "dynamic"):
        for rep in range(1, args.repeat + 1):
            log.info("=== T4: mode=%s, scale=%d, repeat %d ===", mode, args.scale, rep)
            run_dir = RESULTS / f"t4_{mode}_r{rep}"
            summary, _ = run_once_distributed(cfg, args, args.scale, mode, run_dir,
                                              weak_workers=args.weak_workers)
            row = summary_row("t4", args.scale, rep, summary)
            row["weak_workers"] = args.weak_workers
            rows.append(row)
            log.info("T4 %s r=%d: imbalance=%s requeued=%s",
                     mode, rep, row["imbalance"], row["requeued_total"])
    write_csv(T4_CSV, rows)


def test_t5(args, cfg):
    rows = []
    for rep in range(1, args.repeat + 1):
        log.info("=== T5: kill w%d setelah %.1f s, repeat %d ===", args.kill_idx, args.kill_delay, rep)
        run_dir = RESULTS / f"t5_r{rep}"
        summary, t_kill = run_once_distributed(cfg, args, args.scale, "dynamic", run_dir,
                                               kill_idx=args.kill_idx, kill_delay=args.kill_delay)
        row = summary_row("t5", args.scale, rep, summary, t_kill=t_kill)
        rows.append(row)
        log.info("T5 r=%d: exec=%ss detection=%ss recovery=%ss requeued=%s",
                 rep, row["exec_time_s"], row["detection_s"], row["recovery_s"], row["requeued_total"])
    # Overhead total (7.2): T_dengan_kegagalan - T_tanpa_kegagalan (dari T3 dynamic, scale sama)
    t3 = [r for r in read_t3_rows() if int(r["workers"]) == args.scale and r["mode"] == "dynamic"]
    if t3:
        baseline = statistics.mean(float(r["exec_time_s"]) for r in t3)
        for r in rows:
            r["overhead_vs_t3_s"] = round(float(r["exec_time_s"]) - baseline, 3)
        log.info("Overhead vs T3 (scale %d): %.3f s", args.scale, rows[0]["overhead_vs_t3_s"])
    write_csv(T5_CSV, rows)


def test_t6(args):
    """Agregasi T3 -> kurva scalability (speedup/efficiency vs jumlah worker)."""
    rows = read_t3_rows()
    if not rows:
        log.warning("T6 butuh data T3 di %s — jalankan --test t3 dulu.", T3_CSV)
        return
    t1_mean = load_t1_mean()
    by_scale = {}
    for r in rows:
        by_scale.setdefault(int(r["workers"]), []).append(float(r["exec_time_s"]))
    agg = []
    for n in sorted(by_scale):
        mean_t = statistics.mean(by_scale[n])
        row = {"workers": n, "exec_time_s_mean": round(mean_t, 3),
               "repeats": len(by_scale[n])}
        if t1_mean:
            row["speedup"] = round(t1_mean / mean_t, 3)
            row["efficiency"] = round(row["speedup"] / n, 3)
        agg.append(row)
    write_csv(T6_CSV, agg)
    if t1_mean:
        for r in agg:
            log.info("T6: workers=%d speedup=%s efficiency=%s", r["workers"], r.get("speedup"), r.get("efficiency"))


def main():
    ap = argparse.ArgumentParser(description="Orkestrator benchmark T3-T6")
    ap.add_argument("--test", default="all", choices=["all", "t3", "t4", "t5", "t6"])
    ap.add_argument("--targets", default="targets.txt")
    ap.add_argument("--allowlist", default="allowlist.txt")
    ap.add_argument("--config", default=None)
    ap.add_argument("--gt", default=None, help="ground truth untuk verifikasi tiap run")
    ap.add_argument("--workers", default="1,2,4,6,9", help="skala worker untuk T3 (T6 memakai hasilnya)")
    ap.add_argument("--scale", type=int, default=4, help="jumlah worker untuk T4/T5")
    ap.add_argument("--repeat", type=int, default=3, help="pengulangan tiap konfigurasi (rancangan: min 3)")
    ap.add_argument("--weak-workers", type=int, default=2, help="worker dengan 1 proses (T4)")
    ap.add_argument("--kill-idx", type=int, default=1, help="indeks worker yang di-kill (T5)")
    ap.add_argument("--kill-delay", type=float, default=3.0, help="detik setelah worker start (T5)")
    ap.add_argument("--bind", default="127.0.0.1", help="bind Master (LAN: 0.0.0.0)")
    ap.add_argument("--connect-host", default=None, help="alamat yang dipakai worker connect (default = bind)")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--run-timeout", type=int, default=1800)
    args = ap.parse_args()

    cfg = load_config(args.config)

    if args.test in ("all", "t3", "t6"):
        ensure_t1(args)
    if args.test in ("all", "t3"):
        test_t3(args, cfg)
    if args.test in ("all", "t4"):
        test_t4(args, cfg)
    if args.test in ("all", "t5"):
        test_t5(args, cfg)
    if args.test in ("all", "t6"):
        test_t6(args)
    log.info("Benchmark selesai. Lihat results/ lalu jalankan plot_results.py untuk grafik.")


if __name__ == "__main__":
    main()
