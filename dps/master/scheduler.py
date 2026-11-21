"""Task table + scheduling Master (rancangan bagian 4.3, 4.6, 4.7).

Dua mode untuk pembandingan Dynamic LB (T4):
- dynamic (pull): satu antrean global; Worker meminta task saat siap.
  Worker cepat otomatis mendapat lebih banyak task.
- static (pembanding): partisi sama besar per Worker saat REGISTER, tanpa
  re-pull antar Worker. Task hasil requeue masuk antrean fallback global
  (fault tolerance tetap berlaku di kedua mode).

Status task: PENDING -> IN_FLIGHT -> DONE / FAILED (batas retry, 4.7).
"""

import threading
from collections import deque

PENDING = "PENDING"
IN_FLIGHT = "IN_FLIGHT"
DONE = "DONE"
FAILED = "FAILED"


class Scheduler:
    def __init__(self, tasks, mode="dynamic", expected_workers=None, retry_limit=3):
        self.mode = mode
        self.expected_workers = expected_workers
        self.retry_limit = retry_limit
        self.lock = threading.RLock()
        self.table = {}
        for t in tasks:
            rec = dict(t)
            rec["status"] = PENDING
            rec["assigned_to"] = None
            self.table[t["task_id"]] = rec
        self.global_queue = (deque(self.table.keys()) if mode == "dynamic"
                             else deque())            # dynamic: semua task; static: hanya requeue
        self.static_partitions = {}                    # worker_id -> deque(task_id)
        self._partition_idx = 0
        self.requeued_total = 0
        self.failed_total = 0

    # ---------- penugasan ----------
    def assign_next(self, worker_id):
        """Ambil satu task untuk Worker (pull). Return task dict atau None."""
        with self.lock:
            tid = None
            if self.mode == "static":
                personal = self.static_partitions.get(worker_id)
                if personal:
                    tid = personal.popleft()
            if tid is None and self.global_queue:
                tid = self.global_queue.popleft()
            if tid is None:
                return None
            rec = self.table[tid]
            rec["status"] = IN_FLIGHT
            rec["assigned_to"] = worker_id
            return dict(rec)

    def register_static_partition(self, worker_id):
        """Bagi pekerjaan sama besar saat REGISTER (mode static, 4.6).

        Partisi dihitung atas SELURUH daftar task (urutan pembuatan), bukan
        atas task yang tersisa, agar setiap registrasi berikutnya tidak
        menyusut dan ada task yang tak pernah menjadi milik siapa pun.
        Worker ke-i mendapat slice ke-i dari pembagian sama besar.
        """
        with self.lock:
            if worker_id in self.static_partitions:
                return
            all_ids = list(self.table.keys())  # urutan pembuatan task
            expected = self.expected_workers or 1
            idx = self._partition_idx
            self._partition_idx += 1
            base, extra = divmod(len(all_ids), expected)
            start = idx * base + min(idx, extra)
            size = base + (1 if idx < extra else 0)
            share = all_ids[start:start + size]
            for tid in share:
                self.table[tid]["assigned_to"] = worker_id  # kepemilikan, status tetap PENDING
            self.static_partitions[worker_id] = deque(share)

    # ---------- penyelesaian & kegagalan ----------
    def mark_done(self, task_id):
        with self.lock:
            self.table[task_id]["status"] = DONE

    def requeue_for(self, worker_id):
        """Kembalikan task milik Worker mati ke antrean (4.7): semua task
        IN_FLIGHT (dan PENDING yang sudah jadi miliknya di mode static).
        attempt+1; melewati retry_limit -> FAILED. Return (requeued, failed)."""
        with self.lock:
            requeued, failed = [], []
            for tid, rec in self.table.items():
                if rec["assigned_to"] != worker_id:
                    continue
                if rec["status"] not in (IN_FLIGHT, PENDING):
                    continue
                rec["attempt"] += 1
                rec["assigned_to"] = None
                if rec["attempt"] >= self.retry_limit:
                    rec["status"] = FAILED
                    self.failed_total += 1
                    failed.append(tid)
                else:
                    rec["status"] = PENDING
                    self.requeued_total += 1
                    requeued.append(tid)
                    self.global_queue.appendleft(tid)  # prioritas diproses ulang
            self.static_partitions.pop(worker_id, None)
            return requeued, failed

    # ---------- status ----------
    def stats(self):
        with self.lock:
            by_status = {s: 0 for s in (PENDING, IN_FLIGHT, DONE, FAILED)}
            for rec in self.table.values():
                by_status[rec["status"]] += 1
            return {"by_status": by_status, "total": len(self.table),
                    "queue_len": len(self.global_queue),
                    "requeued_total": self.requeued_total,
                    "failed_total": self.failed_total}

    def is_complete(self):
        with self.lock:
            return all(rec["status"] in (DONE, FAILED) for rec in self.table.values())
