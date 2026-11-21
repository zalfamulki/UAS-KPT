"""Grafik hasil benchmark -> PNG di results/ (rancangan bagian 8, BAB IV).

Membaca CSV hasil run_experiments (plus summary.json untuk distribusi task
per worker pada T4). File yang hilang dilewati dengan peringatan.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from common.utils import setup_logger

log = setup_logger("plot")
RESULTS = Path(__file__).resolve().parents[1] / "results"


def _save(fig, name):
    out = RESULTS / name
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    log.info("Grafik: %s", out)


def plot_t2():
    f = RESULTS / "t2_local_parallel.csv"
    if not f.exists():
        return log.warning("Lewati T2: %s tidak ada", f)
    df = pd.read_csv(f)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.errorbar(df["processes"], df["exec_time_s_mean"], yerr=df["exec_time_s_std"],
                 marker="o", capsize=3)
    ax1.set_xlabel("Jumlah proses (P)"); ax1.set_ylabel("Execution time (s)")
    ax1.set_title("T2: Local parallel — exec time")
    ax1.grid(alpha=0.3)
    ax2.plot(df["processes"], df["speedup"], marker="o", label="speedup")
    ax2.plot(df["processes"], df["processes"], "--", label="ideal", alpha=0.5)
    ax2.plot(df["processes"], df["efficiency"], marker="s", label="efficiency")
    ax2.set_xlabel("Jumlah proses (P)"); ax2.set_ylabel("Rasio")
    ax2.set_title("T2: speedup & efficiency"); ax2.legend(); ax2.grid(alpha=0.3)
    _save(fig, "t2_speedup.png")


def plot_t6():
    f = RESULTS / "t6_scalability.csv"
    if not f.exists():
        return log.warning("Lewati T6: %s tidak ada", f)
    df = pd.read_csv(f)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(df["workers"], df["speedup"], marker="o", label="speedup")
    ax.plot(df["workers"], df["workers"], "--", label="ideal", alpha=0.5)
    ax.plot(df["workers"], df["efficiency"], marker="s", label="efficiency")
    ax.set_xlabel("Jumlah Worker"); ax.set_ylabel("Rasio")
    ax.set_title("T6: Scalability (speedup & efficiency)")
    ax.set_xticks(df["workers"])
    ax.legend(); ax.grid(alpha=0.3)
    _save(fig, "t6_scalability.png")


def plot_t3():
    f = RESULTS / "t3_distributed.csv"
    if not f.exists():
        return log.warning("Lewati T3: %s tidak ada", f)
    df = pd.read_csv(f)
    mean = df.groupby("workers")["throughput"].mean().reset_index()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar([str(w) for w in mean["workers"]], mean["throughput"], alpha=0.8)
    ax.set_xlabel("Jumlah Worker"); ax.set_ylabel("Throughput (port/s)")
    ax.set_title("T3: Throughput vs jumlah Worker")
    ax.grid(alpha=0.3, axis="y")
    _save(fig, "t3_throughput.png")


def plot_t4():
    # distribusi task per worker dari summary.json tiap run
    data = {}
    for mode in ("static", "dynamic"):
        for d in sorted(RESULTS.glob(f"t4_{mode}_r*/summary.json")):
            s = json.loads(d.read_text(encoding="utf-8"))
            ws = s.get("worker_stats", {})
            data.setdefault(mode, {})[d.parent.name] = {w: v["done"] for w, v in ws.items()}
    if not data:
        return log.warning("Lewati T4: summary.json t4_* tidak ditemukan")
    modes = [m for m in ("static", "dynamic") if m in data]
    fig, axes = plt.subplots(1, len(modes), figsize=(6 * len(modes), 4.5), squeeze=False)
    for ax, mode in zip(axes[0], modes):
        for run, dist in data[mode].items():
            items = sorted(dist.items())
            ax.bar([k for k, _ in items], [v for _, v in items], alpha=0.6, label=run)
        ax.set_title(f"T4: task done per worker ({mode})")
        ax.set_xlabel("Worker"); ax.set_ylabel("Task done")
        ax.legend(fontsize=7); ax.grid(alpha=0.3, axis="y")
    _save(fig, "t4_load_balance.png")


def plot_t5():
    f = RESULTS / "t5_fault_tolerance.csv"
    if not f.exists():
        return log.warning("Lewati T5: %s tidak ada", f)
    df = pd.read_csv(f)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    x = df["repeat"].astype(str)
    ax.bar(x, df["detection_s"].fillna(0), label="detection time (s)", alpha=0.8)
    ax.bar(x, df["recovery_s"].fillna(0), bottom=df["detection_s"].fillna(0),
           label="recovery time (s)", alpha=0.8)
    if "overhead_vs_t3_s" in df:
        for _, r in df.iterrows():
            ax.text(r["repeat"], 0.1, f"overhead {r['overhead_vs_t3_s']}s",
                    ha="center", fontsize=8)
    ax.set_xlabel("Repeat"); ax.set_ylabel("Detik")
    ax.set_title("T5: Fault tolerance — detection & recovery")
    ax.legend(); ax.grid(alpha=0.3, axis="y")
    _save(fig, "t5_recovery.png")


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    plot_t2()
    plot_t3()
    plot_t4()
    plot_t5()
    plot_t6()
    log.info("Semua grafik yang bisa dibuat sudah disimpan di results/.")


if __name__ == "__main__":
    main()
