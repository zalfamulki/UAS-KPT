"""Protokol komunikasi Master-Worker: JSON satu pesan per baris di atas TCP
(rancangan bagian 4.5).

Setiap pesan adalah objek JSON yang diakhiri '\\n'. Tipe pesan dan field
wajibnya didefinisikan di sini dan divalidasi di kedua sisi agar format
salah terdeteksi cepat, bukan menggantung koneksi.

Ukuran pesan dibatasi MAX_MSG_BYTES untuk menolak input tak wajar.
"""

import json
import threading

MAX_MSG_BYTES = 1_000_000  # 1 MB - cukup untuk hasil satu chunk ratusan port

# Tipe pesan (tabel 4.5 rancangan)
REGISTER = "REGISTER"
REGISTER_ACK = "REGISTER_ACK"
TASK_REQUEST = "TASK_REQUEST"
TASK = "TASK"
NO_TASK = "NO_TASK"
SHUTDOWN = "SHUTDOWN"
RESULT = "RESULT"
HEARTBEAT = "HEARTBEAT"

# Alasan opsional pada NO_TASK — agar pengguna Worker tidak bingung kenapa
# laptopnya diam (ditampilkan di log Worker, bukan sekadar diam tanpa pesan).
NO_TASK_FILTER = "filter"        # worker tidak termasuk pilihan distribusi master
NO_TASK_QUEUE_EMPTY = "queue_empty"  # antrean kosong / semua task sedang dikerjakan worker lain
NO_TASK_NOT_STARTED = "not_started"  # master belum menekan "Mulai pemindaian"

# Field wajib per tipe pesan
REQUIRED_FIELDS = {
    REGISTER: {"type", "worker_id", "cpu_cores", "hostname", "processes"},
    REGISTER_ACK: {"type", "heartbeat_interval", "scan_timeout", "mode"},
    TASK_REQUEST: {"type", "worker_id"},
    TASK: {"type", "task_id", "host", "port_start", "port_end", "timeout", "attempt"},
    NO_TASK: {"type"},
    SHUTDOWN: {"type", "reason"},
    RESULT: {"type", "worker_id", "task_id", "attempt", "results", "duration"},
    HEARTBEAT: {"type", "worker_id", "cpu", "mem", "current_task"},
}


def make_msg(msg_type, **fields):
    """Bangun pesan sekaligus validasi strukturnya."""
    msg = {"type": msg_type}
    msg.update(fields)
    return validate(msg)


def validate(msg):
    """Validasi struktur pesan; raise ValueError bila tidak sah."""
    if not isinstance(msg, dict):
        raise ValueError("Pesan bukan objek JSON")
    mtype = msg.get("type")
    if mtype not in REQUIRED_FIELDS:
        raise ValueError(f"Tipe pesan tak dikenal: {mtype!r}")
    missing = REQUIRED_FIELDS[mtype] - msg.keys()
    if missing:
        raise ValueError(f"Field kurang pada {mtype}: {sorted(missing)}")
    return msg


class MessageConnection:
    """Pembungkus socket TCP untuk kirim/terima pesan JSON per baris.

    - recv() memakai buffer internal, aman bila beberapa pesan datang
      menumpuk dalam satu paket TCP.
    - recv() dipanggil dari SATU thread saja.
    - send() thread-safe (dipakai bersama thread heartbeat di Worker).
    """

    def __init__(self, sock):
        self.sock = sock
        self._buf = bytearray()
        self._send_lock = threading.Lock()

    def send(self, msg):
        data = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
        if len(data) > MAX_MSG_BYTES:
            raise ValueError(f"Pesan terlalu besar ({len(data)} byte)")
        with self._send_lock:
            self.sock.sendall(data)

    def recv(self):
        while True:
            idx = self._buf.find(b"\n")
            if idx != -1:
                line = bytes(self._buf[:idx])
                del self._buf[: idx + 1]
                return validate(json.loads(line.decode("utf-8")))
            if len(self._buf) > MAX_MSG_BYTES:
                raise ValueError("Pesan melebihi batas ukuran")
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("Koneksi ditutup oleh lawan")
            self._buf += chunk

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
