#!/usr/bin/env python3
"""Lapisan database SQLite untuk PantauAkun.

Satu file: data/pantauakun.db (dibuat otomatis saat pertama jalan).
Tabel:
  accounts(id, kode, platform, username, link_profile, created_at)
  posts(id, account_id, platform, url, post_key, author, posted_at, caption, created_at)
  metrics(id, post_id, scraped_at, views, komen, share, like, repost)
  settings(key, value)
"""
import os
import datetime
import sqlite3
import threading

import wibtime as wib

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "data", "pantauakun.db")

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kode TEXT,
    platform TEXT NOT NULL,
    username TEXT NOT NULL,
    link_profile TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(platform, username)
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    post_key TEXT,
    author TEXT,
    posted_at TEXT,
    caption TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    scraped_at TEXT DEFAULT (datetime('now')),
    views INTEGER,
    komen INTEGER,
    share INTEGER,
    like INTEGER,
    repost INTEGER
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- Status follow (relasi tiap akun terhadap akun PEMILIK SESI / admin).
-- Instagram tidak mengekspos relasi follow secara publik, jadi tabel ini
-- hanya terisi kalau cookie sesi Instagram diisi (lihat scrape.py).
CREATE TABLE IF NOT EXISTS follow_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL UNIQUE
        REFERENCES accounts(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    target_user_id TEXT,
    following INTEGER,          -- 1 akun admin sudah follow target
    followed_by INTEGER,        -- 1 target follow balik akun admin
    outgoing_request INTEGER,   -- permintaan follow masih menunggu
    incoming_request INTEGER,   -- target minta follow admin
    is_private INTEGER,
    follower_count INTEGER,
    following_count INTEGER,
    error TEXT,                 -- terisi kalau gagal dicek
    checked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_posts_account ON posts(account_id);
-- Sesi (cookie) PER AKUN: dibutuhkan "cek follow" dengan akun sumber bebas.
-- Cookie disimpan lokal dan ikut terhapus otomatis saat akunnya dihapus
-- (ON DELETE CASCADE) supaya tidak ada kredensial yatim.
CREATE TABLE IF NOT EXISTS account_session (
    account_id INTEGER PRIMARY KEY
        REFERENCES accounts(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    cookies TEXT NOT NULL,
    saved_at TEXT
);
-- Cache id numerik Instagram per akun. Menghemat 1 request setiap kali cek.
CREATE TABLE IF NOT EXISTS ig_user_cache (
    account_id INTEGER PRIMARY KEY
        REFERENCES accounts(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    username TEXT,
    follower_count INTEGER,
    following_count INTEGER,
    is_private INTEGER,
    cached_at TEXT
);
-- Hasil cek follow "akun sumber -> target bebas" (satu baris per akun sumber).
CREATE TABLE IF NOT EXISTS follow_scan (
    account_id INTEGER PRIMARY KEY
        REFERENCES accounts(id) ON DELETE CASCADE,   -- akun SUMBER
    platform TEXT NOT NULL,
    target_username TEXT,
    target_user_id TEXT,
    state TEXT,           -- follow | tidak | ragu
    method TEXT,          -- cookie (1 request) | daftar (baca following)
    pages INTEGER DEFAULT 0,
    following_count INTEGER,
    follower_count INTEGER,
    is_private INTEGER,
    error TEXT,
    checked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_follow_scan_target ON follow_scan(target_username);
CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(posted_at);
CREATE INDEX IF NOT EXISTS idx_metrics_post ON metrics(post_id);
"""


_dir_ready = False
# File ini menyimpan COOKIE SESI platform (Instagram/Threads/Facebook) yang
# setara password untuk akun admin. Standar umum: file rahasia 0600 (owner
# saja), folder 0700. Tanpa ini, user lain di mesin yang sama bisa membacanya
# (terukur 2026-10-12: data/pantauakun.db mode 644).
DB_FILE_MODE = 0o600
DB_DIR_MODE = 0o700


def _tighten_permissions():
    """Kunci izin file DB & folder data jadi hanya untuk pemilik."""
    try:
        d = os.path.dirname(DB_PATH)
        if os.path.isdir(d):
            os.chmod(d, DB_DIR_MODE)
        if os.path.exists(DB_PATH):
            os.chmod(DB_PATH, DB_FILE_MODE)
    except (OSError, PermissionError):
        # Di filesystem yang tidak mendukung (mis.sejenis network mount) ini
        # boleh gagal — bukan alasan menghentikan aplikasi.
        pass


def _enable_wal(conn):
    """SQLite WAL: ~2-5x throughput tulis & reader tidak terblokir writer.

    Tanpa ini journal_mode=delete: setiap commit mengunci seluruh DB, jadi
    dashboard (baca) dan scraping (tulis) saling menunggu.
    """
    try:
        cur = conn.execute("PRAGMA journal_mode=WAL")
        if str(cur.fetchone()[0]).lower() == "wal":
            conn.execute("PRAGMA synchronous=NORMAL")
            return True
    except sqlite3.Error:
        pass
    return False


def connect():
    global _dir_ready
    # makedirs hanya sekali. Versi lama memanggilnya di SETIAP koneksi —
    # dashboard() membuka 1382 koneksi, jadi 1382 syscall sia-sia per request.
    if not _dir_ready:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _dir_ready = True
        _tighten_permissions()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # synchronous bersifat PER-KONEKSI (tidak disimpan di file), jadi harus
    # diulang di sini — hanya 설정 di init() tidak berlaku untuk request
    # berikutnya yang membuka koneksi baru.
    try:
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.Error:
        pass
    return conn


def init():
    with _lock:
        conn = connect()
        try:
            _enable_wal(conn)
            conn.executescript(SCHEMA)
            # indeks pendukung: dashboard memfilter per tanggal + per akun
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_acct_date "
                         "ON posts(account_id, posted_at)")
            # statistik query: query planner memilih lebih baik otomatis
            # pada tabel yang tumbuh (terutama posting & metrik).
            conn.execute("ANALYZE")
            # default settings
            defaults = {
                "scrape_delay": "2",      # detik antar request
                "week_start": "monday",   # pekan dimulai Senin
                "lane_workers": "3",      # worker paralel per lane (1-4)
            }
            for k, v in defaults.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
                    (k, v))
            conn.commit()
        finally:
            conn.close()
    _tighten_permissions()


def q(sql, args=(), one=False):
    """SELECT helper -> list[dict] / dict / None."""
    with _lock:
        conn = connect()
        try:
            cur = conn.execute(sql, args)
            rows = cur.fetchall()
            out = [dict(r) for r in rows]
            return out[0] if one and out else (None if one else out)
        finally:
            conn.close()


def run(sql, args=()):
    """INSERT/UPDATE/DELETE -> lastrowid."""
    with _lock:
        conn = connect()
        try:
            cur = conn.execute(sql, args)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def runmany(sql, seq):
    with _lock:
        conn = connect()
        try:
            conn.executemany(sql, seq)
            conn.commit()
        finally:
            conn.close()


def get_setting(key, default=None):
    r = q("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return r["value"] if r else default


def set_setting(key, value):
    run("INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


# ---------- accounts ----------

def list_accounts(platform=None):
    if platform:
        return q("SELECT * FROM accounts WHERE platform=? ORDER BY kode, username",
                 (platform,))
    return q("SELECT * FROM accounts ORDER BY platform, kode, username")


def add_account(kode, platform, username, link_profile=""):
    username = username.strip().lstrip("@")
    return run("INSERT INTO accounts(kode, platform, username, link_profile) "
               "VALUES(?,?,?,?) ON CONFLICT(platform, username) DO UPDATE SET "
               "kode=excluded.kode, link_profile=excluded.link_profile",
               (kode, platform, username, link_profile))


def get_account(acc_id):
    """Satu akun berdasarkan id (dict) atau None."""
    return q("SELECT * FROM accounts WHERE id=?", (acc_id,), one=True)


def find_account(platform, username):
    if not username:
        return None
    return q("SELECT * FROM accounts WHERE platform=? AND lower(username)=lower(?)",
             (platform, username.strip().lstrip("@")), one=True)


def find_account_by_profile_id(platform, profile_id):
    """Cari akun lewat id profil di link_profile (mis. profile.php?id=...).

    Facebook tidak selalu mengirim NAMA penulis di halaman (terukur:
    /share/v/ sama sekali tidak memuat nama pengirim), tapi id profilnya
    selalu ada di URL story.php?id=12345678900000. Tanpa ini, posting
    Facebook tertentu tidak pernahepasangkan ke akun mana pun.
    """
    if not profile_id or platform != "facebook":
        return None
    pid = str(profile_id).strip()
    if not pid.isdigit():
        return None
    # Cocokkan bagian paling kanan: link_profile bisa punya ?id=..&__cft__=..
    r = q("SELECT * FROM accounts WHERE platform='facebook' AND link_profile "
          "LIKE ? ORDER BY id LIMIT 1", ("%" + pid + "%",), one=True)
    if r:
        return r
    return q("SELECT * FROM accounts WHERE platform='facebook' AND "
             "(username=? OR link_profile LIKE ?) LIMIT 1",
            (pid, "%/" + pid + "%"), one=True)


def delete_account(acc_id):
    run("DELETE FROM accounts WHERE id=?", (acc_id,))


# ---------------- hapus akun massal ----------------

def account_post_counts(ids=None):
    """{account_id: jumlah posting} untuk daftar akun (id=None = semua).

    Dipakai tabel Akun supaya user tahu berapa posting yang ikut hilang
    sebelum menekan hapus, dan dipakai endpoint hapus massal untuk
    menghitung dampaknya.
    """
    if ids:
        marks = ",".join("?" * len(ids))
        rows = q(f"SELECT account_id, COUNT(*) c FROM posts "
                 f"WHERE account_id IN ({marks}) GROUP BY account_id", tuple(ids))
    else:
        rows = q("SELECT account_id, COUNT(*) c FROM posts GROUP BY account_id")
    return {r["account_id"]: r["c"] for r in rows if r["account_id"] is not None}


def count_accounts_deletable(ids=None, platform=None):
    """Ringkasan dampak: berapa akun / posting / metrik akan terhapus.

    Dipakai untuk konfirmasi di UI. Metrik dihitung lewat post_id agar sama
    persis dengan yang akan hilang.
    """
    if ids:
        marks = ",".join("?" * len(ids))
        w_acc, w_post = f"id IN ({marks})", f"account_id IN ({marks})"
    else:
        w_acc = "1=1"
        w_post = "platform=?" if platform else "1=1"
        if platform:
            w_acc = "platform=?"
    args = tuple(ids) if ids else ((platform,) if platform else ())
    n_acc = q(f"SELECT COUNT(*) c FROM accounts WHERE {w_acc}", args, one=True)["c"]
    n_post = q(f"SELECT COUNT(*) c FROM posts WHERE {w_post}", args, one=True)["c"]
    n_met = q(f"SELECT COUNT(*) c FROM metrics WHERE post_id IN "
              f"(SELECT id FROM posts WHERE {w_post})", args, one=True)["c"]
    return {"accounts": n_acc, "posts": n_post, "metrics": n_met}


def delete_accounts(ids=None, platform=None):
    """Hapus akun (posting + metrik ikut terhapus lewat CASCADE).

    ids=None + platform=... -> hapus semua akun platform itu.
    Keduanya None           -> hapus SEMUA akun.

    posts.account_id memakai ON DELETE CASCADE dan PRAGMA foreign_keys=ON
    (lihat connect()), jadi posting & metrik benar-benar ikut terhapus —
    diverifikasi 2026-10-11: akun 1 + 1 post + 1 metrik -> semua 0.

    Semua dalam SATU koneksi/transaksi: db.run() membuka koneksi baru tiap
    panggilan, jadi BEGIN/COMMIT lintas panggilan tidak berlaku (bug yang
    sempat terjadi saat migrasi WIB).
    """
    if ids:
        marks = ",".join("?" * len(ids))
        where, args = f"id IN ({marks})", tuple(ids)
    else:
        where, args = ("platform=?", (platform,)) if platform else ("1=1", ())
    ringkasan = count_accounts_deletable(ids, platform)
    if not ringkasan["accounts"]:
        return ringkasan
    with _lock:
        conn = connect()
        try:
            conn.execute("BEGIN")
            conn.execute(f"DELETE FROM accounts WHERE {where}", args)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    return ringkasan


# ---------------- hapus data scrape (akun TIDAK ikut terhapus) ----------------
# Semua fungsi di bawah hanya menghapus posts + metrics. Akun tetap utuh
# supaya tidak perlu import Excel ulang setelah reset.

def _scope_where(scope, platform=None, account_id=None, sejak=None, sampai=None):
    """Bentuk WHERE + argumen untuk cakupan hapus/penghitungan.

    scope: 'post' | 'account' | 'platform' | 'periode' | 'all'
    """
    if scope == "post":
        return "id=?", (account_id,)          # account_id = post_id
    if scope == "account":
        return "account_id=?", (account_id,)
    if scope == "platform":
        return "platform=?", (platform,)
    if scope == "periode":
        return "substr(posted_at,1,10) BETWEEN ? AND ?", (sejak, sampai)
    return "1=1", ()                          # 'all'


def count_posts(scope, platform=None, account_id=None, sejak=None, sampai=None):
    """Berapa SADposting + metrik yang akan terpengaruh (untuk konfirmasi)."""
    w, a = _scope_where(scope, platform, account_id, sejak, sampai)
    n_posts = q(f"SELECT COUNT(*) c FROM posts WHERE {w}", a, one=True)["c"]
    n_metrics = q(
        f"SELECT COUNT(*) c FROM metrics WHERE post_id IN "
        f"(SELECT id FROM posts WHERE {w})", a, one=True)["c"]
    out = {"posts": n_posts, "metrics": n_metrics}
    # 'all' = seluruh data hasil scrape, jadi hasil cek follow ikut dihitung
    # supaya jumlah di dialog konfirmasi tidak menyesatkan.
    if scope == "all":
        def _c(tabel):
            if platform:
                return q(f"SELECT COUNT(*) c FROM {tabel} WHERE platform=?",
                         (platform,), one=True)["c"]
            return q(f"SELECT COUNT(*) c FROM {tabel} "
                     f"WHERE checked_at IS NOT NULL", one=True)["c"]
        out["follows"] = _c("follow_status") + _c("follow_scan")
    return out


def delete_posts(scope, platform=None, account_id=None, sejak=None, sampai=None):
    """Hapus posting + metrik sesuai cakupan. AKUN TIDAK IKUT TERHAPUS.

    Metrik hilang otomatis lewat ON DELETE CASCADE.
    scope='all' juga mengosongkan hasil cek follow (itu data hasil scrape).
    """
    w, a = _scope_where(scope, platform, account_id, sejak, sampai)
    n = count_posts(scope, platform, account_id, sejak, sampai)
    run(f"DELETE FROM posts WHERE {w}", a)
    if scope == "all":
        clear_follow_status(platform)
        clear_follow_scan(platform)
    return n


# ---------------- status follow (relasi vs akun sesi/admin) ----------------

def save_follow_status(account_id, platform, target_user_id, following,
                       followed_by, outgoing_request=None,
                       incoming_request=None, is_private=None, error=None,
                       follower_count=None, following_count=None):
    """Simpan hasil cek follow satu akun (upsert: 1 baris per akun).

    Boolean disimpan sebagai 0/1; None tetap None (Instagram tidak mengirim
    field itu) supaya UI bisa membedakan "tidak" dari "tidak diketahui".
    checked_at memakai WIB, konsisten dengan posted_at.
    """
    b = lambda v: None if v is None else (1 if v else 0)  # noqa: E731
    return run(
        "INSERT INTO follow_status(account_id, platform, target_user_id,"
        " following, followed_by, outgoing_request, incoming_request,"
        " is_private, follower_count, following_count, error, checked_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(account_id) DO UPDATE SET"
        " platform=excluded.platform, target_user_id=excluded.target_user_id,"
        " following=excluded.following, followed_by=excluded.followed_by,"
        " outgoing_request=excluded.outgoing_request,"
        " incoming_request=excluded.incoming_request,"
        " is_private=excluded.is_private,"
        " follower_count=excluded.follower_count,"
        " following_count=excluded.following_count, error=excluded.error,"
        " checked_at=excluded.checked_at",
        (account_id, platform, target_user_id, b(following), b(followed_by),
         b(outgoing_request), b(incoming_request), b(is_private),
         follower_count, following_count, error,
         wib.now_wib().strftime("%Y-%m-%d %H:%M:%S")))


def list_follow_status(platform=None):
    """Semua akun + status follow-nya (LEFT JOIN).

    LEFT JOIN dipakai supaya akun yang BELUM pernah dicek tetap muncul
    sebagai baris dengan checked_at NULL — bukan hilang dari tabel.
    """
    where = "WHERE a.platform=?" if platform else ""
    args = (platform,) if platform else ()
    return q(f"""
        SELECT a.id AS account_id, a.kode, a.platform, a.username,
               f.target_user_id, f.following, f.followed_by,
               f.outgoing_request, f.incoming_request, f.is_private,
               f.follower_count, f.following_count, f.error, f.checked_at
        FROM accounts a
        LEFT JOIN follow_status f ON f.account_id = a.id
        {where}
        ORDER BY a.kode, a.username
    """, args)


def follow_counts(platform="instagram"):
    """Ringkasan: berapa akun yang sudah dicek & status dominannya."""
    rows = list_follow_status(platform)
    n = {"total": len(rows), "checked": 0, "mutual": 0, "following": 0,
         "followed_by": 0, "none": 0, "pending": 0, "error": 0, "unchecked": 0}
    for r in rows:
        if r["error"]:
            n["error"] += 1
            continue
        if not r["checked_at"]:
            n["unchecked"] += 1
            continue
        n["checked"] += 1
        if r["outgoing_request"]:
            n["pending"] += 1
        elif r["following"] and r["followed_by"]:
            n["mutual"] += 1
        elif r["following"]:
            n["following"] += 1
        elif r["followed_by"]:
            n["followed_by"] += 1
        else:
            n["none"] += 1
    return n


def clear_follow_status(platform=None):
    """Hapus hasil cek follow (akun tetap)."""
    if platform:
        return run("DELETE FROM follow_status WHERE platform=?", (platform,))
    return run("DELETE FROM follow_status")


# ---------------- sesi per akun (untuk cek follow sumber bebas) ----------------

def save_account_session(account_id, platform, cookies_raw):
    """Simpan cookie sesi milik SATU akun (cookies_raw = JSON string)."""
    return run(
        "INSERT INTO account_session(account_id, platform, cookies, saved_at)"
        " VALUES(?,?,?,?)"
        " ON CONFLICT(account_id) DO UPDATE SET platform=excluded.platform,"
        " cookies=excluded.cookies, saved_at=excluded.saved_at",
        (account_id, platform, cookies_raw,
         wib.now_wib().strftime("%Y-%m-%d %H:%M:%S")))


def get_account_session(account_id):
    """Cookie mentah (JSON string) milik satu akun, atau None."""
    r = q("SELECT cookies FROM account_session WHERE account_id=?",
          (account_id,), one=True)
    return r["cookies"] if r else None


def list_account_sessions(platform=None):
    """Akun yang punya cookie — TANPA isi cookie-nya.

    Sengaja tidak mengembalikan nilai cookie supaya kredensial tidak ikut
    terkirim ke browser/halaman Pengaturan.
    """
    where = "WHERE platform=?" if platform else ""
    args = (platform,) if platform else ()
    return q(f"SELECT account_id, platform, saved_at FROM account_session "
             f"{where} ORDER BY saved_at DESC", args)


def clear_account_session(account_id):
    return run("DELETE FROM account_session WHERE account_id=?", (account_id,))


# ---------------- cache id numerik Instagram per akun ----------------

def save_ig_cache(account_id, user_id, username=None, follower_count=None,
                  following_count=None, is_private=None):
    b = lambda v: None if v is None else (1 if v else 0)  # noqa: E731
    return run(
        "INSERT INTO ig_user_cache(account_id, user_id, username,"
        " follower_count, following_count, is_private, cached_at)"
        " VALUES(?,?,?,?,?,?,?)"
        " ON CONFLICT(account_id) DO UPDATE SET user_id=excluded.user_id,"
        " username=excluded.username,"
        " follower_count=excluded.follower_count,"
        " following_count=excluded.following_count,"
        " is_private=excluded.is_private, cached_at=excluded.cached_at",
        (account_id, str(user_id), username, follower_count, following_count,
         b(is_private), wib.now_wib().strftime("%Y-%m-%d %H:%M:%S")))


def get_ig_cache(account_id):
    return q("SELECT * FROM ig_user_cache WHERE account_id=?",
             (account_id,), one=True)


# ---------------- hasil cek follow "sumber -> target bebas" ----------------

def save_follow_scan(account_id, platform, target_username, target_user_id,
                     state, method=None, pages=0, following_count=None,
                     follower_count=None, is_private=None, error=None):
    b = lambda v: None if v is None else (1 if v else 0)  # noqa: E731
    return run(
        "INSERT INTO follow_scan(account_id, platform, target_username,"
        " target_user_id, state, method, pages, following_count,"
        " follower_count, is_private, error, checked_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(account_id) DO UPDATE SET"
        " platform=excluded.platform,"
        " target_username=excluded.target_username,"
        " target_user_id=excluded.target_user_id, state=excluded.state,"
        " method=excluded.method, pages=excluded.pages,"
        " following_count=excluded.following_count,"
        " follower_count=excluded.follower_count,"
        " is_private=excluded.is_private, error=excluded.error,"
        " checked_at=excluded.checked_at",
        (account_id, platform, target_username, target_user_id, state, method,
         pages, following_count, follower_count, b(is_private), error,
         wib.now_wib().strftime("%Y-%m-%d %H:%M:%S")))


def list_follow_scan(platform=None, target_username=None):
    """Semua akun + hasil cek terakhirnya (LEFT JOIN, akun belum-dicek tetap tampil)."""
    clauses, args = [], []
    if platform:
        clauses.append("a.platform=?")
        args.append(platform)
    if target_username:
        clauses.append("(s.target_username=? OR s.target_username IS NULL)")
        args.append(target_username)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return q(f"""
        SELECT a.id AS account_id, a.kode, a.platform, a.username,
               s.target_username, s.state, s.method, s.pages,
               s.following_count, s.follower_count, s.is_private, s.error,
               s.checked_at,
               (SELECT 1 FROM account_session cs WHERE cs.account_id=a.id
                LIMIT 1) AS punya_cookie
        FROM accounts a
        LEFT JOIN follow_scan s ON s.account_id = a.id
        {where}
        ORDER BY a.kode, a.username
    """, tuple(args))


def follow_scan_counts(platform="instagram", target_username=None):
    rows = list_follow_scan(platform, target_username)
    n = {"total": len(rows), "follow": 0, "tidak": 0, "ragu": 0,
         "error": 0, "unchecked": 0, "cookie": 0, "daftar": 0}
    for r in rows:
        if r["error"]:
            n["error"] += 1
            continue
        if not r["checked_at"]:
            n["unchecked"] += 1
            continue
        if r["state"] == "follow":
            n["follow"] += 1
        elif r["state"] == "tidak":
            n["tidak"] += 1
        else:
            n["ragu"] += 1
        if r["method"] == "cookie":
            n["cookie"] += 1
        elif r["method"] == "daftar":
            n["daftar"] += 1
    return n


def clear_follow_scan(platform=None):
    if platform:
        return run("DELETE FROM follow_scan WHERE platform=?", (platform,))
    return run("DELETE FROM follow_scan")


def post_history(post_id):
    """Riwayat snapshot metrik satu posting (lama -> baru) + pertumbuhannya."""
    rows = q("SELECT scraped_at, views, komen, share, like, repost "
             "FROM metrics WHERE post_id=? ORDER BY id", (post_id,))
    snap = []
    for i, r in enumerate(rows):
        s = dict(r)
        if i:                                   # delta vs snapshot sebelumnya
            prev = rows[i - 1]
            s["delta"] = {
                k: (None if r[k] is None or prev[k] is None else r[k] - prev[k])
                for k in ("views", "like", "komen", "share", "repost")}
        else:
            s["delta"] = None
        snap.append(s)
    return snap


BACKUP_KEEP = 10        # berapa backup terbaru yang disimpan


def backup_db(tag=""):
    """Salin file database ke data/backup-<tag>.db. Return path.

    Backup lama yang melebihi BACKUP_KEEP dihapus otomatis. Tanpa ini file
    backup menumpuk tanpa batas (terukur 12 file / 8 MB dan bertambah setiap
    kali hapus massal) sampai memakan disk.
    """
    import shutil
    if not os.path.exists(DB_PATH):
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dstdir = os.path.dirname(DB_PATH)
    dst = os.path.join(dstdir, f"backup-{stamp}{tag}.db")
    shutil.copy2(DB_PATH, dst)
    try:
        os.chmod(dst, DB_FILE_MODE)
    except OSError:
        pass
    prune_backups()
    return dst


def prune_backups(keep=None):
    """Hapus backup paling lama, sisakan `keep` (default BACKUP_KEEP)."""
    keep = BACKUP_KEEP if keep is None else keep
    d = os.path.dirname(DB_PATH)
    try:
        files = [f for f in os.listdir(d)
                 if f.startswith("backup-") and f.endswith(".db")]
    except OSError:
        return 0
    if len(files) <= keep:
        return 0
    files.sort(key=lambda f: os.path.getmtime(os.path.join(d, f)))
    dihapus = 0
    for f in files[:len(files) - keep]:
        try:
            os.remove(os.path.join(d, f))
            dihapus += 1
        except OSError:
            pass
    return dihapus


def list_backups():
    """[{nama, ukuran, waktu}] terbaru dulu — untuk UI."""
    d = os.path.dirname(DB_PATH)
    out = []
    try:
        files = [f for f in os.listdir(d)
                 if f.startswith("backup-") and f.endswith(".db")]
    except OSError:
        return out
    for f in files:
        p = os.path.join(d, f)
        try:
            st = os.stat(p)
        except OSError:
            continue
        out.append({"nama": f, "bytes": st.st_size,
                    "waktu": datetime.datetime.fromtimestamp(
                        st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")})
    out.sort(key=lambda x: x["waktu"], reverse=True)
    return out


def trend(sejak, sampai, platform=None):
    """Interaksi per HARI untuk sparkline tren.

    Snapshot TERBARU tiap posting, sama aturan dengan dashboard().
    """
    args = [sejak, sampai]
    where = ""
    if platform:
        where = " AND platform=?"          # tanpa alias "p." (tabel tidak di-alias)
        args.append(platform)
    rows = q(f"""
        SELECT substr(posted_at,1,10) AS hari, COUNT(*) AS n_post
        FROM posts
        WHERE substr(posted_at,1,10) BETWEEN ? AND ?{where}
        GROUP BY hari ORDER BY hari
    """, args)
    n_by_hari = {r["hari"]: r["n_post"] for r in rows}
    ids = q(f"""
        SELECT id, substr(posted_at,1,10) AS hari FROM posts
        WHERE substr(posted_at,1,10) BETWEEN ? AND ?{where}
    """, args)
    per_hari = {}
    for r in ids:
        per_hari.setdefault(r["hari"], []).append(r["id"])
    semua = latest_metrics_map([i for lst in per_hari.values() for i in lst])
    out, d = [], datetime.date.fromisoformat(sejak)
    akhir = datetime.date.fromisoformat(sampai)
    while d <= akhir:
        key = d.isoformat()
        inter = like = 0
        for pid in per_hari.get(key, []):
            m = semua.get(pid)
            if not m:
                continue
            inter += ((m["views"] or 0) + (m["komen"] or 0) + (m["share"] or 0)
                      + (m["like"] or 0) + (m["repost"] or 0))
            like += m["like"] or 0
        out.append({"hari": key, "interaksi": inter, "like": like,
                    "n_post": n_by_hari.get(key, 0)})
        d += datetime.timedelta(days=1)
    return out


def count_accounts():
    r = q("SELECT platform, COUNT(*) c FROM accounts GROUP BY platform")
    return {x["platform"]: x["c"] for x in r}


def urls_exist(urls):
    """Kembalikan set URL yang sudah ada di tabel posts (deteksi duplikat)."""
    out = set()
    urls = [u for u in urls if u]
    for i in range(0, len(urls), 500):
        chunk = urls[i:i + 500]
        ph = ",".join("?" * len(chunk))
        for r in q(f"SELECT url FROM posts WHERE url IN ({ph})", tuple(chunk)):
            out.add(r["url"])
    return out


def keys_exist(pairs):
    """pairs=[(platform, post_key)] -> set pasangan yang sudah ada.

    Identitas postingan yang tahan terhadap bentuk URL berbeda
    (link pendek vs link hasil resolve).
    """
    out = set()
    pairs = [(p, k) for p, k in pairs if p and k]
    for i in range(0, len(pairs), 500):
        chunk = pairs[i:i + 500]
        cond = " OR ".join(["(platform=? AND post_key=?)"] * len(chunk))
        args = [x for pr in chunk for x in pr]
        for r in q(f"SELECT platform, post_key FROM posts WHERE {cond}",
                   tuple(args)):
            out.add((r["platform"], r["post_key"]))
    return out


# ---------- posts & metrics ----------

def add_post(account_id, platform, url, post_key="", author="",
             posted_at=None, caption=""):
    return run(
        "INSERT INTO posts(account_id, platform, url, post_key, author, posted_at, caption)"
        " VALUES(?,?,?,?,?,?,?)"
        " ON CONFLICT(url) DO UPDATE SET account_id=excluded.account_id,"
        " author=excluded.author, posted_at=excluded.posted_at,"
        " caption=excluded.caption",
        (account_id, platform, url, post_key, author, posted_at, caption))


def upsert_post(account_id, platform, url, post_key="", author="",
                posted_at=None, caption=""):
    """Satu postingan fisik = satu baris DB.

    Identitas utama: (platform, post_key) — tahan terhadap bentuk URL
    berbeda (link pendek vs hasil resolve). Fallback: url.
    Mengembalikan (post_id, is_new). Baris lama diperbarui, tidak didobel.
    """
    pid = None
    if post_key:
        r = q("SELECT id FROM posts WHERE platform=? AND post_key=?",
              (platform, post_key), one=True)
        if r:
            pid = r["id"]
    if pid is None:
        r = q("SELECT id FROM posts WHERE url=?", (url,), one=True)
        if r:
            pid = r["id"]
    if pid:
        run("UPDATE posts SET account_id=?, platform=?, url=?, post_key=?,"
            " author=?, posted_at=?, caption=? WHERE id=?",
            (account_id, platform, url, post_key, author, posted_at,
             caption, pid))
        return pid, False
    return run(
        "INSERT INTO posts(account_id, platform, url, post_key, author,"
        " posted_at, caption) VALUES(?,?,?,?,?,?,?)",
        (account_id, platform, url, post_key, author, posted_at, caption)), True


def add_metrics(post_id, views=None, komen=None, share=None, like=None,
                repost=None):
    return run(
        "INSERT INTO metrics(post_id, views, komen, share, like, repost)"
        " VALUES(?,?,?,?,?,?)",
        (post_id, views, komen, share, like, repost))


def latest_metrics(post_id):
    return q("SELECT * FROM metrics WHERE post_id=? ORDER BY id DESC LIMIT 1",
             (post_id,), one=True)


def latest_metrics_map(post_ids):
    """{post_id: snapshot terbaru} untuk banyak sekalian — SATU query.

    Mengganti pola N+1 di dashboard(): versi lama memanggil latest_metrics()
    per posting, jadi satu permintaan dashboard membuka 1382 koneksi SQLite
    (terukur 2026-10-11). Sekarang satu query window function.

    Fallback ke GROUP BY id MAX(id) bila SQLite < 3.25 (tanpa window function).
    """
    ids = [i for i in set(post_ids or ()) if i is not None]
    if not ids:
        return {}
    out = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        marks = ",".join("?" * len(chunk))
        try:
            rows = q(f"""
                SELECT post_id, views, komen, share, like, repost FROM (
                    SELECT post_id, views, komen, share, like, repost,
                           ROW_NUMBER() OVER (PARTITION BY post_id
                                              ORDER BY id DESC) rn
                    FROM metrics WHERE post_id IN ({marks})
                ) WHERE rn=1""", tuple(chunk))
        except sqlite3.OperationalError:
            rows = q(f"""
                SELECT m.* FROM metrics m JOIN (
                    SELECT post_id, MAX(id) mid FROM metrics
                    WHERE post_id IN ({marks}) GROUP BY post_id
                ) t ON m.id = t.mid""", tuple(chunk))
        for r in rows:
            out[r["post_id"]] = r
    return out


def dashboard(sejak, sampai, platform=None):
    """Agregat per akun untuk rentang tanggal (posted_at, format YYYY-MM-DD).

    Metrik tiap postingan = snapshot TERBARU. Hanya postingan yang tanggalnya
    masuk rentang yang dihitung.

    WAJIB lewat latest_metrics_map() (satu query), bukan latest_metrics() per
    posting: pola lama membuka satu koneksi SQLite per posting dan membuat
    dashboard 1381 koneksi untuk satu permintaan.
    """
    where = "WHERE a.platform=?" if platform else ""
    args = [sejak, sampai]
    if platform:
        args.append(platform)
    rows = q(f"""
        SELECT a.id AS account_id, a.kode, a.platform, a.username,
               p.id AS post_id, p.posted_at
        FROM accounts a
        LEFT JOIN posts p ON p.account_id = a.id
            AND substr(p.posted_at, 1, 10) BETWEEN ? AND ?
        {where}
        ORDER BY a.platform, a.kode, a.username
    """, args)

    metrik = latest_metrics_map([r["post_id"] for r in rows if r["post_id"]])
    agg = {}
    for r in rows:
        key = r["account_id"]
        if key not in agg:
            agg[key] = {"account_id": key, "kode": r["kode"],
                        "platform": r["platform"], "username": r["username"],
                        "n_post": 0, "views": 0, "komen": 0, "share": 0,
                        "like": 0, "repost": 0,
                        "has_views": False, "has_share": False,
                        "has_repost": False}
        if not r["post_id"]:
            continue
        m = metrik.get(r["post_id"])
        if not m:
            continue
        a = agg[key]
        a["n_post"] += 1
        a["komen"] += m["komen"] or 0
        a["like"] += m["like"] or 0
        if m["views"] is not None:
            a["views"] += m["views"]
            a["has_views"] = True
        if m["share"] is not None:
            a["share"] += m["share"]
            a["has_share"] = True
        if m["repost"] is not None:
            a["repost"] += m["repost"]
            a["has_repost"] = True
    out = []
    for a in agg.values():
        a["interaksi"] = (a["views"] if a["has_views"] else 0) + a["komen"] \
            + (a["share"] if a["has_share"] else 0) + a["like"] \
            + (a["repost"] if a["has_repost"] else 0)
        if not a["has_views"]:
            a["views"] = None
        if not a["has_share"]:
            a["share"] = None
        if not a["has_repost"]:
            a["repost"] = None
        out.append(a)
    return out


def account_posts(account_id, sejak=None, sampai=None):
    args = [account_id]
    filt = ""
    if sejak and sampai:
        filt = "AND substr(p.posted_at,1,10) BETWEEN ? AND ?"
        args += [sejak, sampai]
    rows = q(f"""SELECT p.* FROM posts p WHERE p.account_id=? {filt}
                 ORDER BY p.posted_at DESC""", args)
    metrik = latest_metrics_map([r["id"] for r in rows])
    for r in rows:
        r["metrics"] = metrik.get(r["id"])
    return rows
