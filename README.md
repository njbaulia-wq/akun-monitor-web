# ◈ PantauAkun — Monitoring Performa Multi-Akun

> Tempel link postingan TikTok / Instagram / Threads / Facebook → otomatis di-scrape, dikelompokkan per akun, ditotal, lalu di-export ke Excel.

Repo: **https://github.com/njbaulia-wq/akun-monitor-web**

**100% read-only.** Tidak perlu password, tidak posting/DM. Login cookie hanya opsional untuk membuka fitur tambahan.

| | |
|---|---|
| 🖥 Server | Python stdlib saja, tanpa framework |
| 🗄 Database | SQLite satu file (`data/pantauakun.db`) |
| 📦 Dependensi | Hanya `openpyxl` |
| 🌐 Buka di | `http://localhost:8765` |

---

## 📋 Daftar isi

0. [Sebelum mulai — apa yang dibutuhkan](#0-sebelum-mulai--apa-yang-dibutuhkan)
1. [Install dari nol — Windows](#1-install-dari-nol--windows)
2. [Install dari nol — Linux](#2-install-dari-nol--linux)
3. [Menjalankan aplikasi](#3-menjalankan-aplikasi)
4. [Cara pakai sehari-hari](#4-cara-pakai-sehari-hari)
5. [Sesi login (opsional)](#5-sesi-login-opsional)
6. [Link yang dikenali & batasan platform](#6-link-yang-dikenali--batasan-platform)
7. [Isi project](#7-isi-project)
8. [Masalah umum](#8-masalah-umum)

---

## 0. Sebelum mulai — apa yang dibutuhkan

Siapkan 4 hal ini dulu (total waktu ±15 menit):

| # | Kebutuhan | Keterangan |
|---|---|---|
| 1 | 💻 Komputer | Windows 10/11 atau Linux (Ubuntu/Debian/Fedora/Arch). RAM 2 GB cukup |
| 2 | 🌐 Internet | Untuk download + scraping halaman publik platform |
| 3 | 🐍 Python 3.8 atau lebih baru | Belum punya? Ikuti Bagian 1 (Windows) / Bagian 2 (Linux) |
| 4 | 📥 Git | Untuk mengunduh project. Belum punya? Ikuti Bagian 1 Langkah 2 / Bagian 2. Alternatif tanpa Git: unduh ZIP (dijelaskan di bawah) |
| 5 | 🌍 Browser | Chrome / Edge / Firefox untuk membuka aplikasinya |

> Sudah punya Python + Git? Langsung lompat ke [Mulai cepat](#-mulai-cepat-kalau-python--git-sudah-ada).

### ⚡ Mulai cepat (kalau Python + Git sudah ada)

**Windows** (CMD / PowerShell):

```bat
git clone https://github.com/njbaulia-wq/akun-monitor-web.git
cd akun-monitor-web
pip install openpyxl
python app.py
```

**Linux**:

```bash
git clone https://github.com/njbaulia-wq/akun-monitor-web.git
cd akun-monitor-web
pip3 install openpyxl
python3 app.py
```

Lalu buka **http://localhost:8765** di browser. Selesai ✅

---

## 1. Install dari nol — Windows

Ikuti langkah 1 → 2 → 3 → 4 secara berurutan. Jangan dilewati.

### Langkah 1: cek dulu, siapa tahu sudah terinstall

1. Tekan `Win + R` di keyboard → ketik `cmd` → tekan Enter (jendela hitam = CMD).
2. Ketik perintah ini satu per satu, tekan Enter tiap baris:
   ```bat
   python --version
   pip --version
   git --version
   ```
3. Artinya:
   - Kalau ketiganya menampilkan nomor versi (mis. `Python 3.13.2`) → **langsung lompat ke [Langkah 3](#langkah-3-unduh-project).
   - Kalau ada yang `is not recognized` → install yang kurang itu di langkah berikut.

### Langkah 2: install Python

1. Buka browser → kunjungi **https://www.python.org/downloads/** (situs resmi Python).
2. Klik tombol kuning **Download Python 3.x** (ambil versi stabil terbaru yang ditawarkan).
3. Tunggu file `.exe` selesai terunduh, lalu **klik 2x** untuk menjalankannya.
4. ⚠️ **PENTING — jangan langsung klik Install:** pada halaman pertama installer, di bagian bawah ada checkbox **`Add python.exe to PATH`** → **centang dulu**, baru klik **Install Now**.
   - Kalau lupa mencentang, perintah `python` nanti tidak dikenal. Solusinya: install ulang dan centang, atau pakai perintah `py` sebagai pengganti `python` di semua perintah bawah.
5. Tunggu proses install selesai. Jika di akhir ada tombol **Disable path length limit**, klik itu → **Close**.
6. **Verifikasi** — tutup CMD lama, buka CMD **baru** (`Win + R` → `cmd`), jalankan:
   ```bat
   python --version
   pip --version
   ```
   Harus muncul mis. `Python 3.13.2` dan `pip 24.x`. Kalau masih `not recognized`, restart komputer sekali lalu coba lagi.

### Langkah 3: install Git

> Git dipakai untuk mengunduh project dari GitHub. **Tidak mau install Git?** Bisa lewati langkah ini — pakai cara ZIP di [Langkah 4 (cara ZIP)](#cara-tanpa-git-unduh-zip).

1. Buka browser → kunjungi **https://git-scm.com/download/win** (situs resmi Git).
2. Download otomatis berjalan. Jalankan file `.exe`-nya.
3. Klik **Next** terus sampai selesai (semua pilihan default sudah benar untuk pemula) → **Install** → **Finish**.
4. **Verifikasi** — buka CMD **baru**, jalankan:
   ```bat
   git --version
   ```
   Harus muncul mis. `git version 2.47.0`. Kalau `not recognized`, tutup CMD dan buka lagi.

### Langkah 4: unduh project

**Cara A — pakai Git (disarankan, gampang update):**

```bat
:: 1. pindah ke folder Downloads
cd %USERPROFILE%\Downloads

:: 2. unduh project dari GitHub
git clone https://github.com/njbaulia-wq/akun-monitor-web.git

:: 3. masuk ke folder project
cd akun-monitor-web
```

**Cara tanpa Git — unduh ZIP:**

1. Buka **https://github.com/njbaulia-wq/akun-monitor-web** di browser.
2. Klik tombol hijau **Code** → **Download ZIP**.
3. Ekstrak file ZIP ke `Downloads`, lalu di CMD:
   ```bat
   cd %USERPROFILE%\Downloads\akun-monitor-web-main
   ```
   (nama folder bisa sedikit berbeda, sesuaikan. Kalau pakai cara ZIP, perintah `git pull` untuk update tidak bisa dipakai — unduh ulang ZIP tiap ada versi baru.)

### Langkah 5: install pustaka `openpyxl` + jalankan

Masih di CMD, posisi sudah di dalam folder `akun-monitor-web`:

```bat
:: install pustaka Excel (sekali saja)
pip install openpyxl

:: jalankan aplikasinya
python app.py
```

Kalau berhasil, muncul tulisan seperti ini — **jangan tutup jendela CMD ini** selama memakai aplikasi:

```
PantauAkun jalan di http://localhost:8765
Database: C:\Users\NAMA\Downloads\akun-monitor-web\data\pantauakun.db
Log     : C:\Users\NAMA\Downloads\akun-monitor-web\data\app.log
```

### Langkah 6: buka di browser 🎉

Buka browser (Chrome/Edge/Firefox) → ketik di address bar:

```
http://localhost:8765
```

Halaman Dashboard PantauAkun akan terbuka. **Berhenti:** tekan `Ctrl + C` di jendela CMD. **Jalan lagi besok:** buka CMD → `cd` ke folder → `python app.py` lagi.

> Butuh baca file `.xls` lama (Excel 97–2003)? Tambahan sekali saja: `pip install xlrd`. Kalau tidak butuh, lewati.
>
> Kalau Windows Firewall bertanya saat pertama jalan, pilih **Cancel** saja — server hanya listen di `127.0.0.1` (komputer sendiri, tidak bisa diakses orang lain).

---

## 2. Install dari nol — Linux

Ikuti langkah 1 → 2 → 3 → 4 secara berurutan.

### Langkah 1: cek dulu apa yang sudah ada

Buka terminal, jalankan:

```bash
python3 --version
pip3 --version
git --version
```

- Ketiganya menampilkan nomor versi → **langsung lompat ke [Langkah 3](#langkah-3-unduh-project-1)**.
- Ada yang `command not found` → install di Langkah 2.

### Langkah 2: install Python + Git + pip

Pilih sesuai distro kamu (kalau tidak tahu pakai yang mana, kemungkinan besar Ubuntu/Debian → pakai perintah `apt`):

**Ubuntu / Debian / Linux Mint:**

```bash
sudo apt update
sudo apt install -y python3 python3-pip git
```

**Fedora:**

```bash
sudo dnf install -y python3 python3-pip git
```

**Arch / Manjaro:**

```bash
sudo pacman -S python python-pip git
```

**Verifikasi** (tutup terminal dan buka lagi bila perlu):

```bash
python3 --version
pip3 --version
git --version
```

Ketiganya harus menampilkan nomor versi.

### Langkah 3: unduh project

```bash
# 1. pindah ke folder Downloads
cd ~/Downloads

# 2. unduh project dari GitHub
git clone https://github.com/njbaulia-wq/akun-monitor-web.git

# 3. masuk ke folder project
cd akun-monitor-web
```

> Tanpa Git? Buka https://github.com/njbaulia-wq/akun-monitor-web → tombol **Code** → **Download ZIP** → ekstrak → `cd` ke foldernya.

### Langkah 4: install pustaka + jalankan

```bash
# install pustaka Excel (sekali saja)
pip3 install openpyxl

# jalankan aplikasinya
python3 app.py
```

Kalau berhasil muncul:

```
PantauAkun jalan di http://localhost:8765
Database: .../data/pantauakun.db
Log     : .../data/app.log
```

Buka **http://localhost:8765** di browser 🎉 **Berhenti:** `Ctrl + C`.

> Kalau `pip3` menolak dengan pesan `externally-managed-environment` (Ubuntu 23+ / Debian 12+), pakai salah satu cara ini:
> ```bash
> pip3 install --break-system-packages openpyxl
> # ATAU cara yang lebih rapi (venv) — tiap buka terminal baru, aktifkan dulu:
> python3 -m venv .venv
> source .venv/bin/activate
> pip install openpyxl
> python app.py
> ```

---

## 3. Menjalankan aplikasi

Perintah-perintah ini dipakai **setiap hari** setelah install selesai. Jalankan dari dalam folder `akun-monitor-web`.

| Perintah | Fungsi |
|---|---|
| `python app.py` (Windows) / `python3 app.py` (Linux) | Jalan di port default `8765` |
| `python app.py --port 8080` | Jalan di port lain (kalau 8765 dipakai aplikasi lain) |
| `Ctrl + C` | Berhenti (data aman, sudah tersimpan di database) |
| `git pull` | Update ke versi terbaru dari GitHub (hanya cara clone Git) |

**Tanda aplikasi berjalan normal:**

```
PantauAkun jalan di http://localhost:8765
```

Buka alamat itu di browser. Kalau browser menampilkan "tidak dapat terhubung", berarti server belum jalan atau port-nya beda — lihat jendela terminal/CMD.

**Jalan di background (Linux, opsional)** — supaya terminal bisa ditutup:

```bash
nohup python3 app.py > data/app.log 2>&1 &
# untuk menghentikan:
pkill -f "python3 app.py"
```

---

## 4. Cara pakai sehari-hari

### ① Isi daftar akun (sekali saja)

Halaman **Akun** → **Import dari Excel PEMANTAUAN** (`.xlsx`/`.csv`, sheet per platform, kolom `No, Username, Link Profile`).
Atau tambah satu-satu lewat form. File `accounts.csv` di repo hanya contoh — ganti dengan data kamu.

### ② Pilih periode

Bar atas → isi **Periode** (default pekan berjalan Senin–Minggu, zona **WIB**).

### ③ Tempel link → scrape

Halaman **Input Link** → tempel link (satu per baris, boleh campur platform, ratusan sekaligus) → **Scrape & kelompokkan**.
Bisa juga **Import link dari Excel** — semua link postingan terdeteksi otomatis, link profil dilewati.

- Ada progress bar, aplikasi bisa dipakai sambil jalan.
- Gagal karena jaringan dicoba ulang otomatis 3x. Tombol **Ulangi yang gagal** untuk coba lagi.
- Link duplikat dibuang otomatis. Hasil dikelompokkan per akun — yang tidak cocok tinggal pilih manual → **Simpan**.

### ④ Lihat Dashboard

Total Views / Komen / Share / Like / Repost / Interaksi per akun + tren harian.
Tanda `—` artinya *tidak diekspos platform*, bukan nol.

### ⑤ Export Excel

Tombol **Export** di bar atas → `.xlsx` (ada rumus `SUM`) atau `.csv`.

### Fitur lain

- **Pengaturan → Tarik semua akun Threads**: ambil postingan otomatis per akun, tanpa link, tanpa login.
- **Kelola Data**: hapus per posting / akun / platform / periode / reset. Daftar akun **tidak pernah ikut terhapus**. Backup otomatis dibuat sebelum hapus besar.
- **Riwayat metrik**: klik angka postingan di detail akun → lihat snapshot + selisih `Δ` tiap scrape ulang.

---

## 5. Sesi login (opsional)

Hanya 1 akun admin per platform. Tool **tidak pernah meminta password** — cukup cookie dari browser kamu sendiri:

1. Login ke platformnya di Chrome/Firefox seperti biasa.
2. Pasang ekstensi **Get cookies.txt LOCALLY** → klik → **Export** → simpan `.txt`.
3. Di aplikasi buka **Pengaturan → Sesi login** → upload/tempel cookie → **Simpan** → **Tes sesi**.
4. Cookie kedaluwarsa? Export ulang dan simpan lagi.

| Tanpa sesi | Dengan 1 sesi admin |
|---|---|
| TikTok per link ✅ | tetap via Input Link |
| IG per link ✅ | ➕ daftar postingan per akun otomatis |
| Threads per link ✅ | ➕ view count ikut terbaca |
| Facebook ❌ | ➕ bisa baca postingan (like/komen/share) |

Cookie tersimpan **hanya** di `data/pantauakun.db` di komputermu (file ini di-ignore git, tidak ikut ter-upload).

---

## 6. Link yang dikenali & batasan platform

**Link yang bisa ditempel:**

- TikTok: `tiktok.com/ZSxxx`, `vt./vm.tiktok.com/…`, `@user/video/<id>`, `@user/photo/<id>` (foto ✅)
- Instagram: `/reel/<kode>/`, `/p/<kode>/` (tab `/reels/` otomatis dinormalkan)
- Threads: `/share/…`, `@user/post/<kode>`
- Facebook: `/share/…`, `/posts/…`, `/watch`, `/reel/`, `/videos/…`, `/photo`, `fb.watch/…` (butuh cookie)

**Batasan jujur** (sel kosong = memang tidak diekspos publik):

| Metrik | TikTok | Instagram | Threads | Facebook |
|---|---|---|---|---|
| Tanggal | ✅ | ✅ hari saja (jam 00:00 placeholder) | ✅ | ✅ |
| Views | ✅ | ✅ (reel/video) | ⚠️ akun >10rb views/bln + cookie | ❌ tidak ada |
| Like / Komen | ✅ | ✅ | ✅ | ✅ |
| Share | ✅ | ❌ | ❌ | ✅ |
| Repost | ❌ | ❌ | ✅ | ❌ |

---

## 7. Isi project

```
akun-monitor-web/
├── app.py            # server HTTP + API + background job (tanpa framework)
├── db.py             # SQLite: accounts, posts, metrics, settings
├── scrape.py         # scraping per platform
├── fetchers/         # fetcher tiktok / instagram / threads
├── session.py        # cookie sesi login
├── exporter.py       # export .xlsx / .csv
├── sheetio.py        # baca .xlsx / .xls / .csv
├── accounts.csv      # CONTOH 5 akun (ganti dengan data kamu)
├── cek_facebook.py   # tes koneksi Facebook: python cek_facebook.py <url>
├── web/              # UI (index.html + static/)
├── data/             # database lokal — dibuat otomatis, TIDAK di-commit
└── .gitignore        # mengecualikan data/*.db, backup, checkpoint, log
```

Hapus `data/pantauakun.db` untuk mulai dari nol.

---

## 8. Masalah umum

| Gejala | Solusi |
|---|---|
| `python` tidak dikenal (Windows) | Ulangi Bagian 1 Langkah 2 (centang `Add to PATH`), restart CMD/komputer, atau pakai `py app.py` |
| `git` tidak dikenal (Windows) | Ulangi Bagian 1 Langkah 3, buka CMD baru |
| `pip install` ditolak / `externally-managed` (Linux baru) | `pip3 install --break-system-packages openpyxl` atau pakai `venv` (lihat Bagian 2) |
| `Address already in use` | Port bentrok → `python app.py --port 8080`, lalu buka `http://localhost:8080` |
| `ModuleNotFoundError: openpyxl` | Install dulu: `pip install openpyxl` (Windows) / `pip3 install openpyxl` (Linux) |
| `.xls` lama tidak terbaca | `pip install xlrd`, atau buka di Excel/LibreOffice → Save As `.xlsx` |
| Browser "tidak dapat terhubung" | Pastikan jendela CMD/terminal masih terbuka dan tulisan `PantauAkun jalan di ...` masih ada |
| TikTok banyak gagal / captcha | Wajar (anti-bot). Coba lagi nanti, naikkan jeda di Pengaturan |
| Facebook gagal semua | Isi/refresh cookie → Tes sesi. Tanpa cookie FB memang tidak bisa |
| Threads views `—` | Hanya akun besar + cookie. Selain itu memang tidak diekspos |
| Dashboard kosong | Cek filter periode, lalu Input Link → Scrape → Simpan |
| `data/` kosong setelah clone | Normal — dibuat otomatis saat pertama jalan |

Log: `data/app.log`. Tes Facebook: `python cek_facebook.py <url_postingan>` (Windows) / `python3 cek_facebook.py <url_postingan>` (Linux).

---

*Scrape dengan sopan: jeda min 2 detik per platform, hormati rate limit, cukup 1x per pekan untuk pemakaian rutin.*
