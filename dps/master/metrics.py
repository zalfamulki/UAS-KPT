"""Metrik performa Master (rancangan bagian 7).

- Execution Time (7.1): dari task pertama didistribusikan s.d. hasil terakhir.
- Throughput: total port / execution time.
- Load imbalance (7.1): max(task done per worker) / rata-ratanya.
- Detection & Recovery Time (7.2): dihitung dari events worker_down/requeue/
  task_done.
- CPU/Memory per worker (7.3) dari HEARTBEAT: rata-rata & puncak.

Semua event ditulis ke events.csv; ringkasan ke summary.json.
"""

import csv
import json
import time
from pathlib import Path


class MetricsLogger:
    def __init__(self):
        self.events = []          # {ts, event, worker_id, task_id, detail}
        self.heartbeat_log = []   # {ts, worker_id, cpu, mem}
        self.t_start = None       # task pertama didistribusikan
        self.t_end = None         # hasil terakhir diterima

    def event(self, name, worker_id=None, task_id=None, detail=None):
        now = time.time()
        self.events.append({"ts": now, "event": name, "worker_id": worker_id,
                            "task_id": task_id, "detail": detail})
        if name == "task_assign" and self.t_start is None:
            self.t_start = now
        return now

    def mark_last_result(self):
        self.t_end = time.time()

    def heartbeat(self, worker_id, cpu, mem):
        self.heartbeat_log.append({"ts": time.time(), "worker_id": worker_id,
                                   "cpu": cpu, "mem": mem})

    # ---------- analisis ----------
    def compute_worker_stats(self):
        per = {}
        for e in self.events:
            wid = e["worker_id"]
            if not wid:
                continue
            d = per.setdefault(wid, {"assigned": 0, "done": 0, "last_event": None})
            if e["event"] == "register":
                det = e.get("detail") or {}
                if det:
                    d["hostname"] = det.get("hostname")
                    d["ip"] = det.get("ip")
                    d["processes"] = det.get("processes")
            elif e["event"] == "task_assign":
                d["assigned"] += 1
            elif e["event"] == "task_done":
                d["done"] += 1
                d["last_event"] = e["ts"]
        done_counts = [d["done"] for d in per.values()] or [0]
        avg = sum(done_counts) / len(done_counts)
        imbalance = (max(done_counts) / avg) if avg else None
        return per, (round(imbalance, 3) if imbalance is not None else None)

    def compute_failures(self):
        """Detection & Recovery Time per kejadian worker_down (7.2).

        detection_s = t_fail - last_seen (jarak heartbeat terakhir; perkiraan
        waktu mati dari sisi Master). recovery_s = selisih t_fail terhadap
        selesainya SEMUA task hasil requeue kejadian tsb.
        """
        done_ts = {e["task_id"]: e["ts"] for e in self.events if e["event"] == "task_done"}
        failures = []
        for e in self.events:
            if e["event"] != "worker_down":
                continue
            detail = e.get("detail") or {}
            t_fail = e["ts"]
            requeued = detail.get("requeued", [])
            detection = t_fail - detail.get("last_seen", t_fail)
            if requeued:
                recoverable = [done_ts[tid] for tid in requeued if tid in done_ts]
                recovery = (max(recoverable) - t_fail) if recoverable else None
            else:
                recovery = None
            failures.append({
                "worker_id": e["worker_id"],
                "reason": detail.get("reason"),
                "t_fail": t_fail,
                "detection_s": round(max(detection, 0.0), 3),
                "recovery_s": round(recovery, 3) if recovery is not None else None,
                "requeued_tasks": len(requeued),
                "failed_tasks": len(detail.get("failed", [])),
            })
        return failures

    def compute_sys_stats(self):
        per = {}
        for h in self.heartbeat_log:
            if h["cpu"] is None:
                continue
            d = per.setdefault(h["worker_id"], {"cpu": [], "mem": []})
            d["cpu"].append(h["cpu"])
            d["mem"].append(h["mem"])
        out = {}
        for wid, v in per.items():
            out[wid] = {
                "cpu_avg": round(sum(v["cpu"]) / len(v["cpu"]), 2),
                "cpu_peak": round(max(v["cpu"]), 2),
                "mem_avg": round(sum(v["mem"]) / len(v["mem"]), 2),
                "mem_peak": round(max(v["mem"]), 2),
            }
        return out

    # ---------- penyimpanan ----------
    def save(self, out_dir, summary):
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)

        with open(out / "events.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ts", "event", "worker_id", "task_id", "detail"])
            w.writeheader()
            for e in self.events:
                row = dict(e)
                row["detail"] = json.dumps(row["detail"], ensure_ascii=False) if row["detail"] is not None else ""
                w.writerow(row)

        with open(out / "heartbeats.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ts", "worker_id", "cpu", "mem"])
            w.writeheader()
            for h in self.heartbeat_log:
                w.writerow(h)

        (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return out / "summary.json"

    def build_summary(self, total_ports, scheduler_stats, results_counts, mode, n_tasks):
        exec_time = (self.t_end - self.t_start) if (self.t_start and self.t_end) else None
        throughput = (total_ports / exec_time) if exec_time else None
        worker_stats, imbalance = self.compute_worker_stats()
        return {
            "mode": mode,
            "n_tasks": n_tasks,
            "execution_time_s": round(exec_time, 3) if exec_time else None,
            "total_ports": total_ports,
            "throughput_ports_per_s": round(throughput, 2) if throughput else None,
            "tasks": scheduler_stats,
            "results": results_counts,
            "worker_stats": worker_stats,
            "load_imbalance_ratio": imbalance,
            "failures": self.compute_failures(),
            "sys_stats": self.compute_sys_stats(),
            "t_start": self.t_start,
            "t_end": self.t_end,
        }
