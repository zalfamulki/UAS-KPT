"""Entry point Master (rancangan bagian 4.2, 4.5, 4.6, 4.7).

Tanggung jawab Master: menerima koneksi Worker (thread per koneksi),
memecah target menjadi task (chunk), membagikan via pull/static, mengumpulkan
hasil, memantau heartbeat + requeue, mencatat metrik, dan menampilkan
menu/tabel CLI.

Tampilan terminal:
- Interaktif (stdout terminal): menu statis. Master TIDAK menulis dashboard
  berulang saat menganggur; layar diperbarui hanya saat keadaan berubah
  (worker masuk/mati, mulai, distribusi) atau saat menu dipilih.
- Non-interaktif (mis. benchmark, stdout ke file): tanpa menu/dashboard,
  hanya log ringkas + summary.json.

Windows: jalankan dengan `python master/master.py --targets targets.txt`.
"""

import argparse
import json
import logging
import re
import socket
import sys
import threading
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.protocol import (HEARTBEAT, NO_TASK, NO_TASK_FILTER, NO_TASK_NOT_STARTED,
                             NO_TASK_QUEUE_EMPTY, REGISTER, REGISTER_ACK, RESULT,
                             SHUTDOWN, TASK, TASK_REQUEST, MessageConnection, make_msg)
from common.ui import console
from common.utils import (generate_tasks, load_config, read_allowlist, read_targets,
                          setup_logger, total_ports)
from master import dashboard
from master.fault_monitor import FaultMonitor
from master.metrics import MetricsLogger
from master.results import ResultsStore, compare_ground_truth
from master.scheduler import Scheduler

log = setup_logger("master")


def _detect_local_ip():
    """Perkirakan IP LAN Master untuk ditampilkan pada panduan worker."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))  # tidak mengirim paket; hanya pilih rute
            return sock.getsockname()[0]
        finally:
            sock.close()
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


class Master:
    def __init__(self, cfg, targets_path, allowlist_path, overrides, interactive=False):
        # Validasi allowlist (bagian 2: tolak target yang tidak diizinkan)
        allowed = read_allowlist(allowlist_path)
        targets = read_targets(targets_path)
        rejected = [t[0] for t in targets if t[0].lower() not in allowed]
        if rejected:
            raise SystemExit(f"Target tidak terdaftar di allowlist.txt - DITOLAK: {rejected}")

        self.mode = overrides.get("mode", cfg["mode"])
        self.chunk_size = overrides.get("chunk_size", cfg["chunk_size"])
        self.scan_timeout = overrides.get("scan_timeout", cfg["scan_timeout"])
        tasks = generate_tasks(targets, self.chunk_size, self.scan_timeout)
        self.scheduler = Scheduler(tasks, mode=self.mode,
                                   expected_workers=overrides.get("expected_workers"),
                                   retry_limit=cfg["retry_limit"])
        self.results = ResultsStore()
        self.metrics = MetricsLogger()
        self.total_ports = total_ports(tasks)

        self.bind_host = overrides.get("host", cfg["master_host"])
        self.port = overrides.get("port", cfg["master_port"])
        self.hb_interval = cfg["heartbeat_interval"]
        self.hb_timeout = cfg["heartbeat_timeout"]
        self.results_dir = overrides.get("results_dir", cfg["results_dir"])
        self.gt_path = overrides.get("gt")

        # UI: mode menu hanya jika terminal interaktif (atau dipaksa --ui).
        self.ui_enabled = bool(interactive)
        # Pada mode menu, tugas baru dikirim setelah pengguna memilih
        # "Mulai pemindaian"; mode benchmark tetap otomatis.
        self.started = not self.ui_enabled
        self.scan_finished = False
        self.ui_closing = False
        self.activity = deque(maxlen=8)
        self.display_host = self.bind_host
        if self.bind_host in ("0.0.0.0", "", "::"):
            self.display_host = _detect_local_ip()

        self.workers = {}  # worker_id -> {conn, addr, hostname, processes, last_seen,
                           #                alive, cpu, mem, assigned, done, task, idle_reason}
        self.distribution = {"mode": "all", "tokens": [], "worker_ids": set()}
        self.lock = threading.RLock()
        self.done_event = threading.Event()
        self.listen_sock = None

    # ---------- siklus hidup ----------
    def start(self):
        if self.scheduler.is_complete():
            if self.ui_enabled:
                self._mark_scan_finished()
            else:
                log.warning("Tidak ada task - selesai segera.")
                self.done_event.set()
        self.listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listen_sock.bind((self.bind_host, self.port))
        self.listen_sock.listen(16)
        self.listen_sock.settimeout(1.0)

        if self.ui_enabled:
            self._add_activity(f"Master siap di {self.bind_host}:{self.port}", "info")
            if not self.started:
                self._add_activity("Menunggu worker terhubung ...", "info")
        else:
            log.info("Master %s:%d | mode=%s | %d task (chunk=%d) | total %d port",
                     self.bind_host, self.port, self.mode, len(self.scheduler.table),
                     self.chunk_size, self.total_ports)

        threading.Thread(target=self._accept_loop, daemon=True).start()
        FaultMonitor(self).start()
        if self.ui_enabled:
            threading.Thread(target=self._menu_loop, daemon=True).start()

        try:
            self.done_event.wait()
        except KeyboardInterrupt:
            if self.ui_enabled:
                self._add_activity("Dihentikan pengguna — menyimpan hasil seadanya.", "warn")
            else:
                log.warning("Dihentikan pengguna - mematikan Worker lalu menyimpan hasil parsial.")
            self.done_event.set()
        self.ui_closing = True
        time.sleep(0.5)  # beri kesempatan SHUTDOWN terkirim
        self._shutdown_workers()
        return self._finish()

    # ---------- jaringan ----------
    def _accept_loop(self):
        while not self.done_event.is_set():
            try:
                raw_conn, addr = self.listen_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handler, args=(raw_conn, addr), daemon=True).start()

    def _handler(self, raw_conn, addr):
        conn = MessageConnection(raw_conn)
        wid = None
        try:
            first = conn.recv()
            if first["type"] != REGISTER:
                raise ValueError("Pesan pertama bukan REGISTER")
            wid = self._register(conn, addr, first)
            conn.send(make_msg(REGISTER_ACK, heartbeat_interval=self.hb_interval,
                               scan_timeout=self.scan_timeout, mode=self.mode))
            while True:
                msg = conn.recv()
                mtype = msg["type"]
                if mtype == TASK_REQUEST:
                    if not self.started:
                        conn.send(make_msg(NO_TASK, reason=NO_TASK_NOT_STARTED))
                        self._set_current_task(wid, None)
                        self._set_idle(wid, "not_started")
                    elif self._distribution_allows(wid):
                        task = self.scheduler.assign_next(wid)
                        if task:
                            self.metrics.event("task_assign", worker_id=wid,
                                               task_id=task["task_id"])
                            self._bump(wid, "assigned")
                            self._set_current_task(wid, task)
                            self._set_idle(wid, None)
                            conn.send(make_msg(TASK, task_id=task["task_id"],
                                               host=task["host"],
                                               port_start=task["port_start"],
                                               port_end=task["port_end"],
                                               timeout=task["timeout"],
                                               attempt=task["attempt"]))
                        else:
                            conn.send(make_msg(NO_TASK, reason=NO_TASK_QUEUE_EMPTY))
                            self._set_current_task(wid, None)
                            self._set_idle(wid, "empty")
                    else:
                        # worker tidak termasuk pilihan distribusi saat ini — beri
                        # tahu alasannya supaya penggunanya tidak bingung laptopnya diam
                        conn.send(make_msg(NO_TASK, reason=NO_TASK_FILTER))
                        self._set_current_task(wid, None)
                        self._set_idle(wid, "filtered")
                    self._touch(wid)
                elif mtype == HEARTBEAT:
                    self._touch(wid, cpu=msg.get("cpu"), mem=msg.get("mem"))
                    self.metrics.heartbeat(wid, msg.get("cpu"), msg.get("mem"))
                elif mtype == RESULT:
                    self._on_result(wid, msg)
                elif mtype == REGISTER:  # re-REGISTER dari worker yang reconnect
                    wid = self._register(conn, addr, msg)
                    conn.send(make_msg(REGISTER_ACK, heartbeat_interval=self.hb_interval,
                                       scan_timeout=self.scan_timeout, mode=self.mode))
        except (ConnectionError, ValueError, OSError) as e:
            if wid:
                if not self.ui_enabled:
                    log.info("Koneksi Worker %s terputus: %s", wid, e)
                self.mark_worker_dead(wid, reason="connection_lost", dead_conn=conn)
        finally:
            conn.close()

    def _register(self, conn, addr, msg):
        wid = msg["worker_id"]
        with self.lock:
            prev = self.workers.get(wid)
            if prev and prev["alive"]:
                note = f"Worker {wid} re-REGISTER dengan koneksi baru"
            else:
                note = None
            self.workers[wid] = {"conn": conn, "addr": addr,
                                 "cpu_cores": msg["cpu_cores"],
                                 "hostname": msg["hostname"],
                                 "processes": msg["processes"],
                                 "last_seen": time.time(),
                                 "alive": True, "cpu": None, "mem": None,
                                 "assigned": 0, "done": 0, "task": None,
                                 "idle_reason": None}
            self.metrics.event("register", worker_id=wid,
                               detail={"hostname": msg["hostname"], "ip": addr[0],
                                       "cores": msg["cpu_cores"],
                                       "processes": msg["processes"]})
        if self.mode == "static":
            self.scheduler.register_static_partition(wid)
        if note:
            self._add_activity(note, "info")
        self._add_activity(
            f"+ {msg['hostname']} ({addr[0]}) terhubung · {msg['processes']} proses", "join")
        if not self.ui_enabled:
            log.info("Worker %s [%s @ %s] terhubung (cores=%s, proses=%s)",
                     wid, msg["hostname"], addr[0], msg["cpu_cores"], msg["processes"])
        return wid

    def _touch(self, wid, cpu=None, mem=None):
        with self.lock:
            w = self.workers.get(wid)
            if w:
                w["last_seen"] = time.time()
                if cpu is not None:
                    w["cpu"] = cpu
                if mem is not None:
                    w["mem"] = mem

    def _bump(self, wid, key):
        with self.lock:
            w = self.workers.get(wid)
            if w:
                w[key] = w.get(key, 0) + 1

    def _set_idle(self, wid, code):
        """Catat status 'sedang tidak memegang tugas' (None = sedang kerja)."""
        with self.lock:
            w = self.workers.get(wid)
            if w:
                w["idle_reason"] = code

    def _set_current_task(self, wid, task):
        """Simpan tugas yang sedang dipegang worker untuk ditampilkan di tabel."""
        with self.lock:
            w = self.workers.get(wid)
            if not w:
                return
            if task is None:
                w["task"] = None
            else:
                w["task"] = {"task_id": task["task_id"], "host": task["host"],
                             "port_start": task["port_start"],
                             "port_end": task["port_end"],
                             "started": time.time()}

    # ---------- distribusi: semua vs worker terpilih ----------
    def _find_workers(self, token):
        """Cocokkan token dengan worker_id / hostname (nama laptop) / IP."""
        t = token.lower()
        out = set()
        with self.lock:
            for wid, w in self.workers.items():
                ip = w["addr"][0].lower() if w.get("addr") else ""
                if t in wid.lower() or t in w["hostname"].lower() or t in ip:
                    out.add(wid)
        return out

    def _distribution_allows(self, wid):
        """True bila worker ini boleh menerima tugas menurut pilihan distribusi."""
        with self.lock:
            dist = self.distribution
            if dist["mode"] == "all":
                return True
            if wid in dist["worker_ids"]:
                return True
            w = self.workers.get(wid)
            if not w:
                return False
            ip = w["addr"][0].lower() if w.get("addr") else ""
            host = w["hostname"].lower()
            for tok in dist["tokens"]:
                if tok in wid.lower() or tok in host or tok in ip:
                    return True  # worker baru yang cocok dengan pilihan ikut dikerjakan
            return False

    def _set_distribution_to(self, tokens):
        """Batasi distribusi hanya ke worker yang cocok dengan token (IP/nama/id)."""
        with self.lock:
            matched = set()
            for tok in tokens:
                matched |= self._find_workers(tok)
            if not matched:
                self._notice(f"Tidak ada worker yang cocok dengan "
                             f"'{' '.join(tokens)}' - pengaturan tidak berubah", "warn")
                return False
            self.distribution = {"mode": "pilih",
                                 "tokens": [t.lower() for t in tokens],
                                 "worker_ids": matched}
            names = "; ".join(f"{self.workers[wid]['hostname']} ({wid})"
                              for wid in sorted(matched))
        self._notice(f"Distribusi hanya ke {len(matched)} worker: {names}", "dist")
        return True

    def _set_distribution_all(self):
        with self.lock:
            self.distribution = {"mode": "all", "tokens": [], "worker_ids": set()}
        self._notice("Distribusi kembali ke SEMUA worker", "dist")

    # ---------- menu interaktif ----------
    def _add_activity(self, text, kind="info"):
        """Simpan aktivitas singkat untuk panel di layar (tanpa spam stdout)."""
        with self.lock:
            self.activity.append((time.time(), text, kind))

    def _notice(self, text, kind="info"):
        self._add_activity(text, kind)
        if not self.ui_enabled:
            print(f"[master] {text}", flush=True)

    def _menu_signature(self):
        """Keadaan yang memicu gambar ulang layar menu.

        Sengaja TIDAK memasukkan jumlah tugas/CPU: menu harus tetap statis
        saat worker sedang bekerja; progres dilihat lewat monitor/status.
        """
        with self.lock:
            rows = tuple(sorted(
                (wid, bool(w.get("alive")), str(w.get("hostname", "")),
                 str(w.get("addr")))
                for wid, w in self.workers.items()))
            dist = (self.distribution.get("mode", "all"),
                    tuple(self.distribution.get("tokens") or []))
        return self.started, self.scan_finished, dist, rows

    def _menu_loop(self):
        if console.char_mode:
            self._menu_loop_keys()
        else:
            self._menu_loop_input()

    def _menu_loop_input(self):
        """Fallback bila menu dipaksa saat input bukan terminal interaktif."""
        while not self.done_event.is_set() and not self.ui_closing:
            console.clear()
            console.write(dashboard.render_home(self))
            try:
                line = input("\n  Pilih menu > ")
            except (EOFError, OSError):
                return
            if self.done_event.is_set() or self.ui_closing:
                return
            self._handle_menu_input(line)

    def _menu_loop_keys(self):
        """Menu dengan pembacaan tombol: layar hanya digambar ulang saat
        keadaan berubah, jadi tidak ada output berulang saat menganggur."""
        prompt = "\n  " + console.style("Pilih menu > ", "bold", "cyan")
        console.clear()
        console.write(dashboard.render_home(self))
        console.write(prompt, end="")
        buf = ""
        last_sig = self._menu_signature()
        while not self.done_event.is_set() and not self.ui_closing:
            sig = self._menu_signature()
            if not buf and sig != last_sig:
                console.clear()
                console.write(dashboard.render_home(self))
                console.write(prompt, end="")
                last_sig = sig
            key = console.read_key(0.3)
            if key is None:
                continue
            if key in ("\r", "\n"):
                console.write("")
                line = buf.strip()
                buf = ""
                self._handle_menu_input(line)
                if self.done_event.is_set() or self.ui_closing:
                    return
                console.clear()
                console.write(dashboard.render_home(self))
                console.write(prompt, end="")
                last_sig = self._menu_signature()
            elif key in ("\x08", "\x7f"):
                if buf:
                    buf = buf[:-1]
                    console.write("\b \b", end="")
            elif key == "\x03":  # Ctrl+C
                self.done_event.set()
                return
            elif key == "\x1b":
                continue
            elif len(key) == 1 and key.isprintable():
                buf += key
                console.write(key, end="")

    def _handle_menu_input(self, line):
        line = (line or "").strip()
        if not line:
            return
        parts = line.split()
        cmd = parts[0].lower()

        if cmd in ("0", "keluar", "quit", "exit", "stop"):
            self._add_activity("Permintaan berhenti — menyimpan hasil ...", "warn")
            self.done_event.set()
        elif cmd == "1":
            if not self.started:
                self._start_scan()
            elif self.scan_finished:
                self._show_status(full=False)
            else:
                self._monitor_live()
        elif cmd in ("2", "status", "ringkas", "list", "ls", "daftar"):
            self._show_status(full=False)
        elif cmd in ("3", "worker", "workers"):
            self._show_status(full=True)
        elif cmd in ("4", "distribusi", "pilih", "filter", "target"):
            if len(parts) > 1:
                self._set_distribution_to(parts[1:])
            else:
                self._distribution_menu()
        elif cmd in ("5", "bantuan", "help", "?"):
            self._show_help()
        elif cmd in ("all", "semua"):
            self._set_distribution_all()
        elif cmd in ("refresh", "r"):
            return
        else:
            self._notice(f"Perintah '{line}' tidak dikenal - pilih nomor menu 0-5.", "warn")

    def _start_scan(self):
        if self.scan_finished:
            self._show_status(full=False)
            return
        with self.lock:
            self.started = True
            has_workers = any(w.get("alive") for w in self.workers.values())
        self._add_activity("Pemindaian DIMULAI — tugas dikirim ke worker.", "start")
        if not self.ui_enabled:
            log.info("Pemindaian dimulai.")
        if has_workers:
            self._monitor_live()
        else:
            self._add_activity("Belum ada worker; tugas menunggu worker masuk.", "warn")

    def _show_status(self, full=False):
        console.clear()
        console.write(dashboard.render_status(self, full=full))
        if console.is_tty:
            console.pause("Tekan Enter untuk kembali ke menu")

    def _show_help(self):
        console.clear()
        console.write(dashboard.render_help(self))
        if console.is_tty:
            console.pause("Tekan Enter untuk kembali ke menu")

    def _distribution_menu(self):
        console.clear()
        console.write(dashboard.render_distribution(self))
        try:
            line = input("\n  Pilih (a / nomor / nama / IP / 0) > ").strip()
        except (EOFError, OSError):
            return
        if not line or line == "0":
            return
        if line.lower() in ("a", "all", "semua"):
            self._set_distribution_all()
            return
        tokens = [t for t in re.split(r"[,\s]+", line) if t]
        with self.lock:
            order = sorted(self.workers,
                           key=lambda wid: (str(self.workers[wid].get("hostname", "")),
                                            str(wid)))
        mapped, invalid = [], []
        for token in tokens:
            if token.isdigit():
                idx = int(token)
                if 1 <= idx <= len(order):
                    mapped.append(order[idx - 1])
                else:
                    invalid.append(token)
            else:
                mapped.append(token)
        if invalid:
            self._notice(f"Nomor worker tidak ada: {', '.join(invalid)}", "warn")
        if mapped:
            self._set_distribution_to(mapped)

    def _monitor_live(self):
        """Dashboard refresh di tempat (bukan scroll). Keluar: Enter / Q."""
        if not self.ui_enabled:
            return
        if not console.is_tty:
            # Mode --ui dengan output dialihkan: satu snapshot agar log tetap
            # bisa dibaca dan skrip tidak menggantung.
            console.write(dashboard.render_live(self))
            return
        while (not self.done_event.is_set() and not self.ui_closing
               and not self.scan_finished):
            console.clear()
            console.write(dashboard.render_live(self))
            console.write("\n  " + console.style(
                "Tekan Enter / Q untuk kembali ke menu", "dim"))
            key = console.read_key(1.0)
            if key in ("\r", "\n", "q", "Q", "0", "\x1b"):
                break
            if key == "\x03":
                self.done_event.set()
                break
        console.clear()

    # ---------- hasil ----------
    def _on_result(self, wid, msg):
        rec = self.scheduler.table.get(msg["task_id"])
        if rec is None:
            log.warning("RESULT task tak dikenal %s dari %s", msg["task_id"], wid)
            return
        accepted = self.results.submit(rec, wid, msg["results"], msg["duration"])
        if accepted:
            self.scheduler.mark_done(msg["task_id"])
            self.metrics.event("task_done", worker_id=wid, task_id=msg["task_id"])
            self.metrics.mark_last_result()
            self._bump(wid, "done")
        else:
            self.metrics.event("task_duplicate", worker_id=wid, task_id=msg["task_id"])
            log.info("Hasil duplikat task %s dari %s dibuang (idempotensi)",
                     msg["task_id"], wid)
        self._set_current_task(wid, None)
        self._mark_scan_finished()

    def _mark_scan_finished(self):
        """Tandai pekerjaan selesai; sesi interaktif tetap hidup sampai dipilih keluar."""
        if not self.scheduler.is_complete():
            return False
        with self.lock:
            if self.scan_finished:
                return True
            self.scan_finished = True
            self.started = True
        self._add_activity(
            "Semua tugas selesai. Worker tetap terhubung; pilih [0] untuk menutup sesi.",
            "complete",
        )
        if self.ui_enabled:
            return True
        log.info("Semua task DONE/FAILED -> sistem selesai.")
        self.done_event.set()
        return True

    # ---------- fault tolerance ----------
    def mark_worker_dead(self, wid, reason, dead_conn=None):
        """Satu pintu: tandai mati, requeue in-flight, catat metrik.
        Dipanggil FaultMonitor (heartbeat timeout) atau handler (koneksi putus);
        hanya pemicu pertama yang efektif."""
        with self.lock:
            w = self.workers.get(wid)
            if not w or not w["alive"]:
                return
            if dead_conn is not None and w["conn"] is not dead_conn:
                return  # koneksi lama mati, worker sudah re-REGISTER lewat koneksi baru
            w["alive"] = False
            w["task"] = None
            last_seen = w["last_seen"]
            hostname = w.get("hostname", wid)
            ip = w["addr"][0] if w.get("addr") else "?"
            w["conn"].close()
        requeued, failed = self.scheduler.requeue_for(wid)
        self.metrics.event("worker_down", worker_id=wid,
                           detail={"reason": reason, "requeued": requeued,
                                   "failed": failed, "last_seen": last_seen})
        for tid in requeued:
            self.metrics.event("requeue", worker_id=wid, task_id=tid)
        detail = f"{hostname} ({ip}) terputus"
        if requeued or failed:
            detail += f" — {len(requeued)} tugas di-requeue, {len(failed)} gagal"
        self._add_activity(detail, "down")
        if requeued or failed:
            if not self.ui_enabled:
                log.warning("Worker %s mati (%s): requeue=%d, failed=%d",
                            wid, reason, len(requeued), len(failed))
        self._mark_scan_finished()

    def _shutdown_workers(self):
        for wid, w in list(self.workers.items()):
            if w["alive"]:
                try:
                    w["conn"].send(make_msg(SHUTDOWN, reason="master_stopping"))
                except (OSError, ConnectionError):
                    pass

    # ---------- penutupan ----------
    def _finish(self):
        summary = self.metrics.build_summary(self.total_ports, self.scheduler.stats(),
                                             self.results.counts(), self.mode,
                                             len(self.scheduler.table))
        if self.gt_path:
            gt = json.loads(Path(self.gt_path).read_text(encoding="utf-8"))
            summary["ground_truth"] = compare_ground_truth(self.results.port_status, gt)
        out = Path(self.results_dir)
        results_file = self.results.export(out)
        summary_file = self.metrics.save(out, summary)
        if self.ui_enabled:
            console.clear()
            console.write(dashboard.render_final(self, summary))
        else:
            log.info("Exec time=%.3fs | throughput=%.1f port/s | dup=%d | imbalance=%s",
                     summary["execution_time_s"] or -1,
                     summary["throughput_ports_per_s"] or -1,
                     self.results.duplicates, summary["load_imbalance_ratio"])
            for f in summary["failures"]:
                log.info("  worker_down %s (%s): detection=%.2fs recovery=%s requeued=%d",
                         f["worker_id"], f["reason"], f["detection_s"],
                         f["recovery_s"], f["requeued_tasks"])
            log.info("Hasil: %s | ringkasan: %s", results_file, summary_file)
        return summary


def main():
    ap = argparse.ArgumentParser(description="Master DPS (jalankan di node Master)")
    ap.add_argument("--config", default=None, help="path config.json")
    ap.add_argument("--targets", default="targets.txt")
    ap.add_argument("--allowlist", default="allowlist.txt")
    ap.add_argument("--host", default=None, help="alamat bind (default dari config)")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--mode", choices=["dynamic", "static"], default=None)
    ap.add_argument("--expected-workers", type=int, default=None,
                    help="jumlah worker yang diharapkan (partisi static; wajib akurat)")
    ap.add_argument("--chunk-size", type=int, default=None)
    ap.add_argument("--scan-timeout", type=float, default=None)
    ap.add_argument("--gt", default=None, help="ground_truth.json untuk verifikasi hasil")
    ap.add_argument("--results-dir", default=None)
    ap.add_argument("--ui", action="store_true",
                    help="paksa tampilan menu interaktif (walau input dialihkan)")
    ap.add_argument("--no-ui", action="store_true",
                    help="paksa mode log sederhana tanpa menu (untuk skrip/benchmark)")
    args = ap.parse_args()

    if args.ui and args.no_ui:
        ap.error("--ui dan --no-ui tidak bisa dipakai bersamaan")
    interactive = args.ui or (not args.no_ui
                             and sys.stdin.isatty() and sys.stdout.isatty())
    if interactive:
        # Log INFO akan mengacaukan layar menu; aktivitas penting tetap tampil
        # lewat panel aktivitas di layar.
        logging.getLogger("master").setLevel(logging.WARNING)
        logging.getLogger("fault").setLevel(logging.WARNING)

    cfg = load_config(args.config)
    overrides = {k: v for k, v in {
        "host": args.host, "port": args.port, "mode": args.mode,
        "expected_workers": args.expected_workers, "chunk_size": args.chunk_size,
        "scan_timeout": args.scan_timeout, "gt": args.gt,
        "results_dir": args.results_dir,
    }.items() if v is not None}

    try:
        master = Master(cfg, args.targets, args.allowlist, overrides,
                        interactive=interactive)
    except SystemExit as e:
        print(f"[DITOLAK] {e}")
        sys.exit(2)

    try:
        master.start()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
