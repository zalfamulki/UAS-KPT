# PANDUAN DEMO DPS — ikuti berurutan dari atas ke bawah

Panduan ini mengalir: kerjakan **Bagian 0 → 1 → 2 → 3 → (4) → (5) → 6** sesuai urutan,
jangan lompat. Setiap langkah berpola sama:

- **📍 DIMANA** — di PC apa dan di terminal mana perintah diketik
- **⌨️ PERINTAH** — tinggal salin-tempel (kalau tidak ada yang perlu diketik, tertulis **TANPA PERINTAH**)
- **👀 YANG MUNCUL** — tanda kalau berhasil

---

## PEMETAAN AWAL — siapa punya apa, di mana

| PC | Jumlah | Menjalankan | Terminal yang dipakai |
|---|---|---|---|
| **PC MASTER** (mis. laptop kamu) | 1 | Target ("PC korban") + Master ("otak") + benchmark | **A** (Target), **B** (Master), **C** (benchmark/ekstra) |
| **PC WORKER** | 9 | Worker ("tangan") | 1 terminal per PC |

**Aturan penting biar tidak bingung:**
1. **TERMINAL A, B, C** = 3 jendela cmd di PC MASTER yang kamu buka di Langkah 1.0. Nama-nama ini dipakai konsisten sampai bawah.
2. Di PC WORKER cukup 1 terminal per PC.
3. Terminal yang baru dibuka **wajib masuk folder program dulu** (Langkah 1.0) sebelum menjalankan perintah `python ...`.
4. Menu (`1`–`5`, `0`) dan perintah teks (`list` / `pilih` / `all` / `keluar`) **diketik persis di TERMINAL B** — di tulisan `Pilih menu >` milik Master — bukan di jendela baru.

---

## BAGIAN 0 — PERSIAPAN SEKALI (sebelum hari demo)

### Langkah 0.1 — 📍 SEMUA PC (master + 9 worker) — install Python
**TANPA PERINTAH**: download di <https://www.python.org>, saat instal centang
**Add python.exe to PATH** (kalau lupa, `python` tidak akan dikenali).
✅ Cek berhasil — ⌨️ di terminal mana pun:
```
python --version
```
👀 muncul `Python 3.x.x` → aman, lanjut.

### Langkah 0.2 — 📍 SEMUA PC — install dependensi program
⌨️ (dari dalam folder `dps` — cara masuk folder ada di Langkah 1.0):
```
pip install -r requirements.txt
```
👀 berakhir tanpa kata `error` (boleh banyak `Requirement already satisfied`).

### Langkah 0.3 — 📍 SEMUA PC — salin folder program
**TANPA PERINTAH**: salin folder `dps` ke tiap PC (flashdisk / clone repo).
Pastikan isinya ada folder `master`, `worker`, `target`, `bench` dan file `README.md`.

### Langkah 0.4 — 📍 PC MASTER — catat IP-nya
⌨️ (terminal mana pun):
```
ipconfig
```
👀 cari baris `IPv4 Address . . . : 192.168.x.x` pada adapter yang aktif (Wi-Fi/Ethernet).
✍️ **TANPA PERINTAH**: tulis IP itu di kertas. Ini `<IP_MASTER>` yang dipakai
seluruh panduan (contoh di bawah memakai `192.168.1.10` — ganti dengan milikmu).

### Langkah 0.5 — 📍 PC MASTER — izinkan port 5000 di firewall
⌨️:
```
netsh advfirewall firewall add rule name="DPS-master" dir=in action=allow protocol=TCP localport=5000
```
👀 tidak muncul `error` = berhasil (dibersihkan kembali di Langkah 6.2).

---

## BAGIAN 1 — AS MASTER (semua langkah di PC MASTER)

### Langkah 1.0 — 📍 PC MASTER — buka 3 terminal + masuk folder program
**TANPA PERINTAH untuk membuka**: Start → ketik `cmd` → Enter, **ulangi 3 kali**.
Sepakati sekarang: jendela ke-1 = **TERMINAL A (Target)**, ke-2 = **TERMINAL B (Master)**,
ke-3 = **TERMINAL C (benchmark/ekstra)**.

Lalu **di TIAP terminal** masuk folder program (wajib — tanpa ini semua perintah
`python ...` akan gagal "file tidak ditemukan"):
```
cd /d "D:\My Project\UAS KPT\dps"
```
👀 prompt berubah jadi `...\dps>` → lanjut.
(gunakan PowerShell/Git Bash? cukup `cd "D:\My Project\UAS KPT\dps"`)

### Langkah 1.1 — 📍 TERMINAL A — buat "kunci jawaban" target
⌨️:
```
python target/target_sim.py --generate --host 127.0.0.1 --start 1 --end 2000 --open-ratio 0.08 --filtered-ratio 0.4 --seed 42
```
👀 `Ground truth tersimpan: target\ground_truth.json (open=160 closed=1040 filtered=800)`
ℹ️ ini menetapkan port mana open/closed/filtered — nanti hasil scan dibandingkan
dengan ini untuk membuktikan sistem akurat. (Mau uji antar-PC? ganti
`--host 127.0.0.1` dengan IP PC target.)

### Langkah 1.2 — 📍 TERMINAL A — (opsional, perlu admin) blokir port "filtered"
**TANPA hak admin? LEWATKAN langkah ini** — catat sebagai keterbatasan di laporan.
Punya admin (buka cmd sebagai Administrator, lalu `cd` ke folder dps lagi):
```
python target/firewall_filtered.py --add
```
👀 deretan baris `OK : netsh advfirewall ...` (dihapus kembali di Langkah 6.2).

### Langkah 1.3 — 📍 TERMINAL A — jalankan Target
⌨️:
```
python target/target_sim.py --serve --gt target/ground_truth.json
```
👀 `Target 127.0.0.1 berjalan: 160 listener 'open' (rentang GT: [1, 2000])`
⛔ **TANPA PERINTAH LAGI di TERMINAL A** — biarkan menyala sampai demo tuntas.

### Langkah 1.4 — 📍 TERMINAL B — jalankan Master
⌨️:
```
python master/master.py --targets targets.txt --gt target/ground_truth.json
```
👀 Master menampilkan **banner + menu statis** (bukan baris log yang mengalir):
```
┌ DPS | DISTRIBUTED PORT SCANNER ──────────────────────┐
│ Mode dynamic | Bind 0.0.0.0:5000 | 8 tugas | 2000 port │
└──────────────────────────────────────────────────────┘
STATUS: SIAP - pemindaian belum dimulai. Pilih [1] untuk mengirim tugas.
```
diikuti tabel Worker (masih kosong), panel **AKTIVITAS TERAKHIR**, dan menu:

| Pilih | Fungsi |
|---|---|
| `1` | Mulai pemindaian (kalau sudah jalan: monitor live) |
| `2` | Status ringkas |
| `3` | Tabel semua Worker (nama laptop + IP + tugas aktif) |
| `4` | Atur distribusi (semua / pilih sebagian) |
| `5` | Bantuan |
| `0` | Keluar dan simpan hasil |

⛔ biarkan menyala. **Master sedang menunggu worker masuk — ini normal, bukan
macet.** Layar **tidak berkedip** dan **tidak mencetak apa pun** saat menganggur;
hanya berubah ketika ada Worker masuk/mati atau menu dipilih.
⚠️ **Jangan pilih `[1]` dulu** — tunggu Bagian 2 selesai (semua Worker masuk),
baru mulai pemindaian di Langkah 3.0.

> Varian kalau ditanya dosen — mode static (bagi rata di awal):
> ```
> python master/master.py --mode static --expected-workers 9
> ```

---

## BAGIAN 2 — AS WORKER (ulangi di SETIAP PC worker — perintahnya sama semua)

### Langkah 2.1 — 📍 PC WORKER ke-1 — masuk folder + jalankan worker
⌨️ (terminal baru di PC worker; **ganti `192.168.1.10` dengan `<IP_MASTER>` hasil Langkah 0.4**):
```
cd /d "D:\My Project\UAS KPT\dps"
python worker/worker.py --master 192.168.0.119:5000
```
👀 di PC worker (panel identitas + baris log):
```
+---------------- WORKER SIAP ----------------+
| Perangkat : NAMA-LAPTOP-MU (192.168.1.11)    |
| Master    : 192.168.1.10:5000                |
| Proses    : 8 - core logis 8                 |
+----------------------------------------------+
15:04:12  INFO    [koneksi] NAMA-LAPTOP-MU (192.168.1.11) -> master 192.168.1.10:5000
15:04:12  INFO    [ok] Terhubung ke 192.168.1.10:5000 | mode=dynamic | proses=8 | heartbeat=2.0s
```
👀 di **TERMINAL B** (PC master) layar langsung diperbarui: baris baru di panel
**AKTIVITAS TERAKHIR** + satu baris Worker di tabel (nama laptop + IP):
```
15:04:12  + NAMA-LAPTOP-MU (192.168.1.11) terhubung - 8 proses
...
| 1 | NAMA-LAPTOP-MU-1234 | NAMA-LAPTOP-MU | 192.168.1.11 | 8 | 0% | 0/0 | - | menunggu mulai |
```
✅ tidak terhubung? langsung ke tabel "Kalau terasa macet" di Langkah 3.5.

### Langkah 2.2 — 📍 PC WORKER ke-2 s.d. ke-9 — ulangi
**TANPA PERINTAH BARU**: ulangi **persis** Langkah 2.1 di tiap PC worker
(perintahnya identik semua; IP master sama). Ulangi sampai 9 PC.

### Langkah 2.3 — 📍 TERMINAL B — pastikan semua sudah masuk
⌨️ (ketik `3` di tulisan `Pilih menu >` milik Master, lalu tekan `Enter`):
```
3
```
👀 tabel **SEMUA WORKER** berisi 9 baris: nomor, Worker ID, **nama laptop
(hostname)**, **IP**, jumlah proses, CPU, tugas selesai, tugas aktif, status
(`menunggu mulai` karena pemindaian belum dimulai).
Tekan `Enter` untuk kembali ke menu. Setelah pemindaian berjalan, pilihan
`[1]` otomatis berubah menjadi **Monitor langsung**. Setelah semua tugas selesai,
Master kembali ke menu dan `[1]` menjadi **Lihat hasil**.

---

## BAGIAN 3 — SISTEM BERJALAN (hampir semuanya TANPA PERINTAH — cukup amati)

### Langkah 3.0 — 📍 TERMINAL B — mulai pemindaian
⌨️ (ketik `1` di `Pilih menu >`, lalu `Enter`):
```
1
```
👀 Master langsung masuk **monitor live** (refresh 1 detik di tempat): kartu
metrik (worker aktif, tugas, port, waktu, throughput, distribusi), progres port,
dan tabel worker. Status di tabel berubah menjadi `bekerja` dengan kolom
**Task aktif** berisi tugas yang sedang dipegang tiap laptop — jadi terlihat
jelas siapa mengerjakan apa. Tekan `Enter` atau `Q` kapan pun untuk kembali ke
menu; pemindaian tetap berjalan.

### Langkah 3.1 — 📍 semua terminal — TANPA PERINTAH, amati
👀 **TERMINAL B** (monitor live) kira-kira seperti ini:
```
MONITOR LANGSUNG                                   15:04:20 · refresh 1 dtk
+--------------+--------------+--------------+--------------+--------------+--------------+
| WORKER       | TUGAS        | PORT         | WAKTU        | THROUGHPUT   | DISTRIBUSI   |
| 9/9 aktif    | 5/8 selesai  | 1500/2000    | 12.4 s       | 121.0 port/s | SEMUA        |
| 9 bekerja    | 3 antre      |              |              |              |              |
+--------------+--------------+--------------+--------------+--------------+--------------+
  Progres port  ##########################....  (1500/2000)

  WORKER (9)
  +---+--------------+-------------+-----------------+--------+-----+-------+-------------+---------+
  | # | Perangkat    | IP          | Proses          | ...    |     | Tugas | Task aktif  | Status  |
  | 1 | DESKTOP-ALFA | 192.168.1.11| 8               |        |     | 2/2   | t00005 501-750 | bekerja |
  | 2 | DESKTOP-BETA | 192.168.1.12| 8               |        |     | 1/1   | t00006 751-1000| bekerja |
  ...
```
👀 di layar worker sesekali muncul baris log:
`15:04:25  INFO    [task] selesai t00003 | 250 port | 3.12 s (total 2 tugas / 500 port)`

### Langkah 3.2 — 📍 TERMINAL B — demo pilihan distribusi (opsional, bagus untuk video)
⌨️ tekan `Enter`/`Q` untuk kembali ke menu, lalu ketik `4` + `Enter`:
```
4
```
👀 muncul tabel **ATUR DISTRIBUSI TUGAS**. Ketik `a` (semua), nomor worker,
nama laptop, IP, atau Worker ID — misalnya:
```
1
```
👀 Master mencatat `Distribusi hanya ke 1 worker: ...`, lalu tabel worker
menampilkan kolom **Distribusi**: `ya` untuk yang dipilih, `-` untuk yang lain,
dengan status `tidak dipilih`.
👀 di laptop yang **tidak** dipilih muncul pesan jelas (bukan diam):
```
15:04:40  INFO    [menunggu] Master sedang membatasi distribusi ke worker lain. Di menu
                  Master pilih [4] Atur distribusi -> 'a' (semua) atau nama/IP laptop ini.
                  Laptop ini sengaja idle, bukan macet.
```

### Langkah 3.3 — 📍 TERMINAL B — kembalikan ke semua worker
⌨️ ketik `all` (atau `4` lalu `a`):
```
all
```
👀 `Distribusi kembali ke SEMUA worker` — semua worker langsung kerja lagi.

### Langkah 3.4 — 📍 semua terminal — pemindaian selesai
👀 **TERMINAL B**: status berubah menjadi **SELESAI** dan Master kembali ke
menu. Worker tetap terhubung dan menunggu, jadi terminal worker tidak ditutup.
Pilih `0` atau tekan `Ctrl+C` di TERMINAL B bila ingin mengakhiri sesi. Master
kemudian mengirim SHUTDOWN dan menyimpan hasil di folder `results\`:
- `results.json` / `results.csv` — status tiap port
- `events.csv` — timeline: siapa daftar, siapa kerja apa, worker mati, requeue
- `heartbeats.csv` — catatan CPU/mem tiap worker
- `summary.json` — angka demo: waktu eksekusi, throughput, distribusi tugas,
  **IP + nama laptop tiap worker**, dan perbandingan dengan kunci jawaban
  (`matched` / `mismatched`)

👀 Setelah memilih `0` atau menekan `Ctrl+C`, semua Worker menerima SHUTDOWN
dari Master dan berhenti sendiri.

### Langkah 3.5 — 📍 kapan pun ragu — cek status dulu, jangan panik
Semua keadaan "diam" punya pesan. Arti tiap status dan tindakannya:

| Yang terlihat | Artinya | Yang perlu dilakukan |
|---|---|---|
| Worker: `[menunggu] Master belum memulai pemindaian...` | Master masih di menu, `[1]` belum ditekan | di TERMINAL B pilih `1` |
| Worker: `[menunggu] Master sedang membatasi distribusi ke worker lain...` | laptop sengaja tidak dipilih (mode pilih aktif) | di TERMINAL B ketik `all`, atau `4` lalu pilih laptop itu |
| Worker: `[menunggu] Antrean kosong / semua tugas sedang dikerjakan worker lain...` | normal — tugas sedang dipegang worker lain | tidak perlu apa-apa, otomatis lanjut |
| TERMINAL B: status `tidak dipilih` | sama dengan baris kedua di atas | ketik `all` atau `4` lalu pilih worker itu |
| TERMINAL B: `[info] N tugas antre...` di monitor | ada tugas menunggu di mode pilih | tekan `Enter`, lalu `all` |
| TERMINAL B: `MATI` di baris worker | koneksi putus / proses worker ditutup | tugas otomatis di-requeue; jalankan lagi Langkah 2.1 di PC itu |
| TERMINAL B: kartu `GAGAL` naik | 1 tugas sudah 3x gagal | cek jaringan/target, lalu ulangi run |

Ragu? **tekan `2` (Status ringkas) atau `3` (Daftar worker lengkap) di TERMINAL B**
sebelum mengambil tindakan.

---

## BAGIAN 4 — DEMO FAULT TOLERANCE (favorit dosen — bisa diulang)

Kalau Bagian 3 sudah selesai (master & worker sudah berhenti), jalankan ulang
Langkah 1.4 + Bagian 2 — perintahnya sama persis. Lalu:

### Langkah 4.1 — 📍 salah satu PC WORKER — matikan worker di tengah jalan
**TANPA PERINTAH**: di terminal worker itu tekan `Ctrl+C`
(atau tutup terminal / matikan Wi-Fi PC-nya).

### Langkah 4.2 — 📍 TERMINAL B — TANPA PERINTAH, amati penyelamatan
👀 `Worker w-XXX mati (connection_lost): requeue=2, failed=0`
→ tugas si worker mati dikembalikan ke antrean dan dikerjakan worker lain.
👀 opsional — ⌨️ `list` → worker itu tampil dengan status `MATI`.

### Langkah 4.3 — 📍 semua terminal — TANPA PERINTAH — hasil tetap lengkap
👀 setelah selesai, buka `results\summary.json` → ground truth
`matched` = total port dan `mismatched = 0` → bukti fault tolerance bekerja.

---

## BAGIAN 5 — BENCHMARK T1–T6 + GRAFIK (wajib untuk laporan; untuk video cukup cuplikan)

Syarat: **TERMINAL A (Target) masih menyala**, Master dari Bagian 3 sudah selesai
(kalau masih jalan, ketik `keluar` di TERMINAL B), dan terminal worker sudah ditutup.
📍 **Semua perintah di PC MASTER — TERMINAL C** (yang sudah `cd` ke folder dps).

### Langkah 5.1 — 📍 TERMINAL C — T1 baseline (1 proses, tanpa jaringan)
```
python bench/run_sequential.py --gt target/ground_truth.json
```
### Langkah 5.2 — 📍 TERMINAL C — T2 multiprocessing 1 PC
```
python bench/run_local_parallel.py
```
### Langkah 5.3 — 📍 TERMINAL C — T3–T6 terdistribusi (demo cepat `--repeat 1`; laporan `--repeat 3`)
```
python bench/run_experiments.py --test all --repeat 1
```
### Langkah 5.4 — 📍 TERMINAL C — grafik PNG
```
python bench/plot_results.py
```
👀 5 grafik di `results\`: `t2_speedup.png`, `t3_throughput.png`,
`t4_load_balance.png`, `t5_recovery.png`, `t6_scalability.png`.

---

## BAGIAN 6 — SETELAH DEMO: rapikan

### Langkah 6.1 — 📍 semua PC WORKER — TANPA PERINTAH
Tutup terminal worker (semua sudah berhenti sendiri sejak Bagian 3.4).

### Langkah 6.2 — 📍 PC MASTER — bersihkan aturan firewall
```
netsh advfirewall firewall delete rule name="DPS-master"
python target/firewall_filtered.py --remove
```
(kalimat kedua hanya kalau Langkah 1.2 pernah dijalankan)
 Folder `results\` **jangan dihapus** — itu bukti pengujian.

---

## BAGIAN 7 — NASKAH VIDEO 5 MENIT

| Waktu | Yang direkam |
|---|---|
| 0:00–0:30 | Judul, anggota, tema 14, tujuan singkat |
| 0:30–1:15 | **Sapukan kamera ke 10 PC fisik** + label IP tiap PC (syarat dosen!) |
| 1:15–2:30 | Langkah 1.3–1.4 dan 2.1: master jalan, 9 worker masuk satu-satu, dashboard jalan |
| 2:30–3:15 | Load balancing: `list`/dashboard + `summary.json` (jumlah tugas per laptop) |
| 3:15–4:15 | Bagian 4: matikan 1 worker → requeue → hasil tetap lengkap |
| 4:15–5:00 | Ringkasan angka: speedup/efficiency dari `t6_scalability.png`, tutup |

---

## BAGIAN 8 — REFERENSI FUNGSI (biar tahu tiap file itu buat apa)

### `common/` — bahasa komunikasi & alat bantu
| File/fungsi | Gunanya |
|---|---|
| `protocol.py` → `make_msg`, `validate` | bikin & cek format pesan JSON (REGISTER, TASK, RESULT, HEARTBEAT, dll.) biar salah format langsung ketahuan |
| `protocol.py` → `MessageConnection` | pembungkus socket TCP: kirim/terima pesan per baris, aman dari pesan yang numpuk |
| `utils.py` → `generate_tasks` | **memecah** rentang port jadi tugas kecil (task decomposition) |
| `utils.py` → `load_config`, `read_targets`, `read_allowlist` | baca file konfigurasi, daftar target, dan daftar IP yang boleh dipindai |

### `target/` — PC korban buatan sendiri
| File/fungsi | Gunanya |
|---|---|
| `target_sim.py` → `generate_ground_truth` | bikin kunci jawaban open/closed/filtered (ber-seed, jadi sama terus di semua uji) |
| `target_sim.py` → `ListenerFarm` / `serve` | buka listener di port "open" — scanner yang connect akan melihatnya open |
| `firewall_filtered.py` → `run_netsh` | blokir port filtered lewat firewall Windows (perlu admin) |

### `worker/` — tangan-tangannya
| File/fungsi | Gunanya |
|---|---|
| `scanner.py` → `scan_port` | cek 1 port pakai TCP connect: berhasil=open, ditolak=closed, nunggu sampai timeout=filtered |
| `pool.py` → `ScanPool.scan_task` | kerjakan 1 tugas pakai **banyak proses sekaligus** (multiprocessing) |
| `sys_monitor.py` → `SysMonitor.sample` | ambil angka CPU & RAM untuk laporan |
| `worker.py` → `_heartbeat_loop` | kirim sinyal "aku masih hidup" tiap 2 detik + angka CPU/RAM |
| `worker.py` → `_report_idle` | saat menganggur, tampilkan alasan ("menunggu dipilih"/"antrean kosong") — biar tidak dianggap macet |
| `worker.py` → `run` | kalau koneksi putus, coba sambung lagi sendiri (auto-reconnect) |

### `master/` — otaknya
| File/fungsi | Gunanya |
|---|---|
| `master.py` → `_register` / `_accept_loop` | terima daftar worker baru yang masuk |
| `scheduler.py` → `assign_next` | kasih 1 tugas ke worker yang minta (worker cepat = dapat banyak) |
| `scheduler.py` → `register_static_partition` | mode static: bagi rata di awal (pembanding) |
| `scheduler.py` → `requeue_for` | tugas milik worker mati dikembalikan ke antrean (maks 3x coba) |
| `fault_monitor.py` → `check` | cari worker yang tidak kirim kabar > 6 detik → dianggap mati |
| `results.py` → `submit` / `compare_ground_truth` | terima hasil (buang yang dobel), cocokkan dengan kunci jawaban |
| `metrics.py` → `build_summary` / `compute_failures` | hitung waktu eksekusi, throughput, waktu deteksi & pemulihan |
| `master.py` → `_dashboard` / `_command_loop` | baris status tiap 2 detik + perintah `list/pilih/all/keluar` |

### `bench/` — alat uji
| Skrip | Gunanya |
|---|---|
| `run_sequential.py` | T1: tanpa paralel, tanpa jaringan — pembanding dasar |
| `run_local_parallel.py` | T2: multiprocessing di 1 PC |
| `run_experiments.py` | T3–T6: jalanin master+worker otomatis, matiin worker (T5), hitung scalability |
| `plot_results.py` | bikin 5 grafik PNG |

---

## BAGIAN 9 — CHECKLIST SEBELUM REKAM VIDEO

- [ ] Semua PC sudah: Python + `pip install -r requirements.txt` + folder `dps/`
- [ ] Label kertas berisi IP ditempel di tiap PC (buat adegan 0:30–1:15)
- [ ] Uji coba penuh dari folder bersih pernah dilakukan (bukan cuma "katanya jalan")
- [ ] Beban target sudah dikalibrasi: scan sequential butuh beberapa menit
      (naikkan rentang port / filtered-ratio / timeout kalau masih cepat banget)
- [ ] Rekam layar + kamera sekaligus; dashboard master ikut terlihat
