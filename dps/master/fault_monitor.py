"""Fault monitor: heartbeat timeout -> Worker dianggap mati (rancangan 4.7).

Thread latar belakang yang memeriksa last_seen tiap Worker; bila tidak ada
kabar lebih lama dari heartbeat_timeout (mis. 3x interval), Master memandang
Worker mati dan task in-flight-nya di-requeue (logika requeue ada di
Master.mark_worker_dead agar satu sumber kebenaran untuk kedua pemicu:
timeout heartbeat ATAU koneksi terputus).
"""

import threading
import time

from common.utils import setup_logger

log = setup_logger("fault")


class FaultMonitor(threading.Thread):
    def __init__(self, master, check_interval=1.0):
        super().__init__(daemon=True)
        self.master = master
        self.check_interval = check_interval

    def run(self):
        while not self.master.done_event.is_set():
            time.sleep(self.check_interval)
            self.check()

    def check(self):
        now = time.time()
        for wid, w in list(self.master.workers.items()):
            if w["alive"] and (now - w["last_seen"]) > self.master.hb_timeout:
                log.warning("Worker %s tanpa kabar %.1f s (timeout %.1f s) -> dianggap mati",
                            wid, now - w["last_seen"], self.master.hb_timeout)
                self.master.mark_worker_dead(wid, reason="heartbeat_timeout")
