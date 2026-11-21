"""T1 - baseline sequential (rancangan bagian 6.3).

Satu proses, tanpa Master-Worker, tanpa jaringan. Output: exec time,
throughput, dan (opsional) verifikasi vs ground truth. Hasil CSV dipakai
sebagai penumerator speedup (S = T_seq / T(p)).
"""

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.utils import load_config, read_targets, setup_logger
from master.results import compare_ground_truth
from worker.scanner import scan_range

log = setup_logger("t1")


def run_once(targets, timeout):
    t0 = time.monotonic()
    results = {}
    for host, start, end in targets:
        for r in scan_range(host, start, end, timeout):
            results[(host, r["port"])] = r["status"]
    return results, time.monotonic() - t0


def main():
    ap = argparse.ArgumentParser(description="T1: baseline sequential")
    ap.add_argument("--targets", default="targets.txt")
    ap.add_argument("--config", default=None)
    ap.add_argument("--gt", default=None, help="ground_truth.json untuk verifikasi")
    ap.add_argument("--repeat", type=int, default=3, help="pengulangan (rancangan: min 3)")
    ap.add_argument("--out", default="results/t1_sequential.csv")
    args = ap.parse_args()

    cfg = load_config(args.config)
    targets = read_targets(args.targets)
    ports = sum(e - s + 1 for _, s, e in targets)

    gt = None
    if args.gt:
        gt = json.loads(Path(args.gt).read_text(encoding="utf-8"))

    rows = []
    for i in range(args.repeat):
        results, exec_time = run_once(targets, cfg["scan_timeout"])
        row = {"repeat": i + 1, "exec_time_s": round(exec_time, 3), "ports": ports,
               "throughput": round(ports / exec_time, 2) if exec_time else None}
        if gt:
            cmp = compare_ground_truth(results, gt)
            row.update({"matched": cmp["matched"], "mismatched": cmp["mismatched"],
                        "precision_open": cmp["precision_open"], "recall_open": cmp["recall_open"]})
            log.info("Repeat %d: exec=%.3fs matched=%d mismatched=%d",
                     i + 1, exec_time, cmp["matched"], cmp["mismatched"])
        else:
            log.info("Repeat %d: exec=%.3fs (%d port)", i + 1, exec_time, ports)
        rows.append(row)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    log.info("T1 selesai. Mean exec=%.3fs -> %s",
             statistics.mean(r["exec_time_s"] for r in rows), out)


if __name__ == "__main__":
    main()
