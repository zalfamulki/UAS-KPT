"""T2 - local parallel: multiprocessing pada satu komputer (rancangan 6.3).

Memakai ScanPool yang sama dengan Worker, jadi perbandingannya adil.
Speedup dihitung terhadap baseline T1 (results/t1_sequential.csv).
"""

import argparse
import csv
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.utils import load_config, read_targets, setup_logger
from worker.pool import ScanPool

log = setup_logger("t2")


def processes_list(spec, cpu_count):
    """'1,2,4,8' -> [1,2,4,8]; tanpa arg: 1,2,4,... hingga core logis."""
    if spec:
        return sorted({int(x) for x in spec.split(",") if x.strip()})
    vals, p = [], 1
    while p <= cpu_count:
        vals.append(p)
        p *= 2
    if not vals or vals[-1] < cpu_count:
        vals.append(cpu_count)
    return vals


def run_once(targets, timeout, processes):
    pool = ScanPool(processes)
    tasks = [{"host": h, "port_start": s, "port_end": e, "timeout": timeout}
             for h, s, e in targets]
    t0 = time.monotonic()
    ports = 0
    for t in tasks:
        ports += len(pool.scan_task(t))
    exec_time = time.monotonic() - t0
    pool.close()
    return exec_time, ports


def main():
    ap = argparse.ArgumentParser(description="T2: local parallel (multiprocessing 1 PC)")
    ap.add_argument("--targets", default="targets.txt")
    ap.add_argument("--config", default=None)
    ap.add_argument("--processes", default=None, help="daftar P, mis. 1,2,4,8 (default: 1,2,4..core)")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--t1", default="results/t1_sequential.csv", help="CSV T1 untuk speedup")
    ap.add_argument("--out", default="results/t2_local_parallel.csv")
    args = ap.parse_args()

    cfg = load_config(args.config)
    targets = read_targets(args.targets)
    cpu = os.cpu_count() or 4

    t1_mean = None
    p1 = Path(args.t1)
    if p1.exists():
        with open(p1, encoding="utf-8") as f:
            t1_rows = list(csv.DictReader(f))
        t1_mean = statistics.mean(float(r["exec_time_s"]) for r in t1_rows)
        log.info("Baseline T1: mean %.3f s (%d run)", t1_mean, len(t1_rows))
    else:
        log.warning("T1 tidak ditemukan di %s — speedup kosong. Jalankan run_sequential.py dulu.", p1)

    rows = []
    for p in processes_list(args.processes, cpu):
        times = []
        ports = 0
        for i in range(args.repeat):
            exec_time, ports = run_once(targets, cfg["scan_timeout"], p)
            times.append(exec_time)
            log.info("P=%d repeat %d: exec=%.3fs (%d port)", p, i + 1, exec_time, ports)
        mean_t = statistics.mean(times)
        row = {"processes": p,
               "exec_time_s_mean": round(mean_t, 3),
               "exec_time_s_std": round(statistics.stdev(times), 3) if len(times) > 1 else 0.0,
               "ports": ports}
        if t1_mean:
            row["speedup"] = round(t1_mean / mean_t, 3)
            row["efficiency"] = round(row["speedup"] / p, 3)
        rows.append(row)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    log.info("T2 selesai -> %s", out)


if __name__ == "__main__":
    main()
