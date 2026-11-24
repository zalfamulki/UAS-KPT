"""Toolkit tampilan terminal (stdlib saja) untuk Master & Worker.

Tujuan: output tidak lagi berupa baris teks yang terus mengalir, tetapi
tabel berbingkai yang rapi, menu, dan panel status. Semua fungsi di sini
hanya mengurus teks (tidak menyentuh jaringan/scheduler), sehingga aman
dipakai di mode non-interaktif (stdout dialihkan ke file) — pada mode itu
warna/karakter bingkai otomatis dinonaktifkan.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import time
import unicodedata

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_ASCII_FALLBACK = str.maketrans({
    "·": "-", "—": "-", "–": "-", "…": "...", "→": "->", "←": "<-",
    "█": "#", "░": ".", "▶": ">", "✔": "ok", "✓": "ok", "✗": "x",
    "│": "|", "─": "-", "═": "=", "║": "|",
    "┌": "+", "┐": "+", "└": "+", "┘": "+", "├": "+", "┤": "+",
    "┬": "+", "┴": "+", "┼": "+", "╔": "+", "╗": "+", "╚": "+", "╝": "+",
})

RESET = "\x1b[0m"
_STYLES = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "white": "37",
    "gray": "90",
}


def _enable_windows_ansi():
    """Aktifkan Virtual Terminal Processing di konsol Windows (Win10+)."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        enable_vt = 0x0004
        return bool(kernel32.SetConsoleMode(handle, mode.value | enable_vt))
    except Exception:
        return False


class Console:
    """Pembungkus output terminal: warna, lebar, bingkai, tabel, key reader."""

    def __init__(self):
        self.is_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
        stdin_tty = bool(getattr(sys.stdin, "isatty", lambda: False)())
        # Mode tombol dipakai hanya bila kedua stream benar-benar terminal.
        # Pada POSIX read_key masuk sebentar ke raw mode agar menu tetap bisa
        # memperbarui tabel worker saat input sedang menunggu.
        self.char_mode = self.is_tty and stdin_tty
        self.ansi = False
        if self.is_tty and not os.environ.get("NO_COLOR"):
            self.ansi = _enable_windows_ansi() if os.name == "nt" else True
        try:
            self.width = shutil.get_terminal_size((110, 30)).columns
        except OSError:
            self.width = 110
        self.width = max(40, int(self.width))
        self.unicode = self.is_tty and self._can_encode("─│┌┐└┘├┤┬┴┼█░…")
        if self.unicode:
            self.g = {
                "h": "─", "v": "│",
                "tl": "┌", "tr": "┐", "bl": "└", "br": "┘",
                "tj": "┬", "bj": "┴", "lj": "├", "rj": "┤", "x": "┼",
                "btl": "╔", "btr": "╗", "bbl": "╚", "bbr": "╝",
                "bh": "═", "bv": "║",
                "full": "█", "empty": "░", "dot": "·", "ellipsis": "…",
            }
        else:
            self.g = {
                "h": "-", "v": "|",
                "tl": "+", "tr": "+", "bl": "+", "br": "+",
                "tj": "+", "bj": "+", "lj": "+", "rj": "+", "x": "+",
                "btl": "+", "btr": "+", "bbl": "+", "bbr": "+",
                "bh": "=", "bv": "|",
                "full": "#", "empty": ".", "dot": "-", "ellipsis": "..",
            }
        import threading

        self._lock = threading.RLock()

    # ---------- dasar ----------
    @staticmethod
    def _can_encode(text):
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        try:
            text.encode(enc)
            return True
        except (UnicodeEncodeError, LookupError):
            return False

    def write(self, text="", end="\n"):
        """Tulis satu blok teks (thread-safe)."""
        if text is None:
            text = ""
        text = str(text)
        if not self.unicode:
            text = text.translate(_ASCII_FALLBACK)
        with self._lock:
            sys.stdout.write(text + end)
            sys.stdout.flush()

    def style(self, text, *names):
        if not self.ansi:
            return str(text)
        codes = [_STYLES[n] for n in names if n in _STYLES]
        if not codes:
            return str(text)
        return "\x1b[" + ";".join(codes) + "m" + str(text) + RESET

    @staticmethod
    def _strip_ansi(text):
        return _ANSI_RE.sub("", text)

    def visible_len(self, text):
        text = self._strip_ansi(str(text))
        total = 0
        for ch in text:
            total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        return total

    def truncate(self, text, width):
        """Potong teks sesuai lebar tampilan; warna hilang bila terpotong."""
        text = str(text)
        if self.visible_len(text) <= width:
            return text
        plain = self._strip_ansi(text)
        if width <= 1:
            return plain[:max(0, width)]
        mark = self.g["ellipsis"]
        mark_len = self.visible_len(mark)
        keep = max(0, width - mark_len)
        out = ""
        used = 0
        for ch in plain:
            w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
            if used + w > keep:
                break
            out += ch
            used += w
        return out + mark

    def pad(self, text, width, align="l"):
        text = str(text)
        gap = max(0, width - self.visible_len(text))
        if align == "r":
            return " " * gap + text
        if align == "c":
            left = gap // 2
            return " " * left + text + " " * (gap - left)
        return text + " " * gap

    def clear(self):
        """Bersihkan layar; no-op bila output bukan terminal (mis. ke file)."""
        if not self.is_tty:
            return
        if self.ansi:
            self.write("\x1b[H\x1b[2J", end="")
        else:
            os.system("cls" if os.name == "nt" else "clear")

    def clear_below(self):
        if self.is_tty and self.ansi:
            self.write("\x1b[H\x1b[J", end="")

    def line(self, char="─", width=None):
        return char * max(0, (width or self.width))

    # ---------- komponen ----------
    def section(self, title, width=None):
        width = min(width or (self.width - 2), max(30, self.width - 2))
        label = f" {title} "
        visible = self.visible_len(label)
        if visible >= width:
            return "  " + self.style(self.truncate(title, width), "bold", "cyan")
        body = self.g["h"] * (width - visible)
        return "  " + self.style(label + body, "cyan")

    def banner(self, title, subtitle=None, badge=None, indent=2):
        """Kotak judul ganda (double-line) selebar terminal (maks 78)."""
        inner = max(48, min(76, self.width - indent - 2))
        content = inner - 2  # ruang di dalam '║  ...  ║'

        def row(left, right=""):
            left = str(left)
            right = str(right)
            gap = content - self.visible_len(left) - self.visible_len(right)
            if gap < 1:
                left = self.truncate(left, max(1, content - self.visible_len(right) - 1))
                gap = max(1, content - self.visible_len(left) - self.visible_len(right))
            return (f"{self.g['bv']} {left}{' ' * gap}{right} {self.g['bv']}")

        lines = [self.g["btl"] + self.g["bh"] * (content + 2) + self.g["btr"]]
        lines.append(row(self.style(title, "bold", "white"),
                         self.style(badge, "bold", "yellow") if badge else ""))
        if subtitle:
            lines.append(row(self.style(subtitle, "dim")))
        lines.append(self.g["bbl"] + self.g["bh"] * (content + 2) + self.g["bbr"])
        pad = " " * indent
        return "\n".join(pad + self.style(ln, "cyan") if self.ansi else pad + ln
                         for ln in lines)

    def panel(self, title, lines, tone="cyan", indent=2):
        """Panel berbingkai tunggal dengan judul di baris pertama."""
        max_width = self.width - indent
        body = [str(x) for x in lines]
        inner = max(
            [self.visible_len(title) + 4] + [self.visible_len(x) + 2 for x in body]
        )
        # 4 = 2 border + 2 padding; inner harus muat di lebar terminal.
        inner = min(inner, max(20, max_width - 4))
        top = (self.g["tl"] + self.g["h"] * (inner + 2) + self.g["tr"])
        out = [self.style(top, tone)]
        head = f" {self.style(title, 'bold')} "
        out.append(self.g["v"] + self.pad(head, inner + 2) + self.g["v"])
        out.append(self.style(self.g["lj"] + self.g["h"] * (inner + 2) + self.g["rj"], tone))
        for ln in body:
            out.append(self.g["v"] + " " + self.pad(self.truncate(ln, inner), inner) + " " + self.g["v"])
        out.append(self.style(self.g["bl"] + self.g["h"] * (inner + 2) + self.g["br"], tone))
        pad = " " * indent
        return "\n".join(pad + ln for ln in out)

    def table(self, headers, rows, aligns=None, max_width=None, indent=2,
              min_widths=None, empty="(belum ada data)"):
        """Tabel berbingkai dengan lebar adaptif terhadap terminal."""
        headers = [str(h) for h in headers]
        n = len(headers)
        aligns = (list(aligns or []) + ["l"] * n)[:n]
        min_widths = (list(min_widths or []) + [3] * n)[:n]
        body = []
        for row in rows:
            row = [str(c) for c in row]
            row = (row + [""] * n)[:n]
            body.append(row)
        if not body:
            body = [[empty] + [""] * (n - 1)]

        widths = [max(self.visible_len(h), min_widths[i]) for i, h in enumerate(headers)]
        for row in body:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], self.visible_len(cell), min_widths[i])

        avail = max_width if max_width is not None else (self.width - indent)
        overhead = 3 * n + 1
        while sum(widths) + overhead > avail:
            candidates = [i for i in range(n) if widths[i] > min_widths[i]]
            if not candidates:
                break
            idx = max(candidates, key=lambda i: widths[i] - min_widths[i])
            widths[idx] -= 1

        g = self.g

        def border(left, join, right):
            return left + join.join(g["h"] * (w + 2) for w in widths) + right

        def row_line(cells, align_row, header=False):
            parts = []
            for i, cell in enumerate(cells):
                cell = self.truncate(cell, widths[i])
                text = self.pad(cell, widths[i], align_row[i])
                parts.append(" " + text + " ")
            line = g["v"] + g["v"].join(parts) + g["v"]
            return self.style(line, "bold") if header else line

        lines = [border(g["tl"], g["tj"], g["tr"]),
                 row_line(headers, ["c"] * n, header=True),
                 border(g["lj"], g["x"], g["rj"])]
        for row in body:
            lines.append(row_line(row, aligns))
        lines.append(border(g["bl"], g["bj"], g["br"]))
        pad = " " * indent
        return "\n".join(pad + ln for ln in lines)

    def kv_panel(self, items, cols=6, indent=2):
        """Deret kartu metrik (label di header, nilai di baris bawah)."""
        items = [(str(k), str(v)) for k, v in items]
        if not items:
            return ""
        out = []
        for start in range(0, len(items), cols):
            chunk = items[start:start + cols]
            out.append(self.table([k for k, _ in chunk], [[v for _, v in chunk]],
                                  aligns=["l"] * len(chunk), indent=indent,
                                  min_widths=[6] * len(chunk)))
        return "\n".join(out)

    def menu(self, items, indent=2):
        """Menu dua kolom: tombol + nama + keterangan."""
        rows = []
        for key, label, desc in items:
            rows.append([self.style(f"[{key}]", "bold", "yellow"),
                         self.style(label, "bold"), desc])
        return self.table(["PILIH", "MENU", "KETERANGAN"], rows,
                          aligns=["c", "l", "l"], indent=indent,
                          min_widths=[5, 12, 8])

    def progress(self, done, total, width=24):
        width = max(8, min(width, max(8, self.width - 40)))
        ratio = 0.0 if not total else max(0.0, min(1.0, done / total))
        filled = int(round(ratio * width))
        bar = self.g["full"] * filled + self.g["empty"] * (width - filled)
        color = "green" if ratio >= 1.0 else "cyan"
        return f"{self.style(bar, color)} {ratio * 100:5.1f}%"

    # ---------- input ----------
    def read_key(self, timeout=0.0):
        """Baca satu tombol tanpa Enter dari terminal interaktif."""
        if not self.is_tty:
            return None
        if os.name == "nt":
            import msvcrt

            deadline = time.monotonic() + max(0.0, timeout)
            while True:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch in ("\x00", "\xe0"):  # tombol fungsi/panah
                        if msvcrt.kbhit():
                            msvcrt.getwch()
                        continue
                    return ch
                if timeout and time.monotonic() >= deadline:
                    return None
                time.sleep(0.03)
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        previous = None
        try:
            previous = termios.tcgetattr(fd)
            tty.setraw(fd)
            ready, _, _ = select.select([fd], [], [], timeout)
            if not ready:
                return None
            return os.read(fd, 1).decode(getattr(sys.stdin, "encoding", None) or "utf-8",
                                         errors="replace")
        except (OSError, ValueError, termios.error):
            return None
        finally:
            if previous is not None:
                try:
                    termios.tcsetattr(fd, termios.TCSADRAIN, previous)
                except (OSError, termios.error):
                    pass

    def pause(self, prompt="Tekan Enter untuk kembali"):
        """Tunggu satu Enter; tidak menunggu bila output bukan terminal."""
        if not self.is_tty:
            return
        if not self.char_mode:
            try:
                input("\n  " + prompt + " ")
            except (EOFError, OSError):
                pass
            return
        self.write("")
        self.write("  " + self.style(prompt, "dim"), end="")
        while True:
            key = self.read_key(0.5)
            if key in ("\r", "\n", "q", "Q", "\x1b"):
                self.write("")
                return
            if key == "\x03":
                raise KeyboardInterrupt


console = Console()
