"""Helper aturan firewall untuk port 'filtered' (Windows, perlu Administrator).

Membaca ground truth, mengelompokkan port 'filtered' menjadi rentang, lalu
menambah/menghapus aturan inbound BLOCK via netsh (DROP) sehingga koneksi TCP
ke port tersebut mengalami timeout = status 'filtered' (rancangan 3.1/4.2).

Tanpa aturan ini, port 'filtered' berperilaku seperti 'closed' — gunakan
fallback ini hanya bila tidak ada hak admin, dan dokumentasikan keterbatasannya
di BAB III/IV laporan.
"""

import argparse
import ctypes
import json
import subprocess
import sys
from pathlib import Path

RULE_PREFIX = "DPS-filtered"


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except AttributeError:
        return False  # bukan Windows


def filtered_ranges(gt):
    """Kelompokkan port filtered yang berurutan menjadi rentang [a, b]."""
    ports = sorted(int(p) for p, st in gt["statuses"].items() if st == "filtered")
    ranges = []
    for p in ports:
        if ranges and p == ranges[-1][1] + 1:
            ranges[-1][1] = p
        else:
            ranges.append([p, p])
    return ranges


def run_netsh(netsh_args):
    cmd = ["netsh", "advfirewall", "firewall"] + netsh_args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"  GAGAL : {' '.join(cmd)}")
        print(f"          {proc.stderr.strip() or proc.stdout.strip()}")
        return False
    print(f"  OK    : {' '.join(cmd)}")
    return True


def main():
    ap = argparse.ArgumentParser(description="Pasang/hapus aturan firewall DROP untuk port filtered (run-as-admin)")
    ap.add_argument("--gt", default="target/ground_truth.json", help="file ground truth sumber port filtered")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--add", action="store_true", help="tambah aturan block")
    g.add_argument("--remove", action="store_true", help="hapus aturan block (bersih-bersih)")
    args = ap.parse_args()

    if sys.platform != "win32":
        print("Bukan Windows: gunakan firewall OS lain (mis. iptables DROP) atau fallback open/closed.")
        sys.exit(1)
    if not is_admin():
        print("Harus dijalankan sebagai Administrator (klik kanan terminal -> Run as administrator).")
        sys.exit(1)

    gt = json.loads(Path(args.gt).read_text(encoding="utf-8"))
    ranges = filtered_ranges(gt)
    total = sum(b - a + 1 for a, b in ranges)
    action = "Menambah" if args.add else "Menghapus"
    print(f"{action} aturan untuk {total} port filtered dalam {len(ranges)} rentang aturan ...")

    ok = True
    for a, b in ranges:
        name = f"{RULE_PREFIX}-{a}-{b}"
        port_spec = f"{a}-{b}" if a != b else f"{a}"
        if args.add:
            ok &= run_netsh(["add", "rule", f"name={name}", "dir=in", "action=block",
                             "protocol=TCP", f"localport={port_spec}"])
        else:
            ok &= run_netsh(["delete", "rule", f"name={name}"])

    print("Selesai." + ("" if ok else " Ada yang gagal — periksa output di atas."))
    if not args.add:
        print("Catatan: aturan tidak ditemukan dianggap berhasil oleh netsh.")


if __name__ == "__main__":
    main()
