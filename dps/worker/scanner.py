"""Engine scan TCP connect (rancangan 3.1, 4.2, 4.4).

Status port mengikuti konvensi Nmap:
- open     : connect_ex == 0 (layanan menerima koneksi)
- closed   : koneksi ditolak (ECONNREFUSED / WSAECONNREFUSED 10061)
- filtered : tidak ada jawaban (timeout, unreachable, dsb.)

Socket ditutup segera setiap scan untuk menghindari kehabisan file
descriptor / ephemeral port (tabel risiko, bagian 15).

Fungsi berada di level modul agar picklable oleh multiprocessing.Pool
(Windows memakai metode spawn).
"""

import errno
import socket

# Kode error "koneksi ditolak" lintas platform (Linux: 111, Windows: 10061)
CLOSED_ERRNOS = frozenset({errno.ECONNREFUSED, 111, 10061})


def scan_port(host, port, timeout):
    """Scan satu port dengan TCP connect. Return dict {port, status}."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        err = sock.connect_ex((host, port))
        if err == 0:
            status = "open"
        elif err in CLOSED_ERRNOS:
            status = "closed"
        else:
            status = "filtered"
    except socket.timeout:
        status = "filtered"
    except OSError as e:
        status = "closed" if (e.errno in CLOSED_ERRNOS) else "filtered"
    finally:
        sock.close()
    return {"port": port, "status": status}


def scan_range(host, start, end, timeout):
    """Scan rentang port secara sequential (dipakai baseline T1)."""
    return [scan_port(host, p, timeout) for p in range(start, end + 1)]
