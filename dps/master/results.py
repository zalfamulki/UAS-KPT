"""Result store Master (rancangan bagian 4.2, 4.7, 6.2).

- Menggabungkan hasil per (host, port), de-duplikasi per task_id (idempotensi
  4.7: hasil duplikat dari Worker "hidup lagi" dibuang).
- Ekspor JSON + CSV.
- Verifikasi korektness terhadap ground truth (6.2): hitung selisih serta
  precision/recall khusus status 'open'.
"""

import csv
import json
import threading
import time
from pathlib import Path


class ResultsStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.task_meta = {}     # task_id -> {worker_id, attempt, duration, ports}
        self.port_status = {}   # (host, port) -> status
        self.duplicates = 0
        self.last_result_ts = None

    def submit(self, task_rec, worker_id, results, duration):
        """Simpan hasil satu task. Return True bila diterima, False bila
        duplikat (task sudah pernah dihasilkan)."""
        tid = task_rec["task_id"]
        host = task_rec["host"]
        with self.lock:
            if tid in self.task_meta:
                self.duplicates += 1
                return False
            self.task_meta[tid] = {
                "worker_id": worker_id,
                "attempt": task_rec.get("attempt", 0),
                "duration": duration,
                "ports": len(results),
            }
            for r in results:
                self.port_status[(host, r["port"])] = r["status"]
            self.last_result_ts = time.time()
            return True

    def counts(self):
        with self.lock:
            return {"tasks": len(self.task_meta), "ports": len(self.port_status),
                    "duplicates": self.duplicates}

    def export(self, out_dir):
        """Tulis results.json + results.csv. Return path results.json."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        with self.lock:
            data = {
                "port_results": {f"{h}|{p}": st for (h, p), st in self.port_status.items()},
                "task_results": self.task_meta,
                "duplicates": self.duplicates,
            }
            rows = sorted(self.port_status.items())
        (out / "results.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        with open(out / "results.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["host", "port", "status"])
            for (h, p), st in rows:
                w.writerow([h, p, st])
        return out / "results.json"


def compare_ground_truth(port_status, gt):
    """Bandingkan hasil scan dengan ground truth (rancangan 6.2).

    port_status: {(host, port): status}; gt: dict dari ground_truth.json.
    Return: matched, mismatched, precision_open, recall_open.
    """
    gt_host = str(gt.get("host", ""))
    gt_status = gt["statuses"]
    matched = mismatched = 0
    pred_open, actual_open = set(), set()
    for (host, port), status in port_status.items():
        if str(host).lower() != gt_host.lower():
            mismatched += 1  # host di luar ground truth
            continue
        expected = gt_status.get(str(port))
        if expected is None:
            mismatched += 1  # port di luar rentang GT
            continue
        if status == expected:
            matched += 1
        else:
            mismatched += 1
        if status == "open":
            pred_open.add(port)
        if expected == "open":
            actual_open.add(port)
    tp = len(pred_open & actual_open)
    precision = tp / len(pred_open) if pred_open else 1.0
    recall = tp / len(actual_open) if actual_open else 1.0
    return {"matched": matched, "mismatched": mismatched, "total": matched + mismatched,
            "precision_open": round(precision, 4), "recall_open": round(recall, 4)}
