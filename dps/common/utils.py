"""Utilitas bersama DPS: logging, konfigurasi, allowlist, dan
task decomposition (rancangan bagian 4.3)."""

import json
import logging
import sys
import time
from pathlib import Path

# Root folder proyek (dps/)
ROOT = Path(__file__).resolve().parents[1]

# Nilai default; semuanya [USULAN] dan harus dikalibrasi (rancangan 6.2)
DEFAULT_CONFIG = {
    "master_host": "0.0.0.0",
    "master_port": 5000,
    "scan_timeout": 0.5,
    "chunk_size": 250,
    "heartbeat_interval": 2.0,
    "heartbeat_timeout": 6.0,
    "retry_limit": 3,
    "mode": "dynamic",
    "results_dir": "results",
}


def setup_logger(name):
    """Logger sederhana ke stderr dengan format waktu singkat."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-7s %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def load_config(path=None):
    """Muat config.json di atas nilai default (bagian 5: angka wajib
    dikalibrasi lewat percobaan, bukan dianggap pasti)."""
    cfg = dict(DEFAULT_CONFIG)
    p = Path(path) if path else (ROOT / "config.json")
    if p.exists():
        cfg.update(json.loads(p.read_text(encoding="utf-8")))
    return cfg


def now_ts():
    return time.time()


def generate_tasks(targets, chunk_size, scan_timeout):
    """Task decomposition (4.3): pecah (host, start, end) menjadi chunk
    berukuran tetap. Task saling independen -> aman didistribusikan.

    targets: iterable berisi (host, port_start, port_end).
    Return: list task dict {task_id, host, port_start, port_end, timeout, attempt}.
    """
    tasks = []
    for host, start, end in targets:
        cur = start
        while cur <= end:
            stop = min(cur + chunk_size - 1, end)
            tasks.append({
                "task_id": f"t{len(tasks):05d}",
                "host": host,
                "port_start": cur,
                "port_end": stop,
                "timeout": scan_timeout,
                "attempt": 0,
            })
            cur = stop + 1
    return tasks


def total_ports(tasks):
    return sum(t["port_end"] - t["port_start"] + 1 for t in tasks)


def read_targets(path):
    """Baca targets.txt: satu target per baris, format 'host port_start port_end'."""
    targets = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 3:
            raise ValueError(f"Baris target tidak sah: {raw!r} (format: host start end)")
        host, start, end = parts[0], int(parts[1]), int(parts[2])
        if start < 1 or end < start or end > 65535:
            raise ValueError(f"Rentang port tidak sah: {raw!r}")
        targets.append((host, start, end))
    return targets


def read_allowlist(path):
    """Baca allowlist.txt (bagian 2: hanya target milik sendiri yang diizinkan)."""
    allowed = set()
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            allowed.add(line.lower())
    return allowed
