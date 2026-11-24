"""Tampilan terminal Master: menu, tabel worker, monitor, dan ringkasan akhir.

Modul ini hanya membentuk teks dari keadaan Master (tidak mengubah state),
supaya logika jaringan/scheduler tetap terpisah dan mudah diuji.
"""

from __future__ import annotations

import time
from pathlib import Path

from common.ui import console


# ---------- util format ----------
def _fmt_duration(seconds):
    if seconds is None:
        return "-"
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.2f} s"
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes}m {rest:02d}s"


def _fmt_rate(value):
    return "-" if not value else f"{value:.1f} port/s"


def _fmt_pct(value):
    return "-" if value is None else f"{value:.0f}%"


def _clock():
    return time.strftime("%H:%M:%S")


def _snapshot(master):
    with master.lock:
        workers = [(wid, dict(w)) for wid, w in master.workers.items()]
        dist = {
            "mode": master.distribution.get("mode", "all"),
            "tokens": list(master.distribution.get("tokens") or []),
            "worker_ids": set(master.distribution.get("worker_ids") or set()),
        }
    workers.sort(key=lambda item: (str(item[1].get("hostname", "")), str(item[0])))
    return workers, dist


def _allowed(wid, worker, dist):
    if dist["mode"] == "all":
        return True
    if wid in dist["worker_ids"]:
        return True
    ip = (worker.get("addr")[0] if worker.get("addr") else "").lower()
    host = str(worker.get("hostname", "")).lower()
    return any(tok in wid.lower() or tok in host or tok in ip for tok in dist["tokens"])


def _dist_label(dist):
    if dist["mode"] == "all":
        return "SEMUA worker"
    tokens = dist["tokens"]
    if not tokens:
        return "tidak ada"
    if len(tokens) <= 3:
        return "hanya: " + ", ".join(tokens)
    return f"hanya {len(tokens)} worker"


def _task_label(worker):
    task = worker.get("task")
    if not task:
        return "-"
    return f"{task.get('task_id', '?')} {task.get('port_start', '?')}-{task.get('port_end', '?')}"


def _status_cell(worker, started=True):
    if not worker.get("alive"):
        return console.style("MATI", "bold", "red")
    if worker.get("task"):
        return console.style("bekerja", "bold", "green")
    if not started:
        return console.style("menunggu mulai", "yellow")
    reason = worker.get("idle_reason")
    if reason == "filtered":
        return console.style("tidak dipilih", "yellow")
    if reason == "empty":
        return console.style("menunggu tugas", "yellow")
    if reason == "not_started":
        return console.style("menunggu mulai", "yellow")
    return console.style("siap", "green")


def _stats(master):
    st = master.scheduler.stats()
    rc = master.results.counts()
    alive = busy = 0
    with master.lock:
        for worker in master.workers.values():
            if worker.get("alive"):
                alive += 1
                if worker.get("task"):
                    busy += 1
        total_workers = len(master.workers)
    elapsed = None
    if master.metrics.t_start:
        elapsed = time.time() - master.metrics.t_start
    throughput = (rc["ports"] / elapsed) if elapsed and elapsed > 0 else None
    return st, rc, alive, busy, total_workers, elapsed, throughput


def _metric_items(master, st, rc, alive, busy, total_workers, elapsed, throughput, dist):
    done = st["by_status"]["DONE"]
    failed = st["by_status"]["FAILED"]
    task_text = f"{done}/{st['total']} selesai"
    if failed:
        task_text += f" · {failed} gagal"
    if master.scan_finished:
        worker_text = f"{alive}/{total_workers} tersambung"
    elif not master.started:
        worker_text = f"{alive}/{total_workers} siap"
    else:
        worker_text = f"{alive}/{total_workers} aktif"
        if busy:
            worker_text += f" · {busy} bekerja"
    return [
        ("WORKER", worker_text),
        ("TUGAS", task_text),
        ("PORT", f"{rc['ports']}/{master.total_ports}"),
        ("WAKTU", _fmt_duration(elapsed)),
        ("THROUGHPUT", _fmt_rate(throughput)),
        ("DISTRIBUSI", _dist_label(dist)),
    ]


# ---------- tabel worker ----------
def worker_table(master, full=False):
    workers, dist = _snapshot(master)
    if not workers:
        return console.panel("WORKER TERHUBUNG", [
            "Belum ada worker yang masuk.",
            "Master tetap diam (tidak mengeluarkan output berulang).",
            "Tabel ini otomatis muncul begitu worker terhubung.",
        ])

    wide = console.width >= (120 if full else 100)
    very_wide = console.width >= (140 if full else 130)
    show_id = full and console.width >= 70
    show_task = (console.width >= 70
                 and (console.width >= 90
                      or (not full and dist["mode"] == "all")))
    show_dist = dist["mode"] != "all" or (full and console.width >= 130)

    headers = ["#"]
    aligns = ["r"]
    mins = [1]
    if show_id:
        headers.append("Worker ID")
        aligns.append("l")
        mins.append(10)
    headers += ["Perangkat", "IP"]
    aligns += ["l", "l"]
    mins += [10, 15]
    if wide:
        headers += ["Proses", "CPU"]
        aligns += ["r", "r"]
        mins += [6, 5]
    if very_wide:
        headers.append("RAM")
        aligns.append("r")
        mins.append(5)
    headers.append("Tugas")
    aligns.append("c")
    mins.append(5)
    if show_task:
        headers.append("Task aktif")
        aligns.append("l")
        mins.append(8)
    if show_dist:
        headers.append("Distribusi")
        aligns.append("c")
        mins.append(9)
    headers.append("Status")
    aligns.append("l")
    mins.append(10)

    rows = []
    for idx, (wid, worker) in enumerate(workers, 1):
        ip = worker.get("addr")[0] if worker.get("addr") else "?"
        row = [str(idx)]
        if show_id:
            row.append(wid)
        row += [str(worker.get("hostname", "?")), ip]
        if wide:
            row += [str(worker.get("processes", "?")), _fmt_pct(worker.get("cpu"))]
        if very_wide:
            row.append(_fmt_pct(worker.get("mem")))
        row.append(f"{worker.get('done', 0)}/{worker.get('assigned', 0)}")
        if show_task:
            row.append(_task_label(worker))
        if show_dist:
            row.append("ya" if _allowed(wid, worker, dist) else "-")
        row.append(_status_cell(worker, getattr(master, "started", True)))
        rows.append(row)

    table = console.table(headers, rows, aligns=aligns, min_widths=mins)
    if not full:
        legend = "Tugas = selesai/diterima"
        if show_task:
            legend += " · Task aktif = tugas yang sedang dikerjakan"
        table += "\n  " + console.style(
            console.truncate(legend, console.width - 2), "dim")
    return table


# ---------- aktivitas ----------
def activity_panel(master, limit=5):
    with master.lock:
        entries = list(master.activity)[-limit:]
    lines = ["  " + console.style("AKTIVITAS TERAKHIR", "bold", "cyan")]
    if not entries:
        lines.append("  " + console.style("(belum ada aktivitas)", "dim"))
        return "\n".join(lines)
    color = {"join": "green", "down": "red", "start": "green",
             "dist": "yellow", "info": "white", "warn": "red"}
    for ts, text, kind in entries:
        stamp = console.style(time.strftime("%H:%M:%S", time.localtime(ts)), "gray")
        line = f"  {stamp}  {console.style(text, color.get(kind, 'white'))}"
        lines.append(console.truncate(line, console.width))
    return "\n".join(lines)


# ---------- layar ----------
def header(master):
    lines = [
        console.banner(
            "DPS · DISTRIBUTED PORT SCANNER",
            "Master–Worker port scanner · UAS KPT Tema 14",
            "MASTER",
        ),
        "",
        "  " + console.style(console.truncate(
            f"Mode {master.mode} · Bind {master.bind_host}:{master.port} · "
            f"{len(master.scheduler.table)} tugas · {master.total_ports} port · "
            f"chunk {master.chunk_size}", console.width - 2), "dim"),
    ]
    return "\n".join(lines)


def waiting_panel(master):
    host = getattr(master, "display_host", master.bind_host)
    return console.panel("MENUNGGU WORKER TERHUBUNG", [
        "Master siap. Belum ada worker yang masuk — layar ini TIDAK berkedip.",
        "",
        "Di setiap PC worker jalankan:",
        f"  python worker/worker.py --master {host}:{master.port}",
        "",
        "Tabel worker dan menu akan otomatis diperbarui saat worker terhubung.",
    ])


def render_home(master):
    st, rc, alive, busy, total_workers, elapsed, throughput = _stats(master)
    workers, dist = _snapshot(master)
    parts = [header(master), ""]

    if master.scan_finished:
        parts.append("  " + console.style(
            "STATUS: SELESAI - worker tetap tersambung sampai Anda memilih [0].",
            "bold", "green"))
        parts.append("")
    elif not master.started:
        parts.append("  " + console.style(
            "STATUS: SIAP — pemindaian belum dimulai. Pilih [1] untuk mengirim tugas.",
            "bold", "yellow"))
        parts.append("")
    else:
        parts.append("  " + console.style(
            "STATUS: BERJALAN — worker menerima tugas dari Master.", "bold", "green"))
        parts.append("")

    parts.append(console.kv_panel(
        _metric_items(master, st, rc, alive, busy, total_workers, elapsed, throughput, dist),
        cols=6 if console.width >= 120 else (3 if console.width >= 90 else 2)))
    parts.append("")
    parts.append("  Progres port  " + console.progress(rc["ports"], master.total_ports, 28)
                 + f"  ({rc['ports']}/{master.total_ports})")
    parts.append("")

    if workers:
        parts.append(console.section(f"WORKER TERHUBUNG ({len(workers)})"))
        parts.append(worker_table(master))
    else:
        parts.append(waiting_panel(master))
    parts.append("")
    parts.append(activity_panel(master))
    parts.append("")
    parts.append(console.section("MENU"))
    parts.append(console.menu(menu_items(master)))
    return "\n".join(parts)


def menu_items(master):
    if master.scan_finished:
        first = ("1", "Lihat hasil", "Tampilkan ringkasan tugas dan worker")
    elif not master.started:
        first = ("1", "Mulai pemindaian", "Kirim tugas ke semua worker yang terhubung")
    else:
        first = ("1", "Monitor langsung", "Dashboard refresh otomatis tiap 1 detik")
    return [
        first,
        ("2", "Status ringkas", "Ringkasan + tabel worker (sekali lihat)"),
        ("3", "Daftar worker lengkap", "Tampilkan Worker ID, proses, CPU, RAM"),
        ("4", "Atur distribusi", "Pilih worker tertentu atau kembali ke semua"),
        ("5", "Bantuan", "Arti menu, status, dan perintah lama"),
        ("0", "Keluar & simpan hasil", "Hentikan master dengan rapi"),
    ]


def render_status(master, full=False):
    st, rc, alive, busy, total_workers, elapsed, throughput = _stats(master)
    workers, dist = _snapshot(master)
    parts = [header(master), ""]
    parts.append(console.kv_panel(
        _metric_items(master, st, rc, alive, busy, total_workers, elapsed, throughput, dist),
        cols=6 if console.width >= 120 else (3 if console.width >= 90 else 2)))
    parts.append("")
    parts.append("  Progres port  " + console.progress(rc["ports"], master.total_ports, 28)
                 + f"  ({rc['ports']}/{master.total_ports})")
    parts.append("")
    title = "DAFTAR WORKER LENGKAP" if full else f"WORKER TERHUBUNG ({len(workers)})"
    parts.append(console.section(title))
    parts.append(worker_table(master, full=full))
    if not workers:
        parts.append("")
        parts.append(waiting_panel(master))
    parts.append("")
    parts.append(activity_panel(master))
    return "\n".join(parts)


def render_live(master):
    st, rc, alive, busy, total_workers, elapsed, throughput = _stats(master)
    workers, dist = _snapshot(master)
    left = console.style("MONITOR LANGSUNG", "bold", "cyan")
    right = console.style(f"{_clock()} · refresh 1 dtk", "dim")
    gap = max(1, console.width - console.visible_len(left) - console.visible_len(right) - 4)
    parts = ["  " + left + " " * gap + right, ""]
    parts.append(console.kv_panel(
        _metric_items(master, st, rc, alive, busy, total_workers, elapsed, throughput, dist),
        cols=6 if console.width >= 120 else (3 if console.width >= 90 else 2)))
    parts.append("")
    parts.append("  Progres port  " + console.progress(rc["ports"], master.total_ports, 32)
                 + f"  ({rc['ports']}/{master.total_ports})")
    parts.append("")
    parts.append(console.section(f"WORKER ({len(workers)})"))
    parts.append(worker_table(master))
    if dist["mode"] != "all" and st["queue_len"] > 0:
        parts.append("")
        parts.append("  " + console.style(
            f"[info] {st['queue_len']} tugas antre — worker yang tidak dipilih sengaja idle. "
            "Pilih menu [4] untuk kembali ke semua.", "yellow"))
    parts.append("")
    parts.append(activity_panel(master))
    return "\n".join(parts)


def render_distribution(master):
    workers, dist = _snapshot(master)
    parts = [header(master), ""]
    parts.append(console.section("ATUR DISTRIBUSI TUGAS"))
    if not workers:
        parts.append(waiting_panel(master))
        parts.append("")
        parts.append("  " + console.style("Belum ada worker — distribusi masih SEMUA.", "dim"))
        return "\n".join(parts)

    rows = []
    show_id = console.width >= 70
    show_proses = console.width >= 80
    for idx, (wid, worker) in enumerate(workers, 1):
        row = [str(idx)]
        if show_id:
            row.append(wid)
        row += [
            str(worker.get("hostname", "?")),
            worker.get("addr")[0] if worker.get("addr") else "?",
        ]
        if show_proses:
            row.append(str(worker.get("processes", "?")))
        row += [
            _status_cell(worker, getattr(master, "started", True)),
            console.style("ya", "green") if _allowed(wid, worker, dist)
            else console.style("-", "dim"),
        ]
        rows.append(row)
    headers = ["#"]
    aligns = ["r"]
    mins = [1]
    if show_id:
        headers.append("Worker ID")
        aligns.append("l")
        mins.append(10)
    headers += ["Perangkat", "IP"]
    aligns += ["l", "l"]
    mins += [10, 15]
    if show_proses:
        headers.append("Proses")
        aligns.append("r")
        mins.append(6)
    headers += ["Status", "Ikut"]
    aligns += ["l", "c"]
    mins += [10, 4]
    parts.append(console.table(headers, rows, aligns=aligns, min_widths=mins))
    parts.append("")
    parts.append("  Distribusi aktif: " + console.style(_dist_label(dist), "bold", "yellow"))
    parts.append("")
    parts.append(console.panel("CARA MEMILIH", [
        "[a]              semua worker (default)",
        "[1,3] / [1 3]    nomor worker pada tabel di atas",
        "[nama / IP]      ketik langsung, boleh beberapa (pisah spasi/koma)",
        "[0]              kembali tanpa mengubah distribusi",
        "",
        "Worker yang tidak dipilih tetap terhubung, hanya tidak diberi tugas.",
    ]))
    return "\n".join(parts)


def render_help(master):
    workers, dist = _snapshot(master)
    parts = [header(master), ""]
    parts.append(console.panel("BANTUAN MASTER", [
        "MENU",
        "  [1] Mulai pemindaian / monitor / lihat hasil sesuai status",
        "  [2] Ringkasan status + tabel worker (sekali lihat)",
        "  [3] Daftar worker lengkap (ID, proses, CPU, RAM, distribusi)",
        "  [4] Atur distribusi: semua worker atau hanya worker tertentu",
        "  [5] Bantuan ini",
        "  [0] Keluar & simpan hasil seadanya",
        "",
        "ARTI STATUS WORKER",
        "  bekerja          : sedang mengerjakan satu tugas",
        "  menunggu mulai   : master belum menekan [1] Mulai pemindaian",
        "  menunggu tugas   : antrean kosong / tugas dipegang worker lain",
        "  tidak dipilih    : sengaja diidlekan oleh menu [4]",
        "  MATI             : koneksi putus; tugasnya otomatis di-requeue",
        "",
        "PERINTAH LAMA (masih diterima)",
        "  list · pilih <nama/IP/nomor> · all · keluar · bantuan",
        "",
        "Master hanya menulis ulang layar saat keadaan berubah atau menu dipilih,",
        "jadi terminal tidak lagi dipenuhi output tiap 2 detik.",
    ]))
    if workers:
        parts.append("")
        parts.append("  " + console.style(
            f"Distribusi sekarang: {_dist_label(dist)} · {len(workers)} worker terhubung",
            "dim"))
    return "\n".join(parts)


def render_final(master, summary):
    st = summary.get("tasks") or {}
    by = st.get("by_status") or {}
    results = summary.get("results") or {}
    gt = summary.get("ground_truth")
    complete = getattr(master, "scan_finished", False)
    title = "PEMINDAIAN SELESAI" if complete else "SESI MASTER BERAKHIR"
    subtitle = ("Semua tugas telah diproses" if complete
                else "Hasil yang sudah terkumpul disimpan")
    badge = "SELESAI" if complete else "PARSIAL"
    parts = [console.banner(title, subtitle, badge), ""]

    items = [
        ("WAKTU", _fmt_duration(summary.get("execution_time_s"))),
        ("THROUGHPUT", _fmt_rate(summary.get("throughput_ports_per_s"))),
        ("TUGAS", f"{by.get('DONE', 0)}/{st.get('total', 0)}"),
        ("PORT", f"{results.get('ports', 0)}/{summary.get('total_ports', 0)}"),
        ("DUPLIKAT", str(results.get("duplicates", 0))),
        ("IMBALANCE", str(summary.get("load_imbalance_ratio", "-"))),
    ]
    parts.append(console.kv_panel(items, cols=6 if console.width >= 120 else 3))
    parts.append("")

    if gt:
        parts.append(console.section("VERIFIKASI GROUND TRUTH"))
        parts.append(console.kv_panel([
            ("MATCHED", str(gt.get("matched", "-"))),
            ("MISMATCHED", str(gt.get("mismatched", "-"))),
            ("PRECISION OPEN", str(gt.get("precision_open", "-"))),
            ("RECALL OPEN", str(gt.get("recall_open", "-"))),
        ], cols=4))
        parts.append("")

    parts.append(console.section("REKAP WORKER"))
    parts.append(_final_worker_table(master, summary))
    parts.append("")

    failures = summary.get("failures") or []
    if failures:
        parts.append(console.section(f"FAULT TOLERANCE ({len(failures)} kejadian)"))
        rows = []
        for f in failures:
            rows.append([
                str(f.get("worker_id", "?")),
                str(f.get("reason", "?")),
                _fmt_duration(f.get("detection_s")),
                _fmt_duration(f.get("recovery_s")) if f.get("recovery_s") is not None else "-",
                str(f.get("requeued_tasks", 0)),
                str(f.get("failed_tasks", 0)),
            ])
        narrow = console.width < 80
        headers = ["WORKER", "SEBAB", "DETEKSI"]
        aligns = ["l", "l", "r"]
        mins = [8, 8, 8]
        if not narrow:
            headers.append("PEMULIHAN")
            aligns.append("r")
            mins.append(9)
        headers.append("REQUEUE")
        aligns.append("r")
        mins.append(7)
        if not narrow:
            headers.append("GAGAL")
            aligns.append("r")
            mins.append(5)
        if narrow:
            rows = [[r[0], r[1], r[2], r[4]] for r in rows]
        parts.append(console.table(headers, rows, aligns=aligns, min_widths=mins))
        parts.append("")

    out_dir = Path(str(getattr(master, "results_dir", "results")))
    parts.append(console.panel("HASIL DISIMPAN", [
        str(out_dir / "results.json"),
        str(out_dir / "results.csv"),
        str(out_dir / "events.csv"),
        str(out_dir / "heartbeats.csv"),
        str(out_dir / "summary.json"),
    ]))
    return "\n".join(parts)


def _final_worker_table(master, summary):
    stats = summary.get("worker_stats") or {}
    sys_stats = summary.get("sys_stats") or {}
    live = {}
    with master.lock:
        for wid, worker in master.workers.items():
            live[wid] = {
                "hostname": worker.get("hostname", "?"),
                "ip": worker.get("addr")[0] if worker.get("addr") else "?",
            }
    wide = console.width >= 120
    very_narrow = console.width < 80
    headers = ["Worker ID", "Perangkat", "IP"]
    aligns = ["l", "l", "l"]
    mins = [8, 10, 15]
    if not very_narrow:
        headers.append("Diterima")
        aligns.append("r")
        mins.append(8)
    headers.append("Selesai")
    aligns.append("r")
    mins.append(7)
    if not very_narrow:
        headers.append("CPU avg")
        aligns.append("r")
        mins.append(7)
    if wide:
        headers += ["CPU peak", "RAM avg", "RAM peak"]
        aligns += ["r", "r", "r"]
        mins += [8, 7, 7]
    rows = []
    for wid in sorted(stats, key=str):
        info = live.get(wid, {})
        item = stats.get(wid) or {}
        sysinfo = sys_stats.get(wid) or {}
        row = [
            wid,
            info.get("hostname", item.get("hostname", "?")),
            info.get("ip", item.get("ip", "?")),
        ]
        if not very_narrow:
            row.append(str(item.get("assigned", 0)))
        row.append(str(item.get("done", 0)))
        if not very_narrow:
            row.append(str(sysinfo.get("cpu_avg", "-")))
        if wide:
            row += [str(sysinfo.get("cpu_peak", "-")),
                    str(sysinfo.get("mem_avg", "-")),
                    str(sysinfo.get("mem_peak", "-"))]
        rows.append(row)
    if not rows:
        for wid, info in sorted(live.items()):
            row = [wid, info["hostname"], info["ip"]]
            if not very_narrow:
                row += ["-"]
            row += ["-"]
            if not very_narrow:
                row += ["-"]
            if wide:
                row += ["-", "-", "-"]
            rows.append(row)
    if not rows:
        return console.panel("WORKER", ["Tidak ada worker yang terlibat."])
    return console.table(headers, rows, aligns=aligns, min_widths=mins)
