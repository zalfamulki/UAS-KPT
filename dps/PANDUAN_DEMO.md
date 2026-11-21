# PANDUAN DEMO DPS — dari nol sampai selesai

Cara pakai programnya untuk demo ke dosen / rekam video. Santai saja, intinya
program ini cuma punya **2 peran**:

- **PC MASTER** (1 PC) — "otak" sistem. Di sini juga dijalankan Target (PC palsu
  yang kita pindai sendiri, biar aman dan hasilnya bisa dicek kebenarannya).
- **PC WORKER** (9 PC) — "tangan-tangannya" yang mengerjakan scan. Di tiap PC
  worker cukup SATU perintah.

---

## PERSIAPAN (sekali saja, lakukan di SEMUA PC: master dan worker)

1. Install Python 3.8 ke atas — <https://www.python.org> (di Windows, centang
   *Add python.exe to PATH* biar bisa dipanggil dari mana saja).
2. Buka folder `dps/`, lalu ketik:
   ```
   pip install -r requirements.txt
   ```
   Isinya: `psutil` (untuk laporan CPU/mem), `matplotlib` + `pandas` (untuk grafik).
3. Salin folder `dps/` ke tiap PC (flashdisk / share / clone repo).
4. Cek singkat:
   - Semua PC satu jaringan (coba `ping` ke PC master).
   - Di PC master, catat IP-nya: `ipconfig` → lihat IPv4 Address (mis. `192.168.1.10`).

---

## LANGKAH 1 — AS MASTER (di 1 PC saja)

Semua perintah diketik dari dalam folder `dps/`. Buka 2 terminal di PC ini
(nanti keduanya terpakai).

### 1a. Buat "kunci jawaban" target

```
python target/target_sim.py --generate --host 127.0.0.1 --start 1 --end 2000 --open-ratio 0.08 --filtered-ratio 0.4 --seed 42
```

Apa ini? Kita menetapkan dulu port mana yang **open** (ada layanan), **closed**
(tidak ada), dan **filtered** (diblok). Nanti hasil scan di bandingkan dengan
daftar ini — kalau cocok semua, berarti sistem kita akurat.

Yang muncul kira-kira:
```
Ground truth tersimpan: target\ground_truth.json (open=160 closed=1040 filtered=800)
```

> - Mau uji di jaringan? ganti `--host 127.0.0.1` dengan IP PC target (mis.
>   `192.168.1.20`).
> - Tanpa hak admin? boleh pakai `--filtered-ratio 0` — port filtered dilewatkan
>   dulu, catat saja sebagai keterbatasan di laporan.

### 1b. (Opsional, harus run-as-admin) Blokir port filtered lewat firewall

```
python target/firewall_filtered.py --add
```

Ini menambah aturan DROP di firewall Windows supaya port "filtered" benar-benar
terasa seperti port diblok (koneksi nunggu sampai timeout). Tanpa langkah ini,
port filtered perilakunya mirip closed — tetap jalan, hanya beda karakter.

Hapus pas selesai demo: `python target/firewall_filtered.py --remove`

### 1c. Jalankan Target (terminal 1) — biarkan tetap menyala

```
python target/target_sim.py --serve --gt target/ground_truth.json
```

Yang muncul:
```
Target 127.0.0.1 berjalan: 160 listener 'open' (rentang GT: [1, 2000])
```

Terminal ini jangan ditutup — inilah "PC korban" yang dipindai.

### 1d. Izinkan port 5000 di firewall (biar worker bisa masuk)

```
netsh advfirewall firewall add rule name="DPS-master" dir=in action=allow protocol=TCP localport=5000
```

### 1e. Jalankan Master (terminal 2)

```
python master/master.py --targets targets.txt --gt target/ground_truth.json
```

Yang muncul:
```
Master 0.0.0.0:5000 | mode=dynamic | 8 task (chunk=250) | total 2000 port
```

Ini titik penting demo: **2000 port dipecah jadi 8 tugas kecil (task
decomposition)**, dan Master sekarang menunggu worker datang. Catat IP master
tadi — akan ditulis di perintah worker.

**Perintah yang bisa diketik langsung di terminal master** (fitur pilihan distribusi):

```
list                    -> lihat daftar worker: IP + NAMA LAPTOP + jumlah tugas + CPU
pilih 192.168.1.11      -> distribusi HANYA ke laptop itu
pilih DESKTOP-XYZ       -> bisa juga pakai nama laptop
pilih w1                -> atau pakai id worker (boleh beberapa: pilih 192.168.1.11 192.168.1.12)
all                     -> kembali membagikan ke SEMUA worker (default)
keluar                  -> hentikan master dengan rapi
```

Saat `pilih` aktif, worker lain tetap tersambung tapi tidak diberi tugas.
Biar tidak bingung, **laptop yang tidak dipilih akan menampilkan pesan jelas**
di layarnya (bukan diam tanpa kabar):
```
[menunggu tugas] Master sedang memilih worker lain untuk distribusi — laptop ini sengaja idle, bukan macet. (Di terminal master bisa ketik 'all' atau 'pilih <nama-mu>')
```
Begitu kamu ketik `all`, worker itu langsung dapat tugas lagi.

> Varian pembanding load balancing (kalau ditanya dosen):
> `python master/master.py --mode static --expected-workers 9`

---

## LANGKAH 2 — AS WORKER (di SETIAP PC worker, termasuk boleh di PC master buat coba-coba)

Buka folder `dps/` di PC worker, lalu cukup **satu perintah**:

```
python worker/worker.py --master <IP_MASTER>:5000
```

ganti `<IP_MASTER>` dengan IP yang tadi dicatat, mis. `192.168.1.10:5000`.

Yang muncul di worker:
```
Terhubung ke 192.168.1.10:5000 (mode=dynamic, proses=8, heartbeat=2.0s)
```

Yang muncul di layar master:
```
Worker w-DESKTOP-XYZ terhubung dari ('192.168.1.11', 55598) (cores=8, proses=8)
```

Ulangi perintah yang sama di PC worker lainnya. Selesai — worker langsung
kerja tanpa perlu diatur-atur lagi.

> Mau main-main di 1 PC saja? Buka beberapa terminal di PC master dan jalankan
> perintah worker di masing-masing terminal. Sama saja.

---

## SETELAH SEMUA WORKER MASUK — apa yang kelihatan?

1. **Dashboard** di layar master, update tiap 2 detik — **tiap laptop langsung
   terlacak: IP + nama laptop + STATUS-nya**:
   ```
   [dashboard] workers=9 (alive=9) | task: done=5 inflight=9 queued=3 failed=0 | port hasil=1500/2000 dup=0
   [distribusi] SEMUA worker
     w0    192.168.1.11    DESKTOP-ALFA    proses=8    tugas=2/2 cpu=35% | kerja
     w1    192.168.1.12    DESKTOP-BETA    proses=8    tugas=1/1 cpu=32% | kerja
     ...
   ```
   Kalau sedang mode `pilih`, baris `[distribusi]` berubah jadi
   `[distribusi] hanya ke: 192.168.1.11`, status worker yang tidak dipilih
   berubah jadi `menunggu (tidak dipilih)`, dan muncul pengingat kalau ada
   tugas antre:
   ```
   [hint] ada 3 tugas antre — kalau terasa macet, ketik 'all' atau 'pilih' worker lain
   ```
2. Di layar worker muncul identitas node sendiri saat connect:
   `Node ini: DESKTOP-ALFA (192.168.1.11) -> master 192.168.1.10:5000`,
   lalu sesekali: `Task t00003 selesai (250 port, 3.12 s)`. Kalau sempat
   menganggur, muncul pesan `[menunggu tugas] ...` yang menjelaskan kenapa
   (lihat bagian "Kalau terasa macet" di bawah).
3. Kalau semua tugas selesai, sendirian berhenti:
   - Master: `Semua task DONE/FAILED -> sistem selesai` → dia menyuruh semua
     worker pulang (SHUTDOWN), lalu menyimpan hasil.
   - Worker berhenti dengan sendirinya. Terminal bisa ditutup.

Hasil tersimpan di folder `results/`:

| File | Isinya |
|---|---|
| `results.json` / `results.csv` | status tiap port (open/closed/filtered) |
| `events.csv` | catatan kejadian: siapa daftar, siapa kerja task apa, worker mati, requeue |
| `heartbeats.csv` | catatan CPU/mem tiap worker |
| `summary.json` | angka penting: waktu eksekusi, throughput, distribusi tugas, **IP + nama laptop tiap worker**, dan **perbandingan dengan kunci jawaban** |

Poin yang enak disorot ke dosen di momen ini:
- **Task decomposition** — lihat log master: `8 task (chunk=250)`.
- **Parallel** — tiap worker pakai banyak proses (secara default = jumlah core;
  bisa diatur `--processes 4` misalnya).
- **Distributed** — TCP beneran antar PC; IP + nama laptop tiap node kelihatan
  di dashboard dan tersimpan di `summary.json`.
- **Load balancing** — worker yang cepat otomatis dapat tugas lebih banyak
  (cek `worker_stats` di `summary.json`), atau demo-kan perbedaannya dengan
  perintah `pilih` vs `all`.

### Kalau terasa macet / worker diam — baca statusnya, jangan panik

Semua keadaan "diam" sekarang punya pesan. Arti tiap status:

| Yang terlihat | Artinya | Yang perlu dilakukan |
|---|---|---|
| Worker: `[menunggu tugas] Master sedang memilih worker lain...` | laptop sengaja tidak dipilih (mode `pilih` aktif) | di master ketik `all`, atau `pilih` nama laptop itu |
| Worker: `[menunggu tugas] Antrean kosong / semua task sedang dikerjakan worker lain...` | normal — tugas sedang dipegang worker lain | tidak perlu apa-apa, otomatis lanjut |
| Master: kolom status `menunggu (tidak dipilih)` | sama dengan baris pertama di atas | ketik `all` di master |
| Master: `[hint] ada N tugas antre...` | ada tugas menunggu di mode `pilih` | ketik `all` atau `pilih` worker lain |
| Master: `MATI` di baris worker | koneksi worker putus / proses ditutup | tugas otomatis di-requeue; jalankan lagi `python worker/worker.py --master ...` di PC itu |
| Master: `failed=N` naik | 1 tugas sudah 3x gagal | cek jaringan/target, lalu jalankan ulang run |

Perintah `list` juga menampilkan kolom status yang sama — jadi kapan pun
ragu, ketik `list` dulu sebelum mengambil tindakan.

---

## DEMO TAMBAHAN YANG SERING DIMINTA DOSEN

### a. Fault tolerance (paling "manggung", wajibrekam)

1. Jalankan master + beberapa worker seperti di atas, biarkan berjalan.
2. **Matiin salah satu worker di tengah jalan** (Ctrl+C atau tutup terminalnya,
   atau matikan Wi-Fi PC itu).
3. Di layar master muncul:
   ```
   Worker w-XXX mati (connection_lost): requeue=2, failed=0
   ```
   Tugas si worker yang mati dikembalikan ke antrean dan dikerjakan worker lain.
4. Di akhir tunjukkan: hasil tetap lengkap (di `summary.json` → ground truth
   `matched` = total port, `mismatched` = 0).

### b. Bandingkan load balancing: static vs dynamic

- Dynamic (default, worker pintar dapat lebih banyak): jalankan normal.
- Static (bagi rata di awal, tidak peduli worker pintar/lemah):
  ```
  python master/master.py --mode static --expected-workers 9
  ```
  (`--expected-workers` harus sesuai jumlah worker yang masuk.)

### c. Benchmark T1–T6 + grafik (untuk laporan)

Target di langkah 1c harus jalan dulu. Ketik dari folder `dps/`:

```
python bench/run_sequential.py --gt target/ground_truth.json        # T1 baseline 1 proses
python bench/run_local_parallel.py                                  # T2 multiprocessing 1 PC
python bench/run_experiments.py --test all --repeat 1               # T3-T6 (demo cepat)
python bench/plot_results.py                                        # grafik PNG di results/
```

Untuk data laporan, ganti `--repeat 1` jadi `--repeat 3` (diulang 3x, di laporan
ditulis rata-rata ± simpangan baku). Detail tiap opsi ada di `README.md`.

---

## NASKAH VIDEO 5 MENIT

| Waktu | Yang direkam |
|---|---|
| 0:00–0:30 | Judul, anggota, tema 14, tujuan singkat |
| 0:30–1:15 | **Sapukan kamera ke 10 PC fisik** + label IP tiap PC (ini syarat dosen!) |
| 1:15–2:30 | Langkah 1–2: master jalan, 9 worker masuk satu-satu, dashboard jalan |
| 2:30–3:15 | Load balancing: tunjukkan jumlah tugas per worker di summary/dashboard |
| 3:15–4:15 | Fault tolerance: matikan 1 worker, tunjukkan requeue, hasil tetap lengkap |
| 4:15–5:00 | Ringkasan angka: speedup/efficiency dari grafik `t6_scalability.png`, tutup |

---

## FUNGSI-FUNGSI: biar tahu tiap file itu buat apa

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
| `master.py` → `_dashboard` | baris status yang muncul tiap 2 detik |

### `bench/` — alat uji
| Skrip | Gunanya |
|---|---|
| `run_sequential.py` | T1: tanpa paralel, tanpa jaringan — pembanding dasar |
| `run_local_parallel.py` | T2: multiprocessing di 1 PC |
| `run_experiments.py` | T3–T6: jalanin master+worker otomatis, matiin worker (T5), hitung scalability |
| `plot_results.py` | bikin 5 grafik PNG |

---

## SETELAH DEMO SELESAI — rapikan

```
python target/firewall_filtered.py --remove                                  # hapus blokir port filtered
netsh advfirewall firewall delete rule name="DPS-master"                     # hapus izin port 5000
```

Tutup semua terminal. Folder `results/` jangan dihapus — itu bukti pengujian.

## CHECKLIST SEBELUM REKAM VIDEO

- [ ] Semua PC sudah: Python + `pip install -r requirements.txt` + folder `dps/`
- [ ] Label kertas berisi IP ditempel di tiap PC (buat adegan 0:30–1:15)
- [ ] Uji coba penuh dari folder bersih pernah dilakukan (bukan cuma "katanya jalan")
- [ ] Beban target sudah dikalibrasi: scan sequential butuh beberapa menit
      (naikkan rentang port / filtered-ratio / timeout kalau masih cepat banget)
- [ ] Rekam layar + kamera sekaligus; master.log & dashboard ikut terlihat
