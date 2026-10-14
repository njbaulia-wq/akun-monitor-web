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

## ⚡ Mulai cepat (3 perintah)

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

> Belum punya Python atau Git? Ikuti panduan lengkap di bawah (Windows → bagian 1, Linux → bagian 2).

---

## 📋 Daftar isi

1. [Install dari nol — Windows](#1-install-dari-nol--windows)
2. [Install dari nol — Linux](#2-install-dari-nol--linux)
3. [Menjalankan aplikasi](#3-menjalankan-aplikasi)
4. [Cara pakai sehari-hari](#4-cara-pakai-sehari-hari)
5. [Sesi login (opsional)](#5-sesi-login-opsional)
6. [Link yang dikenali & batasan platform](#6-link-yang-dikenali--batasan-platform)
7. [Isi project](#7-isi-project)
8. [Masalah umum](#8-masalah-umum)

---

## 1. Install dari nol — Windows

### Langkah 1: install Python

1. Buka **https://www.python.org/downloads/** → klik tombol kuning **Download Python 3.x**.
2. Jalankan file `.exe` yang terunduh.
3. ⚠️ Pada halaman pertama installer, **centang `Add python.exe to PATH`** → klik **Install Now** → tunggu → **Close**.
4. Buka CMD baru (`Win + R` → ketik `cmd` → Enter), cek:
   ```bat
   python --version
   pip --version
   ```
   Harus muncul nomor versi. Kalau `python` tidak dikenal, ulangi langkah 3 atau pakai perintah `py` sebagai pengganti `python`.

### Langkah 2: install Git (kalau belum ada)

Unduh di **https://git-scm.com/download/win**, install dengan semua default. Atau tanpa Git: buka repo di browser → tombol hijau **Code** → **Download ZIP** → ekstrak.

### Langkah 3: unduh project + install + jalan

```bat
cd %USERPROFILE%\Downloads
git clone https://github.com/njbaulia-wq/akun-monitor-web.git
cd akun-monitor-web
pip install openpyxl
python app.py
```

Buka **http://localhost:8765** 🎉

> Butuh baca file `.xls` lama (Excel 97–2003)? Tambahan: `pip install xlrd`. Kalau tidak butuh, lewati saja.

---

## 2. Install dari nol — Linux

### Ubuntu / Debian / Mint

```bash
sudo apt update
sudo apt install -y python3 python3-pip git
git clone https://github.com/njbaulia-wq/akun-monitor-web.git
cd akun-monitor-web
pip3 install openpyxl
python3 app.py
```

### Fedora

```bash
sudo dnf install -y python3 python3-pip git
git clone https://github.com/njbaulia-wq/akun-monitor-web.git
cd akun-monitor-web
pip3 install openpyxl
python3 app.py
```

### Arch / Manjaro

```bash
sudo pacman -S python python-pip git
git clone https://github.com/njbaulia-wq/akun-monitor-web.git
cd akun-monitor-web
pip install openpyxl
python app.py
```

> Kalau `pip` menolak dengan pesan `externally-managed-environment` (Ubuntu 23+ / Debian 12+), pakai salah satu:
> ```bash
> pip3 install --break-system-packages openpyxl
> # atau lebih rapi pakai venv:
> python3 -m venv .venv && source .venv/bin/activate && pip install openpyxl
> ```

Buka **http://localhost:8765** 🎉

---

## 3. Menjalankan aplikasi

| Perintah | Fungsi |
|---|---|
| `python app.py` / `python3 app.py` | Jalan di port default `8765` |
| `python app.py --port 8080` | Jalan di port lain (kalau 8765 bentrok) |
| `Ctrl + C` | Berhenti (data aman, sudah tersimpan) |

Kalau berhasil, muncul tulisan:

```
PantauAkun jalan di http://localhost:8765
Database: .../data/pantauakun.db
Log     : .../data/app.log
```

**Jalan di background (Linux, opsional):**

```bash
nohup python3 app.py > data/app.log 2>&1 &
pkill -f "python3 app.py"   # untuk menghentikan
```

**Update ke versi terbaru dari GitHub:**

```bash
git pull
```

> Catatan: server hanya listen di `127.0.0.1` (komputer sendiri). Kalau Windows Firewall bertanya, pilih **Cancel** saja.

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

- Ada progress bar, bisa dipakai sambil jalan.
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
| `python` tidak dikenal (Windows) | Centang `Add to PATH` saat install Python, atau pakai `py app.py` |
| `pip install` ditolak (Linux baru) | `pip3 install --break-system-packages openpyxl` atau pakai `venv` |
| `Address already in use` | Port bentrok → `python app.py --port 8080` |
| `ModuleNotFoundError: openpyxl` | `pip install openpyxl` (Windows) / `pip3 install openpyxl` (Linux) |
| `.xls` lama tidak terbaca | `pip install xlrd`, atau Save As `.xlsx` |
| TikTok banyak gagal / captcha | Wajar (anti-bot). Coba lagi nanti, naikkan jeda di Pengaturan |
| Facebook gagal semua | Isi/refresh cookie → Tes sesi. Tanpa cookie FB memang tidak bisa |
| Threads views `—` | Hanya akun besar + cookie. Selain itu memang tidak diekspos |
| Dashboard kosong | Cek filter periode, lalu Input Link → Scrape → Simpan |
| `data/` kosong setelah clone | Normal — dibuat otomatis saat pertama jalan |

Log: `data/app.log`. Tes Facebook: `python cek_facebook.py <url_postingan>`.

---

*Scrape dengan sopan: jeda min 2 detik per platform, hormati rate limit, cukup 1x per pekan untuk pemakaian rutin.*
