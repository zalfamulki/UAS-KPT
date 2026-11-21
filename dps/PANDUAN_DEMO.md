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
4. Perintah `list` / `pilih` / `all` / `keluar` **diketik persis di TERMINAL B** — di tulisan `perintah>` milik Master — bukan di jendela baru.

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
👀 `Master 0.0.0.0:5000 | mode=dynamic | 8 task (chunk=250) | total 2000 port`,
diikuti tulisan bantuan `[perintah master] list | pilih ...` dan dashboard tiap 2 detik.
⛔ biarkan menyala. **Master sedang menunggu worker masuk — ini normal, bukan macet.**

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
python worker/worker.py --master 192.168.1.10:5000
```
👀 di PC worker:
```
Node ini: NAMA-LAPTOP-MU (192.168.1.11) -> master 192.168.1.10:5000
Terhubung ke 192.168.1.10:5000 (mode=dynamic, proses=8, heartbeat=2.0s)
```
👀 di **TERMINAL B** (PC master) muncul:
```
Worker w-NAMA-LAPTOP [NAMA-LAPTOP @ 192.168.1.11] terhubung (cores=8, proses=8)
```
✅ tidak terhubung? langsung ke tabel "Kalau terasa macet" di Langkah 3.5.

### Langkah 2.2 — 📍 PC WORKER ke-2 s.d. ke-9 — ulangi
**TANPA PERINTAH BARU**: ulangi **persis** Langkah 2.1 di tiap PC worker
(perintahnya identik semua; IP master sama). Ulangi sampai 9 PC.

### Langkah 2.3 — 📍 TERMINAL B — pastikan semua sudah masuk
⌨️ (ketik di tulisan `perintah>` milik Master):
```
list
```
👀 9 baris berisi IP + nama laptop + proses + tugas + status tiap worker.

---

## BAGIAN 3 — SISTEM BERJALAN (hampir semuanya TANPA PERINTAH — cukup amati)

### Langkah 3.1 — 📍 semua terminal — TANPA PERINTAH, amati
👀 **TERMINAL B** tiap 2 detik menampilkan:
```
[dashboard] workers=9 (alive=9) | task: done=5 inflight=9 queued=3 failed=0 | port hasil=1500/2000 dup=0
[distribusi] SEMUA worker
  w-PC1   192.168.1.11   DESKTOP-ALFA   proses=8   tugas=2/2 cpu=35% | kerja
  w-PC2   192.168.1.12   DESKTOP-BETA   proses=8   tugas=1/1 cpu=32% | kerja
  ...
```
👀 di layar worker sesekali: `Task t00003 selesai (250 port, 3.12 s)`

### Langkah 3.2 — 📍 TERMINAL B — demo pilihan distribusi (opsional, bagus untuk video)
⌨️ ketik di tulisan `perintah>`:
```
pilih 192.168.1.11
```
(ganti IP dengan laptop yang mau kamu pilih — boleh juga nama laptop, mis. `pilih DESKTOP-ALFA`)
👀 muncul `[distribusi] hanya ke 1 worker: ...` + pengingat cara kembali, dan
dashboard berubah:
```
[distribusi] hanya ke: 192.168.1.11
[hint] ada 3 tugas antre — kalau terasa macet, ketik 'all' atau 'pilih' worker lain
  w-PC1   ... | kerja
  w-PC2   ... | menunggu (tidak dipilih)
```
👀 di laptop yang **tidak** dipilih muncul pesan jelas (bukan diam):
```
[menunggu tugas] Master sedang memilih worker lain untuk distribusi — laptop ini sengaja idle, bukan macet. (Di terminal master bisa ketik 'all' atau 'pilih <nama-mu>')
```

### Langkah 3.3 — 📍 TERMINAL B — kembalikan ke semua worker
⌨️:
```
all
```
👀 `[distribusi] kembali ke SEMUA worker` — semua worker langsung kerja lagi.

### Langkah 3.4 — 📍 semua terminal — TANPA PERINTAH — selesai otomatis
👀 **TERMINAL B**: `Semua task DONE/FAILED -> sistem selesai` → Master menyuruh
semua worker pulang (SHUTDOWN), worker **berhenti sendiri**, lalu hasil tersimpan
di folder `results\`:
- `results.json` / `results.csv` — status tiap port
- `events.csv` — timeline: siapa daftar, siapa kerja apa, worker mati, requeue
- `heartbeats.csv` — catatan CPU/mem tiap worker
- `summary.json` — angka demo: waktu eksekusi, throughput, distribusi tugas,
  **IP + nama laptop tiap worker**, dan perbandingan dengan kunci jawaban
  (`matched` / `mismatched`)

### Langkah 3.5 — 📍 kapan pun ragu — cek status dulu, jangan panik
Semua keadaan "diam" punya pesan. Arti tiap status dan tindakannya:

| Yang terlihat | Artinya | Yang perlu dilakukan |
|---|---|---|
| Worker: `[menunggu tugas] Master sedang memilih worker lain...` | laptop sengaja tidak dipilih (mode `pilih` aktif) | di TERMINAL B ketik `all`, atau `pilih` nama laptop itu |
| Worker: `[menunggu tugas] Antrean kosong / semua task sedang dikerjakan worker lain...` | normal — tugas sedang dipegang worker lain | tidak perlu apa-apa, otomatis lanjut |
| TERMINAL B: status `menunggu (tidak dipilih)` | sama dengan baris pertama di atas | ketik `all` |
| TERMINAL B: `[hint] ada N tugas antre...` | ada tugas menunggu di mode `pilih` | ketik `all` atau `pilih` worker lain |
| TERMINAL B: `MATI` di baris worker | koneksi putus / proses worker ditutup | tugas otomatis di-requeue; jalankan lagi Langkah 2.1 di PC itu |
| TERMINAL B: `failed=N` naik | 1 tugas sudah 3x gagal | cek jaringan/target, lalu ulangi run |

Ragu? **ketik `list` di TERMINAL B dulu** sebelum mengambil tindakan.

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
