# ◈ PantauAkun — Monitoring Performa Multi-Akun

> Tempel link postingan TikTok / Instagram / Threads / Facebook → otomatis dihitung Views, Komen, Share, Like-nya per akun → hasilnya bisa di-download sebagai file Excel.

Repo: **https://github.com/njbaulia-wq/akun-monitor-web**

Aplikasi ini **hanya membaca** (tidak perlu password, tidak bisa posting/mengubah apa-apa di akunmu). Satu pengecualian: menu **Cek Follow** memakai cookie sesi Instagram untuk *membaca* status follow — lihat [Bagian F](#cek-follow-butuh-sesi-opsional).

---

## 📋 Daftar isi

- [Bagian A: Persiapan (cukup sekali saja)](#bagian-a-persiapan-cukup-sekali-saja)
  - [Langkah 1: Install Python](#langkah-1-install-python)
  - [Langkah 2: Install Git](#langkah-2-install-git)
  - [Langkah 3: Download aplikasi ini](#langkah-3-download-aplikasi-ini)
  - [Langkah 4: Install openpyxl](#langkah-4-install-openpyxl)
- [Bagian B: Menjalankan tiap hari](#bagian-b-menjalankan-tiap-hari)
- [Bagian C: Cara memakai aplikasinya](#bagian-c-cara-memakai-aplikasinya)
- [Bagian D: Kalau ada error](#bagian-d-kalau-ada-error)
- [Bagian E: Untuk pengguna Linux](#bagian-e-untuk-pengguna-linux)
- [Bagian F: Keterangan tambahan](#bagian-f-keterangan-tambahan)
  - [Sesi login (opsional)](#sesi-login-opsional-1-akun-admin)
  - [Cek follow (butuh sesi)](#cek-follow-butuh-sesi-opsional)

---

## Bagian A: Persiapan (cukup sekali saja)

> Bagian ini hanya dilakukan **satu kali**. Kalau sudah selesai, tiap hari cukup buka [Bagian B](#bagian-b-menjalankan-tiap-hari).

Sebelum mulai, siapkan 3 hal ini:

1. 💻 **Komputer Windows 10 atau 11** + internet.
2. 🌍 **Browser** (Chrome, Edge, atau Firefox — yang biasa dipakai buka internet).
3. ⏰ Waktu sekitar **15 menit**.

Kita akan install 2 program gratis: **Python** (bahasa yang dipakai aplikasi ini) dan **Git** (alat untuk download aplikasi dari GitHub).

---

### Langkah 1: Install Python

**Apa itu Python?** Python itu program gratis yang wajib ada supaya aplikasi PantauAkun bisa berjalan. Ibaratnya seperti mesinnya.

**1a. Cek dulu, mungkin Python sudah ada:**

1. Tekan tombol **`Win + R`** di keyboard secara bersamaan (tombol Win = tombol bergambar jendela, di kiri bawah keyboard).
2. Akan muncul kotak kecil. Ketik di situ: `cmd` lalu tekan **Enter**.
3. Akan terbuka jendela hitam. Itu namanya **CMD** (tempat mengetik perintah). Ketik persis seperti ini lalu tekan Enter:
   ```
   python --version
   ```
4. Lihat hasilnya:
   - Kalau muncul tulisan seperti `Python 3.13.2` → **Python sudah ada, langsung lompat ke [Langkah 2](#langkah-2-install-git).** 🎉
   - Kalau muncul `is not recognized` → lanjut ke 1b di bawah (belum ada, harus install).

**1b. Download Python:**

1. Buka browser (Chrome/Edge), ketik di address bar (kolom alamat atas):
   ```
   python.org/downloads
   ```
   lalu Enter.
2. Klik tombol kuning besar bertuliskan **Download Python 3.x**.
3. Tunggu sampai file selesai ter-download (nama file seperti `python-3.13.x.exe`, ada di folder Downloads).

**1c. Install Python:**

1. Buka folder **Downloads**, **klik 2x** file Python yang tadi.
2. Akan muncul jendela installer. ⚠️ **PERHATIAN — jangan langsung klik Install.** Lihat di bagian **bawah** jendela, ada kotak kecil (checkbox) bertuliskan **`Add python.exe to PATH`**. **Klik kotak itu sampai ada tanda centang (✓).** Ini penting, kalau lupa dicentang aplikasi tidak bisa jalan.
3. Setelah dicentang, klik tombol **Install Now**.
4. Tunggu sampai selesai (beberapa menit). Kalau di akhir ada tombol **Disable path length limit**, klik itu. Lalu klik **Close**.

**1d. Pastikan berhasil:**

1. **Tutup** jendela hitam (CMD) yang lama, buka yang **baru** (`Win + R` → ketik `cmd` → Enter).
2. Ketik ini lalu Enter:
   ```
   python --version
   ```
3. Harus muncul `Python 3.x.x`. Kalau masih `not recognized`, **restart komputer** sekali lalu coba lagi.

---

### Langkah 2: Install Git

**Apa itu Git?** Git itu alat gratis untuk mendownload aplikasi dari GitHub. Ibaratnya seperti kurir yang mengantar aplikasi ke komputermu.

**2a. Cek dulu, mungkin Git sudah ada:**

1. Buka CMD baru (`Win + R` → `cmd` → Enter), ketik lalu Enter:
   ```
   git --version
   ```
2. Kalau muncul seperti `git version 2.47.0` → **Git sudah ada, lompat ke [Langkah 3](#langkah-3-download-aplikasi-ini).** 🎉
3. Kalau `is not recognized` → lanjut 2b.

**2b. Download dan install Git:**

1. Buka browser, ketik di address bar:
   ```
   git-scm.com/install/windows
   ```
   lalu Enter. (Kalau halaman tidak terbuka, buka `git-scm.com` lalu klik **Downloads** → **Windows**.)
2. Download Git dari halaman itu, lalu jalankan file `.exe`-nya.
3. Klik **Next** terus-menerus sampai ada tombol **Install** (tidak perlu mengubah apa pun, semua pilihan bawaan sudah benar) → klik **Install** → tunggu → **Finish**.
4. Buka CMD **baru**, ketik lalu Enter:
   ```
   git --version
   ```
   Harus muncul nomor versi. Kalau belum, tutup CMD dan buka lagi.

---

### Langkah 3: Download aplikasi ini

Sekarang download aplikasi PantauAkun ke komputermu:

1. Buka CMD (`Win + R` → `cmd` → Enter).
2. Ketik perintah ini lalu Enter (fungsinya: pindah ke folder Downloads):
   ```
   cd %USERPROFILE%\Downloads
   ```
3. Ketik perintah ini lalu Enter (fungsinya: download aplikasi dari GitHub, tunggu sampai selesai):
   ```
   git clone https://github.com/njbaulia-wq/akun-monitor-web.git
   ```
4. Ketik perintah ini lalu Enter (fungsinya: masuk ke folder aplikasi):
   ```
   cd akun-monitor-web
   ```

> **Tidak mau install Git?** Bisa tanpa Git: buka https://github.com/njbaulia-wq/akun-monitor-web di browser → klik tombol hijau **Code** → **Download ZIP** → ekstrak file ZIP ke Downloads → di CMD ketik `cd %USERPROFILE%\Downloads\akun-monitor-web-main` (nama folder menyesuaikan). Kekurangannya: untuk update versi baru harus download ulang.

---

### Langkah 4: Install openpyxl

**Apa itu openpyxl?** Pustaka kecil gratis supaya aplikasi bisa membaca dan membuat file Excel. Hanya install sekali.

1. Masih di CMD yang sama (posisi sudah di dalam folder `akun-monitor-web`), ketik lalu Enter:
   ```
   pip install openpyxl
   ```
2. Tunggu sampai muncul tulisan `Successfully installed openpyxl...`. Selesai ✅

---

## Bagian B: Menjalankan tiap hari

Setelah Bagian A selesai, tiap mau pakai aplikasi cukup 2 perintah ini:

1. Buka CMD (`Win + R` → `cmd` → Enter).
2. Ketik lalu Enter (masuk ke folder aplikasi):
   ```
   cd %USERPROFILE%\Downloads\akun-monitor-web
   ```
3. Ketik lalu Enter (menjalankan aplikasi):
   ```
   python app.py
   ```
4. Kalau berhasil akan muncul tulisan seperti ini. **Jendela CMD ini JANGAN ditutup** selama memakai aplikasi:
   ```
   PantauAkun jalan di http://localhost:8765
   Database: C:\Users\...\akun-monitor-web\data\pantauakun.db
   ```
5. Buka browser → ketik di address bar:
   ```
   localhost:8765
   ```
   lalu Enter. Halaman PantauAkun terbuka 🎉

**Selesai memakai?** Klik jendela CMD, tekan **`Ctrl + C`**, lalu tutup CMD. Data kamu aman, tidak hilang.

**Besok mau pakai lagi?** Ulangi Bagian B dari nomor 1 (cukup 2 perintah + buka browser).

**Mau update ke versi terbaru?** (hanya kalau download pakai Git) Buka CMD di folder aplikasi, ketik:
```
git pull
```

---

## Bagian C: Cara memakai aplikasinya

### ① Isi daftar akun (sekali saja)

1. Klik menu **Akun** (di kiri).
2. Klik **Import dari Excel PEMANTAUAN**, pilih file Excel/CSV kamu. Kolomnya: `No, Username, Link Profile`. Kalau file punya sheet per platform (INSTAGRAM / TIKTOK / THREADS / FACEBOOK), semuanya terbaca otomatis.
3. Bisa juga tambah satu-satu lewat form (isi Kode, Platform, Username).

> File `accounts.csv` di folder hanya contoh isi 5 akun — nanti terganti dengan data kamu sendiri.

### ② Pilih periode

Di bagian **atas**, isi tanggal **Periode** (misal Senin sampai Minggu). Default-nya sudah pekan berjalan.

### ③ Tempel link → scrape

1. Klik menu **Input Link**.
2. Tempel link postingan ke kotak besar (satu link satu baris, boleh campur TikTok/Instagram/Threads/Facebook, boleh ratusan sekaligus).
3. Klik **Scrape & kelompokkan**. Tunggu sampai selesai (ada bar loading-nya).
4. Hasilnya dikelompokkan per akun. Kalau ada yang tidak cocok ke akun mana pun, pilih manual akunnya.
5. Klik **Simpan ke database**.

Bisa juga klik **Import link dari Excel** untuk mengambil semua link dari file Excel sekaligus.

### ④ Lihat Dashboard

Klik menu **Dashboard** → terlihat total Views, Komen, Share, Like, Repost per akun + grafik tren harian.

Tanda **`—`** artinya datanya memang tidak disediakan oleh platformnya (bukan nol, bukan error).

### ⑤ Download Excel

Klik tombol **Export** di atas → file `.xlsx` ter-download, formatnya sama seperti spreadsheet pemantauan (kolom Jumlah Interaksi sudah rumus otomatis).

### Fitur lain (boleh dicoba nanti)

- **Pengaturan → Tarik semua akun Threads**: mengambil postingan otomatis tanpa perlu tempel link, tanpa login.
- **Kelola Data**: menghapus data hasil scrape (per posting / akun / platform / periode). Daftar akun **tidak ikut terhapus**, jadi aman. Sebelum hapus besar, aplikasi membuat backup otomatis.
- **Cek Follow**: menampilkan apakah *akun admin* sudah follow tiap akun Instagram dan apakah dibalas. Butuh cookie sesi Instagram — lihat [Bagian F](#cek-follow-butuh-sesi-opsional).
- **Sesi login (opsional)**: kalau mau Facebook ikut terbaca + fitur tambahan, lihat [Bagian F](#sesi-login-opsional-1-akun-admin).

---

## Bagian D: Kalau ada error

Cari pesan error kamu di kolom kiri, ikuti cara betulkannya di kanan.

| Tandanya (pesan error) | Cara betulkan |
|---|---|
| `python is not recognized` | Python belum terinstall atau lupa centang PATH. Ulangi [Langkah 1](#langkah-1-install-python). Coba juga perintah `py app.py` sebagai pengganti |
| `git is not recognized` | Git belum terinstall. Ulangi [Langkah 2](#langkah-2-install-git), buka CMD baru |
| `pip is not recognized` | Ikut teratasi setelah Python benar (Langkah 1). Buka CMD baru |
| `No module named openpyxl` | Belum install openpyxl. Jalankan [Langkah 4](#langkah-4-install-openpyxl) |
| `Address already in use` | Port 8765 dipakai aplikasi lain. Jalankan `python app.py --port 8080` lalu buka `localhost:8080` |
| Browser tulisannya "tidak dapat terhubung / refused to connect" | Server belum jalan. Pastikan jendela CMD masih terbuka dan ada tulisan `PantauAkun jalan di ...` |
| File `.xls` lama tidak terbaca | Jalankan `pip install xlrd`. Atau buka file di Excel → Save As → pilih `.xlsx` |
| TikTok banyak yang gagal / captcha | Wajar (pertahanan anti-bot TikTok). Coba lagi lain waktu, atau naikkan jeda di menu Pengaturan |
| Facebook gagal semua | Facebook wajib login cookie. Isi di Pengaturan → Sesi login → Tes sesi (lihat Bagian F) |
| Views Threads isinya `—` | Hanya akun besar (>10rb views/bulan) + pakai cookie yang ada views-nya. Selain itu memang tidak disediakan Threads |
| Dashboard kosong / tidak ada data | Cek tanggal Periode (mungkin di luar rentang data). Lalu Input Link → Scrape → Simpan |
| Folder `data` kosong setelah download | Normal. Folder itu terisi sendiri saat aplikasi pertama kali dijalankan |
| Cek Follow: "belum ada sesi login instagram" | Fitur ini wajib cookie. Isi dulu di Pengaturan → Sesi login, lalu coba lagi |
| Cek Follow: banyak akun `❌ gagal` (HTTP 429) | Instagram sedang membatasi permintaan. Tunggu beberapa jam, naikkan jeda di Pengaturan, lalu jalankan lagi |
| Cek Follow: semua gagal walau cookie baru | Cookie kedaluwarsa. Export ulang cookie Instagram, simpan lagi di Pengaturan |
| Cek bebas: status `❔ ragu` semua | Batas halaman tercapai sebelum target ketemu. Naikkan “maks halaman”, atau pasang cookie untuk akun sumber itu |
| Cek bebas: `tidak ada sesi Instagram` | Isi sesi admin (Pengaturan → Sesi login) atau sesi per akun sekurang-kurangnya satu |
| Sesi per akun: `cookie ini milik @X, BUKAN @Y` | Salah tempel — cookie itu milik akun lain. Export ulang dari akun yang benar |

Masih buntu? Lihat file `data/app.log` (catatan error) atau ulangi dari [Bagian B](#bagian-b-menjalankan-tiap-hari) dengan CMD baru.

---

## Bagian E: Untuk pengguna Linux

Singkat saja (dianggap sudah terbiasa terminal):

```bash
# Ubuntu / Debian / Mint:
sudo apt update && sudo apt install -y python3 python3-pip git
# Fedora:
sudo dnf install -y python3 python3-pip git
# Arch:
sudo pacman -S python python-pip git

git clone https://github.com/njbaulia-wq/akun-monitor-web.git
cd akun-monitor-web
pip3 install openpyxl
python3 app.py
# buka http://localhost:8765
```

> Kalau `pip3` menolak (`externally-managed-environment`, Ubuntu 23+): pakai `pip3 install --break-system-packages openpyxl`, atau venv:
> ```bash
> python3 -m venv .venv && source .venv/bin/activate && pip install openpyxl
> ```
> Background (opsional): `nohup python3 app.py > data/app.log 2>&1 &` → hentikan: `pkill -f "python3 app.py"`.

---

## Bagian F: Keterangan tambahan

### Sesi login (opsional, 1 akun admin)

Tool **tidak pernah meminta password**. Cukup cookie dari browser kamu:

1. Login ke platformnya di Chrome seperti biasa.
2. Pasang ekstensi **Get cookies.txt LOCALLY** → klik → **Export** → simpan file `.txt`.
3. Di aplikasi: **Pengaturan → Sesi login** → upload/tempel cookie → **Simpan** → **Tes sesi**.
4. Cookie habis masa berlaku? Export ulang, simpan lagi.

| Tanpa sesi | Dengan 1 sesi admin |
|---|---|
| TikTok per link ✅ | tetap via Input Link |
| IG per link ✅ | ➕ daftar postingan per akun otomatis |
| Threads per link ✅ | ➕ view count ikut terbaca |
| Facebook ❌ | ➕ bisa baca postingan |

Cookie tersimpan **hanya** di `data/pantauakun.db` di komputermu (tidak ikut ter-upload ke GitHub).

### Cek follow (butuh sesi, opsional)

Menu **Cek Follow** punya **dua panel**:

**① Cek cepat — akun admin.** Klik **⇄ Cek follow sekarang**: untuk semua akun di daftar, ditampilkan apakah *akun admin* sudah follow dia dan apakah dia follow balik. Ini jalur termurah (1 request per akun).

| Status | Artinya |
|---|---|
| ✅ Saling follow | akun admin follow dia, dia follow balik |
| → Admin follow, belum balik | kamu sudah follow, dia belum follow back |
| ← Mereka follow, admin belum | dia follow kamu, kamu belum follow dia |
| ✖ Belum saling follow | dua-duanya tidak saling follow |
| ⏳ Menunggu izin (privat) | permintaan follow masih menunggu persetujuan |
| ❌ Gagal dicek | sesi habis / kena rate-limit / akun hilang — lihat *Catatan* |
| ◦ Belum dicek | belum pernah dijalankan |

**② Cek bebas — pilih akun sumber.** Pilih akun sumber (boleh **bukan** akun admin — satu akun tertentu atau semua akun), ketik **username target**, lalu klik **🔎 Cek**. Aplikasi menjawab: *"apakah akun sumber ini sudah follow target?"*

Cara kerjanya (hybrid, otomatis):

| Kondisi akun sumber | Cara yang dipakai | Biaya |
|---|---|---|
| punya cookie sendiri | `friendships/show` | 1 request — jawaban pasti |
| tidak punya cookie | baca daftar "following"-nya halaman demi halaman | 1 request per halaman (≈24–50 orang/halaman) |

Kalau batas **maks halaman** tercapai tapi target belum ketemu, statusnya **❔ ragu** — artinya *tidak ditemukan dalam N halaman pertama*, **bukan** "tidak follow". Naikkan "maks halaman" kalau akun sumbernya mengikuti banyak orang.

**Sesi per akun** (Pengaturan → *Sesi per akun*): simpan cookie milik satu akun tertentu supaya panel ② cukup 1 request. Ada pengaman — saat disimpan, aplikasi langsung memeriksa apakah cookie itu **benar-benar milik akun tersebut**; kalau salah tempel, langsung ditolak.

**Yang wajib kamu pahami (jujur, tanpa dilebih-lebihkan):**

1. **Butuh minimal satu cookie Instagram.** Instagram tidak menyediakan data follow tanpa login — tidak ada jalan lain. Tanpa sesi sama sekali, kedua panel tidak jalan.
2. **Ini bukan API resmi.** Memakai jalur internal Instagram, di luar ToS Instagram. Risikonya nyata: **akun yang cookie-nya dipakai bisa kena rate-limit sampai pembatasan.** Aplikasi sudah memberi jeda sopan, tetapi risiko tetap milikmu.
3. **Panel ② jauh lebih berat** daripada panel ① kalau akun sumbernya tidak punya cookie. Jangan dipakai untuk semua 58 akun berkali-kali sehari.
4. **Jangan terlalu sering.** Cukup 1× per minggu/bulan. Kalau banyak `❌ gagal` dengan keterangan HTTP 429, hentikan beberapa jam lalu ulangi.

### Link yang dikenali

- TikTok: `tiktok.com/ZSxxx`, `vt./vm.tiktok.com/…`, `@user/video/<id>`, `@user/photo/<id>`
- Instagram: `/reel/<kode>/`, `/p/<kode>/`
- Threads: `/share/…`, `@user/post/<kode>`
- Facebook: `/share/…`, `/posts/…`, `/watch`, `/reel/`, `/videos/…`, `/photo`, `fb.watch/…` (butuh cookie)

### Batasan jujur (sel kosong = tidak disediakan platform, bukan error)

| Metrik | TikTok | Instagram | Threads | Facebook |
|---|---|---|---|---|
| Tanggal | ✅ | ✅ (hari saja) | ✅ | ✅ |
| Views | ✅ | ✅ (reel/video) | ⚠️ akun besar + cookie | ❌ tidak ada |
| Like / Komen | ✅ | ✅ | ✅ | ✅ |
| Share | ✅ | ❌ | ❌ | ✅ |
| Repost | ❌ | ❌ | ✅ | ❌ |

### Isi folder

```
akun-monitor-web/
├── app.py            # program utama (server, tanpa framework)
├── db.py             # database SQLite
├── scrape.py         # pembaca tiap platform
├── fetchers/         # pembaca tiktok / instagram / threads
├── session.py        # urusan cookie login
├── exporter.py       # pembuat file Excel
├── sheetio.py        # pembaca file Excel/CSV
├── accounts.csv      # CONTOH 5 akun (nanti terganti datamu)
├── cek_facebook.py   # tes koneksi Facebook
├── web/              # tampilan (jangan diubah kalau tidak perlu)
├── data/             # database — dibuat otomatis, TIDAK ikut ke GitHub
└── .gitignore        # daftar file yang tidak ikut ke GitHub
```

Hapus `data/pantauakun.db` kalau mau mulai dari nol total.

---

*Tips: scrape cukup 1x per pekan untuk pemakaian rutin. Aplikasi memberi jeda otomatis supaya tidak membanjiri platform.*
