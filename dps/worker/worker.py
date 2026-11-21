"""Entry point Worker (rancangan bagian 4.2, 4.5, 4.7).

Alur: connect -> REGISTER -> loop {TASK_REQUEST -> TASK -> proses via
multiprocessing.Pool -> RESULT} -> SHUTDOWN. Thread heartbeat terpisah
mengirim HEARTBEAT (cpu%, mem%, task berjalan) tiap interval H.

Auto-reconnect: bila koneksi ke Master putus (Master restart / jaringan
kembali), Worker mencoba REGISTER ulang — selaras dengan mekanisme fault
tolerance (Worker yang kembali boleh ikut bekerja lagi, 4.7).

Windows: menjalankan file ini langsung (`python worker/worker.py`).
"""

import argparse
import os
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.protocol import (HEARTBEAT, NO_TASK, REGISTER, REGISTER_ACK, RESULT,
                             SHUTDOWN, TASK, TASK_REQUEST, MessageConnection, make_msg)
from common.utils import load_config, setup_logger
from worker.pool import ScanPool
from worker.sys_monitor import SysMonitor

log = setup_logger("worker")


class Worker:
    def __init__(self, master_addr, worker_id, processes, config, max_retries=10):
        self.master_addr = master_addr        # (host, port)
        self.worker_id = worker_id
        self.processes = processes
        self.config = config
        self.max_retries = max_retries
        self.conn = None                      # MessageConnection sesi aktif
        self.pool = ScanPool(processes)
        self.monitor = SysMonitor()
        self.current_task = None              # task_id yang sedang diproses
        self.stop_event = threading.Event()
        self.heartbeat_interval = config["heartbeat_interval"]

    # ---------- koneksi ----------
    def _connect(self):
        host, port = self.master_addr
        sock = socket.create_connection((host, port), timeout=10)
        sock.settimeout(None)  # blocking setelah connect berhasil
        self.conn = MessageConnection(sock)
        try:
            local_ip = sock.getsockname()[0]
        except OSError:
            local_ip = "?"
        log.info("Node ini: %s (%s) -> master %s:%d", socket.gethostname(), local_ip, host, port)
        self.conn.send(make_msg(REGISTER,
                                worker_id=self.worker_id,
                                cpu_cores=os.cpu_count() or 1,
                                hostname=socket.gethostname(),
                                processes=self.processes))
        ack = self.conn.recv()
        if ack["type"] != REGISTER_ACK:
            raise ValueError(f"Balasan pertama bukan REGISTER_ACK: {ack['type']}")
        self.heartbeat_interval = ack.get("heartbeat_interval", self.heartbeat_interval)
        log.info("Terhubung ke %s:%d (mode=%s, proses=%d, heartbeat=%.1fs)",
                 host, port, ack.get("mode"), self.processes, self.heartbeat_interval)

    # ---------- heartbeat ----------
    def _heartbeat_loop(self, conn):
        """Kirim HEARTBEAT berkala pada koneksi sesi ini sampai gagal/berhenti.
        conn dipasang sebagai argumen agar thread sesi lama tidak mengirim di
        koneksi baru setelah reconnect."""
        while not self.stop_event.is_set():
            stats = self.monitor.sample()
            try:
                conn.send(make_msg(HEARTBEAT,
                                   worker_id=self.worker_id,
                                   cpu=stats["cpu"],
                                   mem=stats["mem"],
                                   current_task=self.current_task))
            except (ConnectionError, OSError, ValueError):
                return  # sesi berakhir; main loop yang menangani reconnect
            self.stop_event.wait(self.heartbeat_interval)

    # ---------- pekerjaan ----------
    def _handle_task(self, task):
        self.current_task = task["task_id"]
        t0 = time.monotonic()
        results = self.pool.scan_task(task)
        duration = time.monotonic() - t0
        self.conn.send(make_msg(RESULT,
                                worker_id=self.worker_id,
                                task_id=task["task_id"],
                                attempt=task.get("attempt", 0),
                                results=results,
                                duration=round(duration, 4)))
        self.current_task = None
        log.info("Task %s selesai (%d port, %.2f s)", task["task_id"], len(results), duration)

    def _session(self):
        """Satu koneksi penuh sampai SHUTDOWN / koneksi putus."""
        self._connect()
        hb = threading.Thread(target=self._heartbeat_loop, args=(self.conn,), daemon=True)
        hb.start()
        try:
            while not self.stop_event.is_set():
                self.conn.send(make_msg(TASK_REQUEST, worker_id=self.worker_id))
                msg = self.conn.recv()
                mtype = msg["type"]
                if mtype == TASK:
                    self._handle_task(msg)
                elif mtype == NO_TASK:
                    time.sleep(0.5)  # antrean kosong; poll lagi nanti
                elif mtype == SHUTDOWN:
                    log.info("Master meminta SHUTDOWN: %s", msg.get("reason"))
                    return
        finally:
            self.conn.close()

    def run(self):
        retries = 0
        while retries <= self.max_retries and not self.stop_event.is_set():
            try:
                self._session()
                break  # SHUTDOWN normal -> keluar
            except (ConnectionError, OSError, ValueError) as e:
                retries += 1
                if retries > self.max_retries:
                    log.error("Gagal reconnect %d kali — Worker berhenti.", self.max_retries)
                    break
                wait = min(1.0 * retries, 10.0)
                log.warning("Koneksi putus (%s) — reconnect %d/%d dalam %.1f s",
                            e, retries, self.max_retries, wait)
                self.stop_event.wait(wait)
        self.pool.close()
        log.info("Worker berhenti.")


def main():
    ap = argparse.ArgumentParser(description="Worker DPS (jalankan di tiap node Worker)")
    ap.add_argument("--master", default=None, help="host:port Master (default dari config)")
    ap.add_argument("--id", default=None, help="worker_id (default hostname-pid)")
    ap.add_argument("--processes", type=int, default=None, help="jumlah proses Pool (default: jumlah core logis)")
    ap.add_argument("--config", default=None, help="path config.json")
    ap.add_argument("--max-retries", type=int, default=10)
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.master:
        host, _, port = args.master.partition(":")
        master_addr = (host, int(port or cfg["master_port"]))
    else:
        master_addr = ("127.0.0.1", cfg["master_port"])

    worker_id = args.id or f"{socket.gethostname()}-{os.getpid()}"
    processes = args.processes or os.cpu_count() or 1

    worker = Worker(master_addr, worker_id, processes, cfg, max_retries=args.max_retries)
    try:
        worker.run()
    except KeyboardInterrupt:
        log.info("Dihentikan oleh pengguna.")


if __name__ == "__main__":
    main()
