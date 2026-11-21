"""Entry point Master (rancangan bagian 4.2, 4.5, 4.6, 4.7).

Tanggung jawab Master: menerima koneksi Worker (thread per koneksi),
memecah target menjadi task (chunk), membagikan via pull/static, mengumpulkan
hasil, memantau heartbeat + requeue, mencatat metrik, dan menampilkan
dashboard CLI.

Windows: jalankan dengan `python master/master.py --targets targets.txt`.
"""

import argparse
import json
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.protocol import (HEARTBEAT, NO_TASK, REGISTER, REGISTER_ACK, RESULT,
                             SHUTDOWN, TASK, TASK_REQUEST, MessageConnection, make_msg)
from common.utils import (generate_tasks, load_config, read_allowlist, read_targets,
                          setup_logger, total_ports)
from master.fault_monitor import FaultMonitor
from master.metrics import MetricsLogger
from master.results import ResultsStore, compare_ground_truth
from master.scheduler import Scheduler

log = setup_logger("master")


class Master:
    def __init__(self, cfg, targets_path, allowlist_path, overrides):
        # Validasi allowlist (bagian 2: tolak target yang tidak diizinkan)
        allowed = read_allowlist(allowlist_path)
        targets = read_targets(targets_path)
        rejected = [t[0] for t in targets if t[0].lower() not in allowed]
        if rejected:
            raise SystemExit(f"Target tidak terdaftar di allowlist.txt — DITOLAK: {rejected}")

        self.mode = overrides.get("mode", cfg["mode"])
        self.chunk_size = overrides.get("chunk_size", cfg["chunk_size"])
        self.scan_timeout = overrides.get("scan_timeout", cfg["scan_timeout"])
        tasks = generate_tasks(targets, self.chunk_size, self.scan_timeout)
        self.scheduler = Scheduler(tasks, mode=self.mode,
                                   expected_workers=overrides.get("expected_workers"),
                                   retry_limit=cfg["retry_limit"])
        self.results = ResultsStore()
        self.metrics = MetricsLogger()
        self.total_ports = total_ports(tasks)

        self.bind_host = overrides.get("host", cfg["master_host"])
        self.port = overrides.get("port", cfg["master_port"])
        self.hb_interval = cfg["heartbeat_interval"]
        self.hb_timeout = cfg["heartbeat_timeout"]
        self.results_dir = overrides.get("results_dir", cfg["results_dir"])
        self.gt_path = overrides.get("gt")

        self.workers = {}  # worker_id -> {conn, addr, cpu_cores, hostname, processes, last_seen, alive, cpu, mem}
        self.lock = threading.RLock()
        self.done_event = threading.Event()
        self.listen_sock = None

    # ---------- siklus hidup ----------
    def start(self):
        if self.scheduler.is_complete():
            log.warning("Tidak ada task — selesai segera.")
            self.done_event.set()
        self.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listen_sock.bind((self.bind_host, self.port))
        self.listen_sock.listen(16)
        self.listen_sock.settimeout(1.0)
        log.info("Master %s:%d | mode=%s | %d task (chunk=%d) | total %d port",
                 self.bind_host, self.port, self.mode, len(self.scheduler.table),
                 self.chunk_size, self.total_ports)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        FaultMonitor(self).start()
        threading.Thread(target=self._dashboard, daemon=True).start()

        try:
            self.done_event.wait()
        except KeyboardInterrupt:
            log.warning("Dihentikan pengguna — mematikan Worker lalu menyimpan hasil parsial.")
            self.done_event.set()
        time.sleep(0.5)  # beri kesempatan SHUTDOWN terkirim
        self._shutdown_workers()
        return self._finish()

    # ---------- jaringan ----------
    def _accept_loop(self):
        while not self.done_event.is_set():
            try:
                raw_conn, addr = self.listen_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handler, args=(raw_conn, addr), daemon=True).start()

    def _handler(self, raw_conn, addr):
        conn = MessageConnection(raw_conn)
        wid = None
        try:
            first = conn.recv()
            if first["type"] != REGISTER:
                raise ValueError("Pesan pertama bukan REGISTER")
            wid = self._register(conn, addr, first)
            conn.send(make_msg(REGISTER_ACK, heartbeat_interval=self.hb_interval,
                               scan_timeout=self.scan_timeout, mode=self.mode))
            while True:
                msg = conn.recv()
                mtype = msg["type"]
                if mtype == TASK_REQUEST:
                    task = self.scheduler.assign_next(wid)
                    if task:
                        self.metrics.event("task_assign", worker_id=wid, task_id=task["task_id"])
                        conn.send(make_msg(TASK, task_id=task["task_id"], host=task["host"],
                                           port_start=task["port_start"], port_end=task["port_end"],
                                           timeout=task["timeout"], attempt=task["attempt"]))
                    else:
                        conn.send(make_msg(NO_TASK))
                    self._touch(wid)
                elif mtype == HEARTBEAT:
                    self._touch(wid, cpu=msg.get("cpu"), mem=msg.get("mem"))
                    self.metrics.heartbeat(wid, msg.get("cpu"), msg.get("mem"))
                elif mtype == RESULT:
                    self._on_result(wid, msg)
                elif mtype == REGISTER:  # re-REGISTER dari worker yang reconnect
                    wid = self._register(conn, addr, msg)
                    conn.send(make_msg(REGISTER_ACK, heartbeat_interval=self.hb_interval,
                                       scan_timeout=self.scan_timeout, mode=self.mode))
        except (ConnectionError, ValueError, OSError) as e:
            if wid:
                log.info("Koneksi Worker %s terputus: %s", wid, e)
                self.mark_worker_dead(wid, reason="connection_lost", dead_conn=conn)
        finally:
            conn.close()

    def _register(self, conn, addr, msg):
        wid = msg["worker_id"]
        with self.lock:
            prev = self.workers.get(wid)
            if prev and prev["alive"]:
                log.info("Worker %s re-REGISTER dengan koneksi baru", wid)
            self.workers[wid] = {"conn": conn, "addr": addr,
                                 "cpu_cores": msg["cpu_cores"], "hostname": msg["hostname"],
                                 "processes": msg["processes"], "last_seen": time.time(),
                                 "alive": True, "cpu": None, "mem": None}
            self.metrics.event("register", worker_id=wid)
        if self.mode == "static":
            self.scheduler.register_static_partition(wid)
        log.info("Worker %s terhubung dari %s (cores=%s, proses=%s)",
                 wid, addr, msg["cpu_cores"], msg["processes"])
        return wid

    def _touch(self, wid, cpu=None, mem=None):
        with self.lock:
            w = self.workers.get(wid)
            if w:
                w["last_seen"] = time.time()
                if cpu is not None:
                    w["cpu"] = cpu
                if mem is not None:
                    w["mem"] = mem

    # ---------- hasil ----------
    def _on_result(self, wid, msg):
        rec = self.scheduler.table.get(msg["task_id"])
        if rec is None:
            log.warning("RESULT task tak dikenal %s dari %s", msg["task_id"], wid)
            return
        accepted = self.results.submit(rec, wid, msg["results"], msg["duration"])
        if accepted:
            self.scheduler.mark_done(msg["task_id"])
            self.metrics.event("task_done", worker_id=wid, task_id=msg["task_id"])
            self.metrics.mark_last_result()
        else:
            self.metrics.event("task_duplicate", worker_id=wid, task_id=msg["task_id"])
            log.info("Hasil duplikat task %s dari %s dibuang (idempotensi)", msg["task_id"], wid)
        if self.scheduler.is_complete():
            log.info("Semua task DONE/FAILED -> sistem selesai.")
            self.done_event.set()

    # ---------- fault tolerance ----------
    def mark_worker_dead(self, wid, reason, dead_conn=None):
        """Satu pintu: tandai mati, requeue in-flight, catat metrik.
        Dipanggil FaultMonitor (heartbeat timeout) atau handler (koneksi putus);
        hanya pemicu pertama yang efektif."""
        with self.lock:
            w = self.workers.get(wid)
            if not w or not w["alive"]:
                return
            if dead_conn is not None and w["conn"] is not dead_conn:
                return  # koneksi lama mati, worker sudah re-REGISTER lewat koneksi baru
            w["alive"] = False
            last_seen = w["last_seen"]
            w["conn"].close()
        requeued, failed = self.scheduler.requeue_for(wid)
        self.metrics.event("worker_down", worker_id=wid,
                           detail={"reason": reason, "requeued": requeued,
                                   "failed": failed, "last_seen": last_seen})
        for tid in requeued:
            self.metrics.event("requeue", worker_id=wid, task_id=tid)
        if requeued or failed:
            log.warning("Worker %s mati (%s): requeue=%d, failed=%d",
                        wid, reason, len(requeued), len(failed))
        if self.scheduler.is_complete():
            self.done_event.set()

    def _shutdown_workers(self):
        for wid, w in list(self.workers.items()):
            if w["alive"]:
                try:
                    w["conn"].send(make_msg(SHUTDOWN, reason="all_tasks_done"))
                except (OSError, ConnectionError):
                    pass

    # ---------- dashboard ----------
    def _dashboard(self):
        while not self.done_event.is_set():
            time.sleep(2.0)
            st = self.scheduler.stats()
            rc = self.results.counts()
            with self.lock:
                alive = sum(1 for w in self.workers.values() if w["alive"])
                total = len(self.workers)
            print(f"[dashboard] workers={total} (alive={alive}) | "
                  f"task: done={st['by_status']['DONE']} inflight={st['by_status']['IN_FLIGHT']} "
                  f"queued={st['queue_len']} failed={st['by_status']['FAILED']} | "
                  f"port hasil={rc['ports']}/{self.total_ports} dup={rc['duplicates']}",
                  flush=True)

    # ---------- penutupan ----------
    def _finish(self):
        summary = self.metrics.build_summary(self.total_ports, self.scheduler.stats(),
                                             self.results.counts(), self.mode,
                                             len(self.scheduler.table))
        if self.gt_path:
            gt = json.loads(Path(self.gt_path).read_text(encoding="utf-8"))
            summary["ground_truth"] = compare_ground_truth(self.results.port_status, gt)
        out = Path(self.results_dir)
        results_file = self.results.export(out)
        summary_file = self.metrics.save(out, summary)
        log.info("Exec time=%.3fs | throughput=%.1f port/s | dup=%d | imbalance=%s",
                 summary["execution_time_s"] or -1,
                 summary["throughput_ports_per_s"] or -1,
                 self.results.duplicates, summary["load_imbalance_ratio"])
        for f in summary["failures"]:
            log.info("  worker_down %s (%s): detection=%.2fs recovery=%s requeued=%d",
                     f["worker_id"], f["reason"], f["detection_s"],
                     f["recovery_s"], f["requeued_tasks"])
        log.info("Hasil: %s | ringkasan: %s", results_file, summary_file)
        return summary


def main():
    ap = argparse.ArgumentParser(description="Master DPS (jalankan di node Master)")
    ap.add_argument("--config", default=None, help="path config.json")
    ap.add_argument("--targets", default="targets.txt")
    ap.add_argument("--allowlist", default="allowlist.txt")
    ap.add_argument("--host", default=None, help="alamat bind (default dari config)")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--mode", choices=["dynamic", "static"], default=None)
    ap.add_argument("--expected-workers", type=int, default=None,
                    help="jumlah worker yang diharapkan (partisi static; wajib akurat)")
    ap.add_argument("--chunk-size", type=int, default=None)
    ap.add_argument("--scan-timeout", type=float, default=None)
    ap.add_argument("--gt", default=None, help="ground_truth.json untuk verifikasi hasil")
    ap.add_argument("--results-dir", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    overrides = {k: v for k, v in {
        "host": args.host, "port": args.port, "mode": args.mode,
        "expected_workers": args.expected_workers, "chunk_size": args.chunk_size,
        "scan_timeout": args.scan_timeout, "gt": args.gt, "results_dir": args.results_dir,
    }.items() if v is not None}

    try:
        master = Master(cfg, args.targets, args.allowlist, overrides)
    except SystemExit as e:
        print(f"[DITOLAK] {e}")
        sys.exit(2)

    try:
        master.start()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
