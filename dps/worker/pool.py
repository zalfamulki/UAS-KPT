"""Wrapper multiprocessing.Pool di Worker (rancangan bagian 4.4).

Satu Pool dihidupkan untuk umur Worker; tiap task (chunk port) diproses dengan
imap_unordered agar hasil mengalir tanpa menunggu seluruh chunk selesai.
"""

from multiprocessing import Pool

from worker.scanner import scan_port


def _scan_one(args):
    """Fungsi level-modul untuk picklability (Windows spawn)."""
    host, port, timeout = args
    return scan_port(host, port, timeout)


class ScanPool:
    def __init__(self, processes):
        self.processes = processes
        self._pool = None

    def _ensure_pool(self):
        if self._pool is None:
            self._pool = Pool(processes=self.processes)

    def scan_task(self, task):
        """Proses satu task {host, port_start, port_end, timeout}.
        Return list hasil {port, status} (urutan bebas, digabung Master)."""
        self._ensure_pool()
        ports = range(task["port_start"], task["port_end"] + 1)
        args = [(task["host"], p, task["timeout"]) for p in ports]
        chunksize = max(1, len(args) // (self.processes * 4))
        return list(self._pool.imap_unordered(_scan_one, args, chunksize))

    def close(self):
        if self._pool is not None:
            self._pool.close()
            self._pool.join()
            self._pool = None
