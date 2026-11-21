"""Simulator Target (rancangan bagian 4.2): ground truth + listener port 'open'.

- --generate : buat ground_truth.json (open/closed/filtered) secara
               deterministik (seed), sehingga hasil scan bisa diverifikasi.
- --serve    : buka listener TCP untuk semua port 'open'. Port 'closed' tidak
               dibuka (koneksi ditolak); port 'filtered' juga tidak dibuka dan
               membutuhkan aturan firewall DROP (lihat firewall_filtered.py)
               agar koneksi mengalami timeout. Tanpa firewall, 'filtered'
               berperilaku seperti 'closed' (fallback, dokumentasikan).

ETIKA (bagian 2 rancangan): jalankan hanya pada host milik sendiri /
yang diizinkan eksplisit.
"""

import argparse
import json
import random
import selectors
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.utils import setup_logger

log = setup_logger("target")


def generate_ground_truth(host, start, end, open_ratio, filtered_ratio, seed):
    """Bagi rentang port menjadi status open/closed/filtered secara acak
    namun deterministik (seed) — ground truth identik di semua mode uji."""
    rng = random.Random(seed)
    ports = list(range(start, end + 1))
    rng.shuffle(ports)
    n = len(ports)
    n_open = round(n * open_ratio)
    n_filtered = round(n * filtered_ratio)
    statuses = {}
    for p in ports[:n_open]:
        statuses[str(p)] = "open"
    for p in ports[n_open:n_open + n_filtered]:
        statuses[str(p)] = "filtered"
    for p in ports[n_open + n_filtered:]:
        statuses[str(p)] = "closed"
    gt = {
        "host": host,
        "range": [start, end],
        "seed": seed,
        "open_ratio": open_ratio,
        "filtered_ratio": filtered_ratio,
        "statuses": statuses,
    }
    counts = {s: sum(1 for v in statuses.values() if v == s)
              for s in ("open", "closed", "filtered")}
    return gt, counts


class ListenerFarm:
    """Semua listener dikelola SATU thread via selectors (hemat resource
    dibanding thread per port)."""

    def __init__(self, host, ports):
        self.sel = selectors.DefaultSelector()
        self.host = host
        for p in ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, p))
            s.listen(128)
            s.setblocking(False)
            self.sel.register(s, selectors.EVENT_READ, p)

    def serve_forever(self, stop_event):
        while not stop_event.is_set():
            try:
                events = self.sel.select(timeout=0.5)
            except OSError:
                continue
            for key, _mask in events:
                try:
                    conn, _addr = key.fileobj.accept()
                    conn.close()  # handshake TCP selesai -> scanner melihat 'open'
                except OSError:
                    pass

    def close_all(self):
        for key in list(self.sel.get_map().values()):
            try:
                key.fileobj.close()
            except OSError:
                pass
        self.sel.close()


def serve(gt, duration):
    host = gt["host"]
    open_ports = sorted(int(p) for p, st in gt["statuses"].items() if st == "open")
    if not open_ports:
        log.warning("Tidak ada port 'open' di ground truth — tidak ada listener dibuka.")
    farm = ListenerFarm(host, open_ports)
    stop = threading.Event()
    threading.Thread(target=farm.serve_forever, args=(stop,), daemon=True).start()
    log.info("Target %s berjalan: %d listener 'open' (rentang GT: %s)",
             host, len(open_ports), gt.get("range"))
    if gt.get("statuses") and any(st == "filtered" for st in gt["statuses"].values()):
        log.info("GT memuat port 'filtered' — pastikan firewall_filtered.py sudah "
                 "dipasang, atau catat keterbatasan fallback closed.")
    try:
        if duration > 0:
            time.sleep(duration)
        else:
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        farm.close_all()
        log.info("Target berhenti.")


def main():
    ap = argparse.ArgumentParser(description="Simulator target port scanning (host milik sendiri!)")
    ap.add_argument("--host", default="127.0.0.1", help="host logis di GT / bind listener (0.0.0.0 = semua antarmuka)")
    ap.add_argument("--generate", action="store_true", help="buat ground truth")
    ap.add_argument("--serve", action="store_true", help="jalankan listener")
    ap.add_argument("--gt", default="target/ground_truth.json", help="file ground truth")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=2000)
    ap.add_argument("--open-ratio", type=float, default=0.08)
    ap.add_argument("--filtered-ratio", type=float, default=0.0,
                    help="proporsi port filtered (butuh firewall_filtered.py agar benar-benar timeout)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--duration", type=int, default=0, help="detik berjalan (0 = sampai Ctrl+C)")
    args = ap.parse_args()

    if args.generate:
        gt, counts = generate_ground_truth(args.host, args.start, args.end,
                                           args.open_ratio, args.filtered_ratio, args.seed)
        out = Path(args.gt)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(gt, indent=2), encoding="utf-8")
        log.info("Ground truth tersimpan: %s (open=%d closed=%d filtered=%d)",
                 out, counts["open"], counts["closed"], counts["filtered"])
        return
    if args.serve:
        gt = json.loads(Path(args.gt).read_text(encoding="utf-8"))
        serve(gt, args.duration)
        return
    ap.error("Pilih --generate atau --serve")


if __name__ == "__main__":
    main()
