"""Pemantau CPU/Memory Worker dengan psutil (rancangan bagian 7.3).

Sampel diambil saat heartbeat (interval H) dan dilaporkan ke Master; nilai
avg/peak per node dipakai untuk tabel utilization di BAB IV. Bila psutil
tidak terinstal, Worker tetap berjalan dengan statistik None (tidak memblokir
pengujian — dicatat sebagai keterbatasan).
"""

try:
    import psutil
except ImportError:
    psutil = None


class SysMonitor:
    def __init__(self):
        self._last = {"cpu": None, "mem": None}
        self._peak = {"cpu": 0.0, "mem": 0.0}
        self._sum = {"cpu": 0.0, "mem": 0.0}
        self._n = 0

    def sample(self):
        """Ambil satu sampel instan; dipanggil berkala oleh thread heartbeat."""
        if psutil is None:
            return dict(self._last)
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        self._last = {"cpu": cpu, "mem": mem}
        self._peak["cpu"] = max(self._peak["cpu"], cpu)
        self._peak["mem"] = max(self._peak["mem"], mem)
        self._sum["cpu"] += cpu
        self._sum["mem"] += mem
        self._n += 1
        return dict(self._last)

    def stats(self):
        """Return {last, avg, peak} untuk laporan."""
        avg = {k: (round(self._sum[k] / self._n, 2) if self._n else None)
               for k in ("cpu", "mem")}
        return {
            "last": dict(self._last),
            "avg": avg,
            "peak": {k: round(v, 2) for k, v in self._peak.items()},
        }
