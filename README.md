# PantauAkun — Monitoring Performa Multi-Akun

Web app lokal untuk memantau performa banyak akun **TikTok, Instagram, Threads, Facebook**.

Alur kerja: tempel link postingan → otomatis di-scrape & dikelompokkan per akun → total Views / Komen / Share / Like / Repost per akun → export Excel format spreadsheet pemantauan mingguan.

**100% read-only, tanpa login wajib.** Tidak memakai password, tidak posting/DM. Sesi login (cookie) hanya opsional untuk membuka fitur tambahan.

- Server: Python stdlib saja (`http.server`), tanpa framework.
- Database: SQLite satu file (`data/pantauakun.db`), mudah di-backup.
- Dependensi tambahan: hanya `openpyxl` (untuk baca/tulis Excel).

Sumber resmi: Python → https://www.python.org/downloads/ · openpyxl → https://pypi.org/project/openpyxl/

---

## 1. Kebutuhan (requirements)

| Kebutuhan | Keterangan |
|---|---|
| Python 3.8+ | Windows / Linux / macOS. Teruji di Python 3.14 |
| `openpyxl` | Wajib (export `.xlsx` + import Excel). `pip install openpyxl` |
| `xlrd` | Opsional, hanya jika ingin import file `.xls` lama (Excel 97–2003). `pip install xlrd` |
| Browser | Chrome / Edge / Firefox untuk membuka `http://localhost:8765` |
| Internet | Untuk scraping (membaca halaman publik platform) |

Tidak butuh Node.js, tidak butuh database server, tidak butuh API key.

---

## 2. Setup & menjalankan di Windows (detail lengkap)

### 2.1. Install Python

1. Buka https://www.python.org/downloads/ di browser.
2. Klik **Download Python 3.x** (tombol kuning, ambil versi stabil terbaru).
3. Jalankan file `.exe` yang terunduh.
4. **PENTING:** pada halaman pertama installer, centang **`Add python.exe to PATH`**, lalu klik **Install Now**.
5. Tunggu sampai selesai → klik **Close**.
6. Verifikasi — buka **CMD** baru (tombol `Win + R` → ketik `cmd` → Enter), lalu jalankan:
   ```bat
   python --version
   pip --version
   ```
   Harus muncul mis. `Python 3.13.x` dan `pip 24.x`. Jika `python` tidak dikenal, ulangi langkah 4 (PATH belum masuk) atau pakai perintah `py` sebagai ganti `python`.

### 2.2. Download project ini

```bat
:: pindah ke folder kerja, mis:
cd %USERPROFILE%\Downloads

:: jika dari GitHub (ganti URL dengan repo kamu):
git clone https://github.com/USERNAME/pantauakun-web.git
cd pantauakun-web

:: atau jika unduh ZIP: ekstrak, lalu:
cd pantauakun-web
```

### 2.3. Install dependensi

```bat
pip install openpyxl
```

Opsional (untuk file `.xls` lama):

```bat
pip install xlrd
```

### 2.4. Jalankan server

```bat
python app.py
```

Untuk port lain:

```bat
python app.py --port 8080
```

Jika berhasil muncul:

```
PantauAkun jalan di http://localhost:8765
Database: ...\data\pantauakun.db
Log     : ...\data\app.log
```

### 2.5. Buka di browser

Buka: **http://localhost:8765**

### 2.6. Berhenti

Tekan `Ctrl + C` di jendela CMD. Database aman (sudah tersimpan di SQLite).

> Tips Windows: jika port 8765 dipakai aplikasi lain, muncul error `Address already in use` — pakai `--port` lain seperti di atas. Jika Windows Firewall bertanya, pilih **Cancel** saja (server hanya listen di `127.0.0.1`, tidak bisa diakses dari luar).

---

## 3. Setup & menjalankan di Linux (detail lengkap)

### 3.1. Install Python

**Ubuntu / Debian / Mint:**

```bash
sudo apt update
sudo apt install -y python3 python3-pip
python3 --version
pip3 --version
```

**Fedora:**

```bash
sudo dnf install -y python3 python3-pip
```

**Arch / Manjaro:**

```bash
sudo pacman -S python python-pip
```

### 3.2. Download project ini

```bash
cd ~/Downloads
# ganti URL dengan repo kamu:
git clone https://github.com/USERNAME/pantauakun-web.git
cd pantauakun-web
# atau ekstrak ZIP lalu cd ke foldernya
```

### 3.3. Install dependensi

```bash
pip3 install openpyxl
# atau, jika pip dibatasi (PEP 668 di Debian 12+/Ubuntu 23+):
pip3 install --break-system-packages openpyxl
# alternatif rapi: pakai venv
# python3 -m venv .venv && source .venv/bin/activate && pip install openpyxl
```

Opsional:

```bash
pip3 install xlrd   # hanya untuk .xls lama
```

### 3.4. Jalankan server

```bash
python3 app.py
# port lain:
python3 app.py --port 8080
```

Output yang diharapkan:

```
PantauAkun jalan di http://localhost:8765
Database: .../data/pantauakun.db
Log     : .../data/app.log
```

### 3.5. Buka di browser

Buka: **http://localhost:8765**

### 3.6. Berhenti & jalan di background

```bash
# hentikan: Ctrl + C
# jalan background (opsional):
nohup python3 app.py > data/app.log 2>&1 &
# hentikan background:
pkill -f "python3 app.py"
```

---

## 4. Cara pakai (5 menit)

### Langkah 1 — Isi daftar akun

Buka halaman **Akun** → **Import dari Excel PEMANTAUAN** (pilih `.xlsx` / `.csv`).
Format terdeteksi dari **isi file**, bukan ekstensi. Kolom: `No, Username, Link Profile`. Sheet per platform (INSTAGRAM / TIKTOK / THREADS / FACEBOOK) dibaca otomatis.

Atau tambah manual via form (`Kode, Platform, Username, Link Profile`).

Contoh `accounts.csv` bawaan berisi 5 akun contoh — ganti dengan data kamu.

### Langkah 2 — Pilih periode

Di bar atas, isi **Periode** (default: pekan berjalan Senin–Minggu). Semua tanggal memakai **WIB (UTC+7)**.

### Langkah 3 — Input link

Buka **Input Link** → tempel link postingan (satu per baris, boleh campur platform, puluhan/ratusan sekaligus) → **Scrape & kelompokkan**.

Atau **Import link dari Excel**: semua link postingan di semua sheet & sel (termasuk hyperlink) terdeteksi otomatis. Link profil dilewati dengan laporan jelas.

- Berjalan sebagai **background job** (progress bar + tabel live, bisa dipakai sambil jalan).
- **Retry otomatis** 3x untuk gagal transien (timeout, 429, 5xx). Gagal permanen (URL ngawur) langsung final.
- Tombol **Ulangi yang gagal** untuk mencoba lagi yang transien.
- Link duplikat otomatis dibuang. Hasil dikelompokkan per akun + subtotal. Yang tidak cocok → pilih manual → **Simpan**.

### Langkah 4 — Dashboard

Lihat total per akun + rekap per platform + tren harian. `—` = metrik tidak diekspos platform (bukan 0).

### Langkah 5 — Export Excel

Klik **Export** di bar atas → unduh `.xlsx` (kolom persis spreadsheet pemantauan, `Jumlah Interaksi` = rumus `SUM`) atau `.csv`.

### Fitur tambahan

- **Tarik otomatis Threads** (Pengaturan → *Tarik semua akun Threads*): tanpa login, daftar postingan diambil per akun.
- **Tarik otomatis Instagram**: butuh sesi login (lihat bawah).
- **Sesi login (opsional)**: 1 akun admin per platform. Login di browser → export cookie via ekstensi *Get cookies.txt LOCALLY* → Pengaturan → Sesi login → upload/tempel → Simpan → Tes sesi. Cookie hanya tersimpan di `data/pantauakun.db`, tidak dikirim ke mana pun selain platformnya.
- **Kelola Data**: hapus per posting / akun / platform / periode / reset semua. Daftar akun tidak pernah ikut terhapus. Backup otomatis dibuat sebelum hapus besar.
- **Riwayat metrik**: scrape ulang menambah snapshot baru; kolom `Δ` menampilkan selisih (hijau naik / merah turun).

---

## 5. Bentuk link yang dikenali

| Link | Hasil |
|---|---|
| `tiktok.com/ZSxxx`, `vt.tiktok.com/…`, `vm.tiktok.com/…`, `@user/video/<id>` | ✅ |
| `tiktok.com/@user/photo/<id>` (posting foto) | ✅ via jalur mobile |
| `instagram.com/reel/<code>/`, `/p/<code>/` | ✅ (`/reels/` dinormalkan ke `/reel/`) |
| `threads.com/share/…`, `threads.net/@u/post/<code>` | ✅ |
| `facebook.com/share/r/…`, `/posts/…`, `/watch`, `/reel/`, `/videos/…`, `/photo`, `fb.watch/…` | ✅ butuh cookie |

---

## 6. Batasan jujur per platform

| Metrik | IG | TikTok | Threads | Facebook |
|---|---|---|---|---|
| Tanggal | ✅ (hari saja, jam 00:00 placeholder) | ✅ | ✅ | ✅ (butuh sesi) |
| Views | ✅ (reel/video) | ✅ | ⚠️ hanya akun >10rb views/bln + butuh cookie | ❌ tidak ada di HTML |
| Like / Komen | ✅ | ✅ | ✅ | ✅ (butuh sesi) |
| Share | ❌ tidak diekspos | ✅ | ❌ | ✅ (butuh sesi) |
| Repost | ❌ | ❌ | ✅ | ❌ |

Sel kosong/`—` berarti "tidak diekspos platform", bukan 0.

---

## 7. Struktur project

```
pantauakun-web/
  app.py            # server HTTP stdlib + API JSON + background job
  db.py             # SQLite: accounts, posts, metrics, settings
  scrape.py         # scraping tanpa login (deteksi platform, resolve short-link)
  exporter.py       # export .xlsx / .csv format pemantauan
  sheetio.py        # baca .xlsx/.xls/.csv (deteksi dari isi file)
  session.py        # cookie sesi login (Instagram/Threads/Facebook)
  accounts.csv      # contoh 5 akun (ganti dengan data kamu)
  web/              # UI: index.html + static/style.css + static/app.js
  data/             # pantauakun.db (dibuat otomatis, JANGAN di-commit)
  .gitignore        # mengecualikan data/*.db, backup, checkpoint, log
```

Database: `data/pantauakun.db` (SQLite satu file). Hapus file itu untuk mulai dari nol. File ini di-ignore git karena berisi cookie sesi (setara password).

---

## 8. Troubleshooting

| Gejala | Solusi |
|---|---|
| `python` tidak dikenal (Windows) | Centang `Add to PATH` saat install, atau pakai `py app.py` |
| `pip install` gagal / `externally-managed` (Linux baru) | `pip3 install --break-system-packages openpyxl` atau pakai `venv` |
| `Address already in use` | Portbentrok → `python app.py --port 8080` |
| `ModuleNotFoundError: openpyxl` | `pip install openpyxl` (atau `pip3`) |
| File `.xls` tidak terbaca | `pip install xlrd`, atau Save As `.xlsx` di Excel/LibreOffice |
| TikTok captcha / banyak gagal | Wajar (anti-bot). Turunkan worker ke 1, naikkan jeda di Pengaturan, coba lagi lain waktu |
| Facebook gagal semua | Isi/refresh cookie di Pengaturan → Tes sesi. Tanpa cookie FB memang tidak bisa |
| Threads views `—` | Hanya akun >10rb views/30 hari + butuh cookie. Selain itu memang tidak diekspos |
| Dashboard kosong | Belum ada postingan di periode itu — cek filter tanggal, lalu Input Link → Simpan |
| `data/` hilang setelah clone | Normal (di-ignore). Dibuat otomatis saat `app.py` pertama jalan |

Cek log: `data/app.log`. Cek koneksi Facebook: `python cek_facebook.py <url_post>`.

---

## 9. Etika & ketahanan

- 3 worker paralel + jeda sopan min 2 detik per platform (tidak membanjiri).
- Hanya membaca data publik; hormati rate limit. Untuk pemakaian mingguan, scrape cukup **1x per pekan**.
- Hasil tersimpan aman di SQLite; job besar punya checkpoint tiap 10 item agar tidak hilang saat restart.
