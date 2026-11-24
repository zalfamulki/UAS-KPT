# DPS — Distributed Port Scanner (UAS KPT, Tema 14)

Sistem **Master–Worker** untuk port scanning TCP connect dengan task
decomposition (chunk), multiprocessing per Worker, dynamic load balancing
(pull-based), fault tolerance (heartbeat, requeue, retry, dedupe), serta
pengukuran performa T1–T6.

> ⚠️ **Etika (bagian 2 rancangan):** hanya scan host **milik sendiri** atau yang
> **diizinkan eksplisit** (lihat `allowlist.txt`). Master menolak target di luar
> allowlist. Akses ilegal ke sistem orang lain dapat dipidana (UU ITE).

> 📺 **Untuk demo/presentasi**: ikuti panduan langkah demi langkah di
> [`PANDUAN_DEMO.md`](PANDUAN_DEMO.md) — termasuk naskah video 5 menit, peta
> kewajiban soal → bukti demo, dan penjelasan fungsi tiap modul.

## Prasyarat

- Python **≥ 3.8** di semua node — <https://www.python.org> (saat instal di Windows, centang *Add python.exe to PATH*).
- Instal dependensi di **semua node** (Master, Worker, Target):

  ```
  pip install -r requirements.txt
  ```

  `psutil` wajib di Worker untuk metrik CPU/Memory (7.3); matplotlib/pandas hanya untuk grafik.

## Struktur

```
dps/
├── config.json        # konfigurasi (port, timeout, chunk, heartbeat) — semua [USULAN], kalibrasi!
├── allowlist.txt      # target yang diizinkan (wajib milik sendiri)
├── targets.txt        # daftar target scan: "host port_start port_end"
├── common/            # protokol TCP/JSON per baris + utilitas
├── target/            # simulator target + helper firewall (port filtered)
├── worker/            # scan engine (TCP connect), multiprocessing Pool, heartbeat
├── master/            # scheduler (dynamic/static), fault monitor, results, metrics, dashboard
├── bench/             # T1–T6 + grafik
└── results/           # CSV, JSON, grafik PNG, log (dibuat otomatis)
```

## Menjalankan cepat (1 PC, 3 terminal)

**Terminal 1 — Target** (buat ground truth lalu jalankan listener):

```
python target/target_sim.py --generate --host 127.0.0.1 --start 1 --end 2000 --open-ratio 0.08 --filtered-ratio 0 --seed 42
python target/target_sim.py --serve --gt target/ground_truth.json
```

**Terminal 2 — Master:**

```
python master/master.py --targets targets.txt --gt target/ground_truth.json
```

Master menampilkan **menu statis**: layar TIDAK diulang-ulang saat menganggur,
hanya digambar ulang ketika keadaan berubah (Worker masuk/mati, pemindaian
dimulai, distribusi diubah) atau saat menu dipilih. Saat pertama dibuka
pemindaian **belum dimulai** — hubungkan dulu semua Worker, lalu pilih `[1]`.

| Menu | Fungsi |
|---|---|
| `1` | **Mulai pemindaian**. Saat berjalan membuka **monitor live**; setelah selesai menampilkan ringkasan. |
| `2` | Status ringkas: progres tugas/port, antrean, aktivitas terakhir |
| `3` | Tabel semua Worker: nomor, Worker ID, **nama laptop (hostname)**, **IP**, tugas yang sedang dikerjakan, progres, CPU/RAM, status (`kerja` / `menunggu` / `MATI`) |
| `4` | Atur **distribusi**: `a`/`all` = semua Worker, atau ketik nomor/nama/IP/Worker ID untuk memilih sebagian |
| `5` | Bantuan dan penjelasan istilah |
| `0` | Hentikan Master dengan rapi (hasil seadanya tetap disimpan) |

Monitor live dapat ditutup dengan `Enter`/`Q` untuk kembali ke menu. Setelah
semua tugas selesai, Master dan Worker tetap hidup sampai Anda memilih `0`
atau menekan `Ctrl+C` di Master.

Perintah teks juga bisa diketik langsung, mis. `pilih 192.168.1.11`,
`pilih DESKTOP-XYZ`, `pilih w1 w2`, `all`, `list`, `status`, `keluar`.

Tabel Worker menampilkan **tugas aktif tiap worker** sehingga terlihat siapa
mengerjakan apa; pada mode `pilih`, Worker yang tidak dipilih diberi status
`menunggu (tidak dipilih)` agar tidak terlihat macet. IP/hostname tiap worker
ikut tersimpan di `summary.json` → dipakai untuk tabel Konfigurasi Node di
BAB III. Di sisi Worker, keadaan menganggur juga dijelaskan (`[menunggu] ...`
beserta alasannya).

Mode non-interaktif (stdout dialihkan ke file, mis. benchmark) otomatis
melewati menu dan langsung memulai pemindaian; paksa dengan `--no-ui`
(log sederhana) atau `--ui` (paksa tampilan menu).

**Terminal 3.. — Worker** (satu perintah per node; ulangi sesuai jumlah worker):

```
python worker/worker.py --master 127.0.0.1:5000
```

Saat semua task berstatus DONE/FAILED, Master menampilkan status selesai dan
kembali menunggu di menu. Worker tetap terhubung dalam keadaan idle. Pilih `0`
atau tekan `Ctrl+C` di Master untuk mengirim SHUTDOWN ke Worker dan menyimpan
`results/results.json`, `results.csv`, `events.csv`, `heartbeats.csv`, serta
`summary.json`. Hasil otomatis dibandingkan dengan ground truth
(matched/mismatched, precision/recall status open).

## Benchmark T1–T6

```
python bench/run_sequential.py --gt target/ground_truth.json        # T1 (jalankan pertama)
python bench/run_local_parallel.py                                  # T2
python bench/run_experiments.py --test all --repeat 1               # T3–T6 (uji cepat; laporan pakai --repeat 3)
python bench/plot_results.py                                        # grafik PNG
```

Catatan T3–T6: **target simulator harus sudah berjalan** (Terminal 1 di atas).
Untuk pengujian multi-PC, target bisa dijalankan di PC terpisah.

## Kalibrasi beban kerja (rancangan 6.2 — WAJIB sebelum uji final)

Baseline sequential harus berjalan **beberapa menit** agar efek paralel
terlihat. Cara menaikkan beban:

1. Perbesar rentang port di `targets.txt` (mis. `1 65535` atau beberapa target).
2. Tambah proporsi port **filtered** (paling memakan waktu — timeout):
   generate ulang GT dengan `--filtered-ratio 0.4` lalu pasang firewall DROP:

   ```
   python target/firewall_filtered.py --add     # run-as-admin (Windows); --remove untuk bersih-bersih
   ```

3. Naikkan `scan_timeout` di `config.json` bila perlu.

Tanpa aturan firewall, port `filtered` berperilaku seperti `closed` (fallback —
dokumentasikan sebagai keterbatasan di BAB III/IV). GT memakai seed, jadi
ground truth identik di semua mode uji.

## Uji 10 node fisik (rancangan 5.1)

1. Tentukan 1 PC sebagai **Master**; catat IP-nya (`ipconfig`). Izinkan port
   Master di firewall Master:

   ```
   netsh advfirewall firewall add rule name="DPS-master" dir=in action=allow protocol=TCP localport=5000
   ```

2. Jalankan Target (boleh di Master atau PC terpisah; idealnya bukan di node
   yang CPU-nya diukur — catat sebagai keterbatasan bila menumpang di Master):

   ```
   python target/target_sim.py --serve --gt target/ground_truth.json
   ```

3. Di **tiap PC Worker** (checklist onboarding 5 menit/node, rancangan 5.1):
   - [ ] Python ≥3.8 terinstal (`python --version`)
   - [ ] Salin folder `dps/` + `pip install -r requirements.txt`
   - [ ] `python worker/worker.py --master <IP_MASTER>:5000`
   - [ ] Worker muncul di menu Master (`[3]` tabel Worker)

4. Di Master:

   ```
   python master/master.py --targets targets.txt --gt target/ground_truth.json
   ```

5. Mode static (pembanding T4) memerlukan jumlah worker eksak:

   ```
   python master/master.py --mode static --expected-workers 9
   ```

6. Semua PC harus di satu jaringan (switch/router/hotspot). Ukur beban final
   dulu di 1 PC (kalibrasi), supaya sesi 10 node efisien.

## Troubleshooting

| Gejala | Sebab umum | Solusi |
|---|---|---|
| Worker tidak terhubung | firewall blokir port 5000 / beda jaringan / IP salah | tambah rule firewall di Master (di atas), cek `ping`, cek IP |
| Worker hilang lalu requeue | heartbeat timeout (6 s default) vs jaringan lambat | naikkan `heartbeat_interval`/`heartbeat_timeout` di `config.json` |
| Mismatch ground truth pada port filtered | aturan firewall belum dipasang | jalankan `firewall_filtered.py --add` (admin) atau catat fallback |
| Hasil duplikat tinggi | worker lambat, task selesai setelah di-requeue | wajar (idempotensi bekerja); cek `events.csv` |
| Speedup kecil | beban I/O-bound terlalu ringan; semua port closed cepat | kalibrasi: perbanyak port filtered, perbesar rentang (6.2) |
| Port "closed" terdeteksi "filtered" di laporan | jaringan/PC memblokir koneksi tanpa RST (firewall DROP ketat, sandbox) | sesuaikan GT: generate dengan `--filtered-ratio` sesuai perilaku jaringan, atau uji di jaringan lab yang normal |
| Port layanan OS muncul "open" padahal GT "filtered" | layanan Windows asli (mis. RPC 135, SMB 445) listening di rentang uji | pilih rentang bebas layanan OS (cek `netstat -ano | findstr LISTENING`), atau catat sebagai keterbatasan |
| Pool tidak jalan di Windows | entry point tanpa guard | semua skrip sudah pakai `if __name__ == "__main__"` — jangan hapus |
