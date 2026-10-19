#!/usr/bin/env python3
"""PantauAkun — web app pemantauan performa multi-akun (TikTok/IG/Threads/FB).

Jalankan:  python3 app.py [--port 8765]
Buka:      http://localhost:8765

Nol dependensi di luar stdlib (+ openpyxl untuk export Excel).
Database: data/pantauakun.db (SQLite, dibuat otomatis).
"""
import datetime
import json
import mimetypes
import os
import queue
import re
import sqlite3
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import db
import scrape
import exporter
import session
import textsafe
import sheetio

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
import wibtime as wib

# Semua tanggal di app ini memakai WIB (UTC+7). Lihat wibtime.py.
WIB = wib.WIB

jobs = {}
jobs_lock = threading.Lock()
job_seq = [0]


def today_wib():
    return wib.today_wib()


def default_week():
    """Pekan berjalan Senin-Minggu (WIB)."""
    t = today_wib()
    mon = t - datetime.timedelta(days=t.weekday())
    return mon.isoformat(), (mon + datetime.timedelta(days=6)).isoformat()


JOB_LIMIT = 20          # job lama dibuang dari RAM agar tidak menumpuk


def new_job(kind, total):
    with jobs_lock:
        job_seq[0] += 1
        jid = job_seq[0]
        jobs[jid] = {"id": jid, "kind": kind, "status": "running",
                     "total": total, "done": 0, "ok": 0, "fail": 0,
                     "errors": [], "started": time.time(), "result": None}
        _prune_jobs_locked()
    return jid


def _prune_jobs_locked():
    """Buang job lama dari RAM (selalu jalankan sambil jobs_lock dipegang)."""
    if len(jobs) <= JOB_LIMIT:
        return
    urut = sorted(jobs.values(), key=lambda j: j.get("started", 0))
    for j in urut[:len(jobs) - JOB_LIMIT]:
        if j.get("status") == "running":      # jangan buang job aktif
            continue
        jobs.pop(j["id"], None)


def job_update(jid, **kw):
    with jobs_lock:
        jobs[jid].update(kw)
        _prune_jobs_locked()


# ---------- checkpoint job: agar 668 link tidak hilang saat restart ----------

def save_job_checkpoint(jid):
    """Tulis status job ke disk. Dipanggil tiap 10 item selesai.

    Untuk 668 link satu job berjalan ~20-30 menit; tanpa checkpoint,
    restart server = semua progress hilang.
    """
    with jobs_lock:
        job = jobs.get(jid)
        if not job:
            return
        snap = {
            "id": job["id"], "kind": job["kind"], "total": job["total"],
            "done": job["done"], "ok": job["ok"], "fail": job["fail"],
            "started": job["started"],
            "pending": [it["url"] for it in job.get("items", [])
                        if it.get("status") in ("pending", "running")],
        }
    try:
        os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
        # SATU FILE PER JOB. Versi lama memakai job_checkpoint.json tunggal,
        # jadi dua job yang jalan bersamaan saling menimpa progres -> salah
        # satu job kehilangan checkpoint-nya.
        p = os.path.join(ROOT, "data", f"job_checkpoint_{jid}.json")
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snap, f)
        os.replace(tmp, p)          # atomic: tidak ada file setengah jadi
    except Exception:  # noqa: BLE001 - checkpoint tidak boleh menggagalkan job
        pass


def load_job_checkpoint():
    """Checkpoint job yang paling baru (kalau ada) untuk info UI.

    Sekarang satu file per job (job_checkpoint_<id>.json); file lama
    job_checkpoint.json masih dibaca supaya progress sebelumnya tidak hilang.
    """
    import glob
    d = os.path.join(ROOT, "data")
    pola = os.path.join(d, "job_checkpoint_*.json")
    calon = sorted(glob.glob(pola), key=os.path.getmtime, reverse=True)
    calon.append(os.path.join(d, "job_checkpoint.json"))   # format lama
    for p in calon:
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001 - lewati file rusak
            continue
    return None


# ---------------- background: tarik Threads massal ----------------

def listing_bulk_job(jid, platform, per_account=10):
    """Tarik massal TikTok/Instagram: listing per akun (butuh sesi login),
    lalu scrape tiap video/postingan. Cocok otomatis ke akunnya."""
    delay = float(db.get_setting("scrape_delay", "2") or 2)
    cookies = session.get_stored(platform)
    accounts = db.list_accounts(platform)
    job_update(jid, total=len(accounts))
    if not cookies:
        job_update(jid, status="done",
                   result={"ok": 0, "fail": len(accounts),
                           "error": "belum ada sesi login — isi cookie di Pengaturan"})
        with jobs_lock:
            jobs[jid]["errors"].append("belum ada sesi login untuk " + platform)
        return
    fetch_fn = scrape.fetch_instagram_account  # hanya IG yg didukung saat ini
    ok = fail = saved = 0
    for acc in accounts:
        try:
            items = fetch_fn(acc["username"], cookies, limit=per_account)
            for it in items:
                try:
                    polite_wait(platform)
                    d = scrape.scrape_with_retry(it["url"], cookies=None)
                    pid = db.add_post(acc["id"], platform, d["url"],
                                      d["post_key"], d["author"] or acc["username"],
                                      d["posted_at"], d["caption"])
                    db.add_metrics(pid, d["views"], d["komen"], d["share"],
                                   d["like"], d["repost"])
                    saved += 1
                except Exception as e:
                    with jobs_lock:
                        jobs[jid]["errors"].append(
                            f"@{acc['username']}: {str(e)[:80]}")
            ok += 1
        except Exception as e:
            fail += 1
            with jobs_lock:
                jobs[jid]["errors"].append(f"@{acc['username']}: {str(e)[:100]}")
        with jobs_lock:
            jobs[jid]["done"] += 1
            jobs[jid]["ok"] = ok
            jobs[jid]["fail"] = fail
        time.sleep(delay)
    job_update(jid, status="done",
               result={"ok": ok, "fail": fail, "saved": saved,
                       "per_account": per_account})


def threads_bulk_job(jid, sejak, sampai):
    delay = float(db.get_setting("scrape_delay", "2") or 2)
    accounts = db.list_accounts("threads")
    job_update(jid, total=len(accounts))
    ok = fail = 0
    for acc in accounts:
        try:
            posts = scrape.fetch_threads_account(acc["username"], sejak, sampai)
            for p in posts:
                pid = db.add_post(acc["id"], "threads", p["url"],
                                  p["post_key"], p["author"],
                                  p["posted_at"], p["caption"])
                db.add_metrics(pid, p["views"], p["komen"], p["share"],
                               p["like"], p["repost"])
            ok += 1
        except Exception as e:
            fail += 1
            with jobs_lock:
                jobs[jid]["errors"].append(f"@{acc['username']}: {str(e)[:100]}")
        with jobs_lock:
            jobs[jid]["done"] += 1
            jobs[jid]["ok"] = ok
            jobs[jid]["fail"] = fail
        time.sleep(delay)
    job_update(jid, status="done",
               result={"ok": ok, "fail": fail, "sejak": sejak, "sampai": sampai})


# ---------------- background: cek follow (relasi vs akun admin) ----------------
# Instagram TIDAK mengekspos relasi follow secara publik (riset 2026-10-19):
# tidak ada jalur tanpa login. Fitur ini karena itu WAJIB cookie sesi, dan
# hanya bisa menjawab relasi RELATIF terhadap akun PEMILIK SESI (akun admin) —
# bukan "akun A follow akun B" untuk dua akun sembarang.

FOLLOW_PLATFORMS = ("instagram",)      # platform yang mendukung cek follow


def follow_check_job(jid, platform="instagram"):
    """Cek follow tiap akun di daftar terhadap akun admin (sesi login)."""
    delay = float(db.get_setting("scrape_delay", "2") or 2)
    cookies = session.get_stored(platform)
    accounts = db.list_accounts(platform)
    job_update(jid, total=len(accounts), platform=platform)

    if not cookies:
        with jobs_lock:
            jobs[jid]["errors"].append(
                f"belum ada sesi login {platform} — fitur cek follow wajib "
                f"cookie. Isi di Pengaturan → Sesi login.")
        job_update(jid, status="done",
                   result={"ok": 0, "fail": len(accounts),
                           "error": f"belum ada sesi login {platform}"})
        return

    # Label akun admin (opsional — kalau gagal, cek follow tetap jalan).
    admin = scrape.fetch_instagram_self(cookies)
    if admin:
        db.set_setting("follow_admin_" + platform, admin.get("username") or "")
        job_update(jid, admin=admin)

    ok = fail = 0
    streak = 0

    def simpan(acc_id, tid, fs, prof, err):
        """Simpan hasil satu akun — TIDAK BOLEH mematikan job.

        Akun bisa terhapus dari UI saat job masih berjalan; saat itu baris
        follow_status melanggar FOREIGN KEY. Dulu itu melempar dari dalam
        blok `except`, sehingga thread job mati diam-diam dan job tidak
        pernah selesai (ditemukan lewat tes 2026-10-19).
        """
        try:
            db.save_follow_status(
                acc_id, platform, tid,
                (fs or {}).get("following"), (fs or {}).get("followed_by"),
                (fs or {}).get("outgoing_request"),
                (fs or {}).get("incoming_request"),
                (fs or {}).get("is_private"), err,
                follower_count=(prof or {}).get("follower_count"),
                following_count=(prof or {}).get("following_count"))
        except sqlite3.IntegrityError:
            pass          # akun sudah dihapus -> tidak ada yang perlu disimpan
        except Exception as e:  # noqa: BLE001
            with jobs_lock:
                jobs[jid]["errors"].append(
                    f"gagal menyimpan hasil @{acc_id}: {str(e)[:80]}")

    for acc in accounts:
        berhenti = False
        try:
            polite_wait(platform)
            prof = scrape.fetch_instagram_profile(acc["username"], cookies)
            tid = prof.get("id")
            if not tid:
                raise scrape.ScrapeFailed("id profil tidak ditemukan",
                                          retryable=False)
            polite_wait(platform)
            fs = scrape.fetch_instagram_friendship(tid, cookies)
            simpan(acc["id"], tid, fs, prof, None)
            ok += 1
            streak = 0
        except Exception as e:  # noqa: BLE001 - status dicatat per akun
            fail += 1
            msg = str(e)[:200]
            simpan(acc["id"], None, None, None, msg)
            with jobs_lock:
                jobs[jid]["errors"].append(f"@{acc['username']}: {msg[:90]}")
            if _looks_like_auth_problem(msg):
                streak += 1
                if streak >= 3:
                    with jobs_lock:
                        jobs[jid]["errors"].append(
                            f"[{platform}] Sesi login bermasalah — sisa akun "
                            f"dilewati. Isi ulang cookie di Pengaturan lalu "
                            f"jalankan cek follow lagi.")
                        jobs[jid]["auth_stopped"] = platform
                    berhenti = True
            else:
                streak = 0
        # Penghitung diperbarui SEBELUM break supaya progress di UI tidak
        # tertinggal (dulu akun terakhir yang memicu stop tidak terhitung).
        with jobs_lock:
            jobs[jid]["done"] += 1
            jobs[jid]["ok"] = ok
            jobs[jid]["fail"] = fail
        if berhenti:
            break
        time.sleep(delay)

    job_update(jid, status="done",
               result={"ok": ok, "fail": fail, "platform": platform,
                       "admin": admin})


# ---------------- background: scrape banyak link ----------------
# Model: background job + 3 worker + jeda sopan per platform (min 2 dtk)
# + retry otomatis (maks 3x, backoff eksponensial + jitter) hanya untuk
# kegagalan transien (timeout/429/5xx). Kegagalan permanen (Facebook,
# URL tak dikenal) langsung final tanpa retry.

import concurrent.futures

_plats_guard = threading.Lock()
_plats_locks = {}
_plats_last = {}


def polite_wait(platform, min_interval=2.0):
    """Jamin jeda minimum antar request ke platform yang sama.

    CATATAN ARSITEKTUR: fungsi ini MENGGUNAKAN worker selama tidurnya.
    Kalau pool kecil, link Threads bisa membuat semua worker menganggur
    sementara link IG/FB mengantre (terukur: 10,6s vs 7,7s ideal).
    Karena itu link_scrape_job memakai SATU LANE PER PLATFORM — link
    platform berbeda tidak pernah saling memblokir.
    """
    with _plats_guard:
        lock = _plats_locks.setdefault(platform or "unknown",
                                       threading.Lock())
    with lock:
        wait = min_interval - (time.monotonic() - _plats_last.get(platform, 0))
        if wait > 0:
            time.sleep(wait)
        _plats_last[platform] = time.monotonic()


# Worker paralel per lane, DIUKUR per platform (2026-10-11, link nyata):
#   threads   24 link: 1 worker 156,7s (9,2 link/mnt) -> 3 worker 65,4s
#                     (22,0 link/mnt), sukses 24/24 di keduanya.
#   instagram 12 link: 1 worker 27,1 link/mnt -> 3 worker 30,4 link/mnt, 100%.
#   tiktok    12 link: 1 worker 50% sukses -> 3 worker HANYA 25% sukses,
#                     throughput nyaris sama (3,5 vs 3,9 link/mnt). TikTok
#                     memunculkan captcha SlardarWAF saat beban naik, jadi
#                     HARUS tetap 1 worker.
#   facebook  diuji 2 link: aman, tapi FB besar & berat -> 2 konservatif.
LANE_WORKERS_DEFAULT = {
    "threads": "3",
    "instagram": "3",
    "facebook": "2",
    "tiktok": "1",          # WAF: jangan paralelkan
}


def app_lane_platforms():
    """Platform yang tampil di pengaturan kecepatan (TikTok dikunci 1)."""
    return [p for p in LANE_WORKERS_DEFAULT if p != "tiktok"]


def lane_workers(platform):
    """Berapa worker paralel untuk satu lane platform.

    AMAN untuk threads/instagram/facebook karena polite_wait() tetap berlaku:
    ia mengunci per platform dan mencatat waktu saat request MULAI, jadi
    request baru selalu START >= 2 detik dari request sebelumnya - sama
    persis seperti mode 1 worker. Yang berubah hanya jumlah request yang
    "mengambang" bersamaan, BUKAN frekuensi request per detik.

    TIDAK aman untuk TikTok: diukur, 3 worker menurunkan sukses 50% -> 25%
    karena WAF. Jadi platform itu dikunci di 1 worker dan tidak bisa dinaikkan.
    """
    plat = platform or ""
    raw = (db.get_setting("lane_workers_" + plat)
           or LANE_WORKERS_DEFAULT.get(plat, "2"))
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = int(LANE_WORKERS_DEFAULT.get(plat, "2"))
    if plat == "tiktok":
        n = 1
    return max(1, min(n, 4))


def _run_lane_list(lst, fn):
    """Jalankan fn(u) untuk tiap u dengan jeda sopan per platform."""
    for u in lst:
        polite_wait(scrape.detect_platform(u))
        fn(u)


# Deteksi "sesi login mati" di tengah batch.
# Tanpa ini: cookie Facebook/Threads/Instagram kedaluwarsa -> SEMUA link
# platform itu gagal satu per satu, dan user baru sadar setelah puluhan
# menit. Dengan ini, 3 kegagalan beruntun dengan pesan yang sama langsung
# menghentikan lane platform itu dan memberi tahu alasannya.
_AUTH_HINTS = ("sesi facebook tidak valid", "cookie kedaluwarsa",
               "butuh sesi login", "sesi login", "halaman login")
_AUTH_STREAK = {}


def _looks_like_auth_problem(msg):
    m = (msg or "").lower()
    return any(h in m for h in _AUTH_HINTS)


def _scrape_lane(platform, job_items, job, sessions, jid):
    """Kerjakan antrean link untuk SATU platform dengan N worker paralel.

    Versi lama memproses SATU per satu. Untuk 1000 link itu berarti
    1000 x (2 detik jeda + 3-5 detik scrape) = ~100 menit, karena jeda
    tidak pernah tumpang tindih dengan waktu jaringan.

    Dengan N worker, jeda 2 detik tumpang tindih dengan scrape yang sedang
    berjalan -> request tetap mulai tiap 2 detik, tapi beberapa berlaku
    bersamaan. Throughput naik ~N x tanpa menambah beban per detik.
    """
    antrean = queue.Queue()
    for it in job_items:
        antrean.put(it)
    n = min(lane_workers(platform), len(job_items)) or 1
    stop = threading.Event()      # di-set kalau sesi platform ini mati

    def tandai_sesi_mati():
        """3 kegagalan auth beruntun -> sisa link platform ini ditandai jelas."""
        with jobs_lock:
            job.setdefault("errors", []).append(
                f"[{platform}] Sesi login {platform} bermasalah — "
                f"link {platform} yang tersisa dilewati. "
                f"Isi ulang cookie di Pengaturan lalu ulangi yang gagal.")
            job["auth_stopped"] = platform
        stop.set()

    def worker():
        while not stop.is_set():
            try:
                it = antrean.get_nowait()
            except queue.Empty:
                return
            try:
                _scrape_one(job, it, sessions, jid)
                if it.get("status") == "ok":
                    _AUTH_STREAK[platform] = 0
                elif _looks_like_auth_problem(it.get("error")):
                    _AUTH_STREAK[platform] = _AUTH_STREAK.get(platform, 0) + 1
                    if _AUTH_STREAK[platform] >= 3:
                        tandai_sesi_mati()
                        return
            finally:
                antrean.task_done()

    if n == 1:
        worker()
    else:
        ths = [threading.Thread(target=worker, daemon=True) for _ in range(n)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
    # Sisa antrean yang tidak sempat dikerjakan -> tandai, jangan hilang diam-diam
    if stop.is_set():
        while True:
            try:
                sisa = antrean.get_nowait()
            except queue.Empty:
                break
            sisa["status"] = "failed"
            sisa["error"] = (f"Dilewati: sesi login {platform} bermasalah. "
                             f"Isi ulang cookie di Pengaturan.")
            sisa["retryable"] = True
            with jobs_lock:
                job["done"] += 1
                job["fail"] += 1
            antrean.task_done()


# ---------------- audit hasil scrape ----------------
# Tujuannya: pengguna bisa TAHU mana tanggal yang bisa dipercaya sebelum
# dipakai laporan, tanpa harus tahu detail teknis tiap platform.

def audit_item(d, sekarang=None):
    """Periksa satu hasil scrape -> dict {level, flags, catatan}.

    level:
      "ok"    — tanggal ada dan bertingkat 'exact'
      "wajar" — tanggal ada tapi hanya tingkat HARI (Instagram)
      "periksa" — ada yang janggal: tanggal masa depan, tidak ada tanggal,
                 atau tanggal sangat jauh sebelum sekarang
    """
    # posted_at disimpan sebagai string TANPA timezone;bandingkan dalam
    # bentuk yang sama (naive) supaya tidak salah pada perbandingan waktu.
    if sekarang is None:
        sekarang = datetime.datetime.now(wib.WIB).replace(tzinfo=None)
    now = sekarang
    flags = []
    pa = (d.get("posted_at") or "").strip()
    pres = d.get("date_precision") or "none"
    if not pa:
        flags.append("tanggal kosong")
        return {"level": "periksa", "flags": ["tanggal kosong"],
                "catatan": "Platform tidak memberi tanggal."}
    try:
        dt = datetime.datetime.strptime(pa[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            dt = datetime.datetime.strptime(pa[:10], "%Y-%m-%d")
        except ValueError:
            return {"level": "periksa", "flags": ["format tanggal rusak"],
                    "catatan": f"Tanggal tidak bisa dibaca: {pa!r}"}
    if dt > now + datetime.timedelta(days=1):
        flags.append("tanggal masa depan")
    if (now - dt).days > 365 * 5:
        flags.append("tanggal sangat lama")
    if flags:
        return {"level": "periksa", "flags": flags,
                "catatan": "Periksa tanggal posting ini sebelum dipakai."}
    if pres == "day":
        return {"level": "wajar", "flags": ["tanggal tingkat hari"],
                "catatan": ("Instagram hanya memberi tanggal tanpa jam; "
                            "jam 00:00 adalah placeholder.")}
    if pres == "none":
        return {"level": "periksa", "flags": ["tidak ada penanda tanggal"],
                "catatan": "Sumber tanggal tidak diketahui."}
    return {"level": "ok", "flags": [], "catatan": ""}


def audit_job(items):
    """Ringkasan audit untuk seluruh item sebuah job."""
    hasil = []
    n = {"ok": 0, "wajar": 0, "periksa": 0}
    kunci = {}
    for it in items:
        if it.get("status") != "ok" or not it.get("data"):
            continue
        a = audit_item(it["data"])
        it["audit"] = a
        n[a["level"]] = n.get(a["level"], 0) + 1
        # duplikat dalam batch yang sama (post_key sama)
        pk = (it["data"].get("platform"), (it["data"].get("post_key") or "").strip())
        if pk[1]:
            kunci.setdefault(pk, []).append(it)
        hasil.append(it)
    duplikat = 0
    for pk, lst in kunci.items():
        if len(lst) > 1:
            for it in lst[1:]:
                it.setdefault("audit", {"level": "periksa", "flags": [],
                                        "catatan": ""})
                it["audit"]["flags"].append("duplikat dalam batch")
                it["audit"]["level"] = "periksa"
                it["audit"]["catatan"] = "Link posting ini muncul lebih dari sekali."
                duplikat += 1
                n["periksa"] += 1
                n[a["level"]] -= 1 if a["level"] != "periksa" else 0
    return {"jumlah": len(hasil), **n, "duplikat": duplikat}


def new_link_job(urls):
    """Buat job scrape massal. URL didedupe (urutan dipertahankan)."""
    seen, uniq = set(), []
    for u in urls:
        u = (u or "").strip()
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)
    jid = new_job("link_scrape", len(uniq))
    with jobs_lock:
        jobs[jid]["items"] = [
            {"url": u, "platform": scrape.detect_platform(u),
             "status": "pending", "attempts": 0, "error": None,
             "retryable": False, "data": None, "matched_account": None,
             "account_id": None, "already_saved": False}
            for u in uniq]
    t = threading.Thread(target=link_scrape_job, args=(jid,), daemon=True)
    t.start()
    return jid


def _scrape_one(job, it, sessions, jid=None):
    if it["status"] != "pending":
        return
    it["status"] = "running"
    try:
        polite_wait(it["platform"])
        d = scrape.scrape_with_retry(it["url"], cookies=sessions.get(it["platform"]))
        it["attempts"] = d.pop("_attempts", 1)
        acc = db.find_account(d["platform"], d["author"])
        it["data"] = {k: d.get(k) for k in (
            "platform", "url", "post_key", "author", "posted_at", "caption",
            "views", "komen", "share", "like", "repost",
            "date_precision")}
        if not acc:
            # Facebook kadang tidak mengirim NAMA pengirim; id profilnya
            # masih ada, dan link_profile akun memuat id itu -> tetap bisa
            # dipasangkan (terukur 12 Okt: /share/v/ tanpa nama, tapi
            # actor_id-nya cocok dengan akun Steva Afifah).
            acc = db.find_account_by_profile_id(d["platform"], d.get("actor_id"))
        it["matched_account"] = (
            {"id": acc["id"], "kode": acc["kode"],
             "username": acc["username"]} if acc else None)
        it["account_id"] = acc["id"] if acc else None
        it["status"] = "ok"
        with jobs_lock:
            job["ok"] += 1
    except Exception as e:  # noqa: BLE001 - status dicatat ke job
        it["attempts"] = getattr(e, "attempts", it["attempts"] or 1)
        it["status"] = "failed"
        it["error"] = str(e)[:200]
        it["retryable"] = bool(getattr(e, "retryable", False))
        with jobs_lock:
            job["fail"] += 1
            job["errors"].append(f"{it['url'][:60]}: {it['error'][:80]}")
    finally:
        with jobs_lock:
            job["done"] += 1
            n = job["done"]
        if n % 10 == 0 and jid is not None:   # checkpoint tiap 10 item
            save_job_checkpoint(jid)


def link_scrape_job(jid):
    with jobs_lock:
        job = jobs.get(jid)
    if not job:
        return
    items = job["items"]
    # sesi login dimuat sekali per job (hemat query), dipakai per platform
    sessions = {p: session.get_stored(p) for p in session.PLATFORMS}

    # SATU LANE PER PLATFORM. Alasan: polite_wait() memakai worker selama
    # tidurnya. Dengan pool bersama, 3 link Threads bisa membuat semua
    # worker menganggur ~2 detik dan link IG/FB ikut tertahan (terukur
    # 10,6s vs 7,7s ideal pada campuran 6/2/2). Lane memisahkan antrean
    # sehingga tiap platform punya ritmenya sendiri tanpa saling tunggu.
    lanes = {}
    for it in items:
        lanes.setdefault(it.get("platform") or "unknown", []).append(it)
    if len(lanes) > 1:
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=len(lanes)) as ex:
            futs = [ex.submit(_scrape_lane, plat, its, job, sessions, jid)
                    for plat, its in lanes.items()]
            for f in futs:
                f.exception()      # error sudah dicatat per item
    else:
        for plat, its in lanes.items():
            _scrape_lane(plat, its, job, sessions, jid)
    save_job_checkpoint(jid)
    # tandai duplikat (URL kanonis + identitas postingan)
    canon = [(it["data"]["url"], it["data"]["platform"],
              it["data"].get("post_key", ""))
             for it in items if it["status"] == "ok" and it["data"]]
    known_urls = db.urls_exist([u for u, _, _ in canon])
    # post_key KOSONG jangan pernah dipakai untuk deteksi duplikat: dua
    # posting berbeda yang sama-sama gagal dapat id akan cocok pada
    # ("facebook", "") dan yang kedua ditandai sudah tersimpan padahal belum
    # (bug laten; 0 baris terdampak di DB s.d. 2026-10-11). post_key kosong
    # hanya identity fallback, bukan bukti.
    known_keys = db.keys_exist([(p, k) for _, p, k in canon if k])
    for it in items:
        if it["status"] == "ok" and it["data"]:
            d = it["data"]
            key = str(d.get("post_key") or "").strip()   # defensif: bisa int
            it["already_saved"] = (
                d["url"] in known_urls
                or (bool(key) and (d["platform"], key) in known_keys))
    audit_job(items)
    job_update(jid, status="done",
               result={"ok": job["ok"], "fail": job["fail"]})


def retry_link_job(jid):
    """Kembalikan item gagal-transien ke pending, jalankan ulang worker."""
    with jobs_lock:
        job = jobs.get(jid)
        if not job or job["kind"] != "link_scrape":
            return 0
        n = 0
        for it in job["items"]:
            if it["status"] == "failed" and it["retryable"]:
                it["status"] = "pending"
                it["error"] = None
                n += 1
        if n:
            job["done"] -= n
            job["fail"] -= n
            job["status"] = "running"
    if n:
        t = threading.Thread(target=link_scrape_job, args=(jid,), daemon=True)
        t.start()
    return n


# ---------------- HTTP handler ----------------

class Handler(BaseHTTPRequestHandler):
    server_version = "PantauAkun/1.0"
    # Batas link untuk /api/links/process. Di atas ini harus pakai
    # /api/links/scrape-job (progress + checkpoint + worker paralel).
    LINKS_PROC_MAX = 50

    def log_message(self, *a):
        pass

    # ----- helpers -----
    def send_json(self, obj, status=200):
        # Pengaman lapis kedua: karakter yang tidak bisa jadi UTF-8 (mis.
        # surrogate liar dari caption ber-emoji) TIDAK BOLEH menggagalkan
        # seluruh respons dengan HTTP 500. Tanpa ini satu caption rusak
        # membuat UI tidak menampilkan apa pun (terverifikasi 2026-10-11).
        obj = textsafe.json_safe(obj)
        try:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        except UnicodeEncodeError:
            body = json.dumps(obj, ensure_ascii=True).encode(
                "utf-8", "replace")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

    def read_multipart(self):
        """Parser multipart/form-data: {nama: (filename, bytes)}.

        Binary-safe: hanya CRLF penutup yang dibuang (tidak melukai isi file).
        """
        ctype = self.headers.get("Content-Type", "")
        m = re.search(r'boundary="?([^";]+)"?', ctype)
        if not m:
            raise ValueError("Permintaan harus multipart/form-data.")
        boundary = b"--" + m.group(1).strip().encode()
        n = int(self.headers.get("Content-Length") or 0)
        if n > sheetio.MAX_BYTES * 2:
            raise ValueError("Ukuran upload terlalu besar.")
        body = self.rfile.read(n) if n else b""
        out = {}
        for part in body.split(boundary):
            if part.startswith(b"--"):          # penutup multipart
                continue
            part = part.lstrip(b"\r\n")           # CRLF tepat setelah boundary
            head, sep, data = part.partition(b"\r\n\r\n")
            if not sep:
                continue
            if data.endswith(b"\r\n"):           # CRLF sebelum boundary berikutnya
                data = data[:-2]
            nm = re.search(br'name="([^"]+)"', head)
            fn = re.search(br'filename="([^"]*)"', head)
            if nm:
                out[nm.group(1).decode()] = (
                    fn.group(1).decode() if fn else None, data)
        return out

    def serve_static(self, path):
        if path == "/":
            path = "/index.html"
        fpath = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not fpath.startswith(WEB) or not os.path.isfile(fpath):
            self.send_json({"error": "not found"}, 404)
            return
        ctype = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
        with open(fpath, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8"
                         if ctype.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ----- routing -----
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        p, qs = url.path, urllib.parse.parse_qs(url.query)
        try:
            if p.startswith("/api/"):
                self.api_get(p, qs)
            elif p == "/api/export":
                self.api_get(p, qs)
            else:
                self.serve_static(p)
        except Exception as e:
            traceback.print_exc()
            self.send_json({"error": str(e)[:300]}, 500)

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        p = url.path
        try:
            if p == "/api/accounts":
                b = self.read_json()
                if not b.get("username") or not b.get("platform"):
                    return self.send_json({"error": "username & platform wajib"}, 400)
                aid = db.add_account(b.get("kode", ""), b["platform"],
                                     b["username"], b.get("link_profile", ""))
                self.send_json({"ok": True, "id": aid})
            elif p == "/api/accounts/seed":
                n = seed_accounts()
                self.send_json({"ok": True, "imported": n,
                                "counts": db.count_accounts()})
            elif p == "/api/accounts/import-excel":
                parts = self.read_multipart()
                if "file" not in parts:
                    return self.send_json({"error": "file tidak diterima"}, 400)
                fname, data = parts["file"]
                res = import_excel_accounts(data, fname or "")
                self.send_json({"ok": True, **res,
                                "counts": db.count_accounts()})
            elif p == "/api/links/import-excel":
                parts = self.read_multipart()
                if "file" not in parts:
                    return self.send_json({"error": "file tidak diterima"}, 400)
                fname, data = parts["file"]
                self.send_json({"ok": True,
                                **extract_links_from_excel(data, fname or "")})
            elif p == "/api/links/process":
                self.links_process()
            elif p == "/api/links/scrape-job":
                b = self.read_json()
                urls = [u for u in b.get("urls", []) if (u or "").strip()]
                if not urls:
                    return self.send_json({"error": "tidak ada link"}, 400)
                jid = new_link_job(urls)
                with jobs_lock:
                    total = jobs[jid]["total"]
                self.send_json({"ok": True, "job_id": jid, "total": total,
                                "dimasukkan": len(urls)})
            elif p == "/api/links/save":
                self.links_save()
            elif p == "/api/threads/fetch":
                b = self.read_json()
                sejak = b.get("sejak") or default_week()[0]
                sampai = b.get("sampai") or default_week()[1]
                jid = new_job("threads_bulk", 0)
                t = threading.Thread(target=threads_bulk_job,
                                     args=(jid, sejak, sampai), daemon=True)
                t.start()
                self.send_json({"ok": True, "job_id": jid})
            elif p == "/api/instagram/fetch":
                b = self.read_json()
                limit = int(b.get("limit") or 10)
                jid = new_job("instagram_bulk", 0)
                t = threading.Thread(target=listing_bulk_job,
                                     args=(jid, "instagram", limit), daemon=True)
                t.start()
                self.send_json({"ok": True, "job_id": jid})
            elif p == "/api/follow/check":
                b = self.read_json()
                plat = (b.get("platform") or "instagram").strip().lower()
                if plat not in FOLLOW_PLATFORMS:
                    return self.send_json(
                        {"error": "cek follow saat ini hanya untuk Instagram "
                                  "(butuh sesi login)"}, 400)
                if not session.get_stored(plat):
                    return self.send_json(
                        {"error": f"belum ada sesi login {plat}. Cek follow "
                                  f"wajib cookie — isi di Pengaturan → "
                                  f"Sesi login."}, 400)
                jid = new_job("follow_check", 0)
                t = threading.Thread(target=follow_check_job,
                                     args=(jid, plat), daemon=True)
                t.start()
                self.send_json({"ok": True, "job_id": jid, "platform": plat})
            elif p == "/api/sessions":
                b = self.read_json()
                plat = (b.get("platform") or "").strip().lower()
                if plat not in session.PLATFORMS:
                    return self.send_json({"error": "platform salah"}, 400)
                try:
                    cookies = session.parse_any(b.get("cookie") or "")
                except ValueError as e:
                    return self.send_json({"error": str(e)}, 400)
                session.save_stored(plat, cookies)
                self.send_json({"ok": True, "platform": plat,
                                "n_cookies": len(cookies)})
            elif p == "/api/sessions/upload":
                parts = self.read_multipart()
                if "file" not in parts:
                    return self.send_json({"error": "file tidak diterima"}, 400)
                fname, data = parts["file"]
                plat = ""
                for key in ("platform",):
                    if key in parts:
                        plat = parts[key][1].decode().strip().lower()
                if plat not in session.PLATFORMS:
                    return self.send_json(
                        {"error": "platform salah / tidak dikirim. "
                                  "Kirim field 'platform' dengan nilai: "
                                  + ", ".join(session.PLATFORMS)}, 400)
                try:
                    cookies = session.parse_any(data.decode("utf-8", "replace"))
                except ValueError as e:
                    return self.send_json({"error": str(e)}, 400)
                session.save_stored(plat, cookies)
                self.send_json({"ok": True, "platform": plat,
                                "n_cookies": len(cookies)})
            elif p.startswith("/api/sessions/") and p.endswith("/test"):
                plat = p.split("/")[3]
                if plat not in session.PLATFORMS:
                    return self.send_json({"error": "platform salah"}, 400)
                self.send_json(session.test_session(plat, session.get_stored(plat)))
            elif p == "/api/settings":
                b = self.read_json()
                for k, v in b.items():
                    db.set_setting(k, str(v))
                self.send_json({"ok": True})
            elif p.startswith("/api/links/job/") and p.endswith("/retry"):
                try:
                    jid = int(p.split("/")[4])
                except (IndexError, ValueError):
                    return self.send_json({"error": "job id salah"}, 400)
                n = retry_link_job(jid)
                self.send_json({"ok": True, "retried": n})
            elif p == "/api/posts/delete":
                self.posts_delete()
            elif p == "/api/posts/count":
                b = self.read_json()
                self.send_json(db.count_posts(
                    b.get("scope") or "all", b.get("platform"),
                    b.get("account_id"), b.get("sejak"), b.get("sampai")))
            elif p == "/api/backup":
                path = db.backup_db()
                if not path:
                    return self.send_json({"error": "database belum ada"}, 400)
                self.send_json({"ok": True, "path": path,
                                "nama": os.path.basename(path)})
            else:
                self.send_json({"error": "not found"}, 404)
        except ValueError as e:
            # kesalahan input (file rusak, format salah, JSON tidak valid)
            self.send_json({"error": str(e)[:300]}, 400)
        except Exception as e:
            traceback.print_exc()
            self.send_json({"error": str(e)[:300]}, 500)

    def do_DELETE(self):
        p = urllib.parse.urlparse(self.path).path
        m = re.match(r"^/api/sessions/(\w+)$", p)
        if m and m.group(1) in session.PLATFORMS:
            session.clear_stored(m.group(1))
            self.send_json({"ok": True})
            return
        m = re.match(r"^/api/posts/(\d+)$", p)
        if m:
            n = db.delete_posts("post", account_id=int(m.group(1)))
            self.send_json({"ok": True, **n})
            return
        m = re.match(r"^/api/accounts/(\d+)$", p)
        if m:
            db.delete_account(int(m.group(1)))
            self.send_json({"ok": True})
            return
        if p == "/api/accounts":
            self.accounts_delete()
            return
        self.send_json({"error": "not found"}, 404)

    # ----- API GET -----
    def api_get(self, p, qs):
        g = lambda k, d="": qs.get(k, [d])[0]
        if p == "/api/accounts":
            accs = db.list_accounts(g("platform") or None)
            # sertakan n_post supaya tabel Akun bisa menampilkan "berapa
            # posting yang akan ikut terhapus" sebelum user menekan hapus.
            npost = db.account_post_counts([a["id"] for a in accs] or None)
            for a in accs:
                a["n_post"] = npost.get(a["id"], 0)
            self.send_json(accs)
        elif p == "/api/dashboard":
            sejak = g("sejak") or default_week()[0]
            sampai = g("sampai") or default_week()[1]
            self.send_json({"sejak": sejak, "sampai": sampai,
                            "rows": db.dashboard(sejak, sampai,
                                                 g("platform") or None)})
        elif p == "/api/trend":
            sejak = g("sejak") or default_week()[0]
            sampai = g("sampai") or default_week()[1]
            self.send_json({"points": db.trend(
                sejak, sampai, g("platform") or None)})
        elif p == "/api/follow":
            plat = g("platform") or "instagram"
            self.send_json({
                "platform": plat,
                "admin": db.get_setting("follow_admin_" + plat, "") or "",
                "sesi_aktif": bool(session.get_stored(plat)),
                "ringkasan": db.follow_counts(plat),
                "rows": db.list_follow_status(plat)})
        elif p == "/api/counts":
            self.send_json(db.count_accounts())
        elif p == "/api/posts/count":
            g = lambda k: qs.get(k, [""])[0]
            self.send_json(db.count_posts(
                g("scope") or "all", g("platform") or None,
                int(g("account_id")) if g("account_id") else None,
                g("sejak") or None, g("sampai") or None))
        elif p == "/api/settings":
            self.send_json({
                "scrape_delay": db.get_setting("scrape_delay", "2"),
                "lane_workers": {pl: lane_workers(pl)
                                 for pl in app_lane_platforms()}})
        elif p == "/api/sessions":
            # status sesi per platform — nilai cookie TIDAK PERNAH dikembalikan
            out = {}
            for plat in session.PLATFORMS:
                c = session.get_stored(plat)
                out[plat] = {"active": bool(c), "n_cookies": len(c)}
            self.send_json(out)
        elif p == "/api/jobs":
            with jobs_lock:
                self.send_json(sorted(jobs.values(), key=lambda j: -j["id"])[:10])
        elif p.startswith("/api/jobs/"):
            jid = int(p.rsplit("/", 1)[1])
            with jobs_lock:
                j = jobs.get(jid)
            if not j:
                self.send_json({"error": "not found"}, 404)
                return
            # ?lite=1 -> hanya counter, TANPA seluruh daftar item.
            # Polling tiap 2 detik dengan 1000 link mengirim 623 KB tiap
            # kali (terukur) -> ~1,8 GB sia-sia selama 100 menit.
            # Poll berat cukup dilakukan sekali di awal & setelah selesai.
            if g("lite") in ("1", "true", "yes"):
                self.send_json({k: v for k, v in j.items()
                                if k not in ("items", "errors")})
                return
            self.send_json(j)
        elif re.match(r"^/api/post/\d+$", p):
            pid = int(p.rsplit("/", 1)[1])
            post = db.q("SELECT * FROM posts WHERE id=?", (pid,), one=True)
            if not post:
                self.send_json({"error": "postingan tidak ditemukan"}, 404)
                return
            self.send_json({"post": post, "history": db.post_history(pid)})
        elif re.match(r"^/api/account/\d+/posts$", p):
            aid = int(p.split("/")[3])
            self.send_json(db.account_posts(aid, g("sejak") or None,
                                            g("sampai") or None))
        elif p == "/api/export":
            sejak = g("sejak") or default_week()[0]
            sampai = g("sampai") or default_week()[1]
            plat = g("platform") or None
            fmt = (g("format") or "xlsx").lower()
            if fmt == "csv":
                data = exporter.to_csv_bytes(sejak, sampai, plat)
                ctype = "text/csv; charset=utf-8"
                fname = exporter.csv_filename(sejak, sampai)
            else:
                data = exporter.to_bytes(sejak, sampai, plat)
                ctype = ("application/vnd.openxmlformats-officedocument."
                         "spreadsheetml.sheet")
                fname = exporter.filename(sejak, sampai)
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Disposition",
                             f'attachment; filename="{fname}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_json({"error": "not found"}, 404)

    # ----- hapus data scrape (akun tetap) -----

    def accounts_delete(self):
        """Hapus akun massal: terpilih (ids), per platform, atau semua.

        Posting + metrik milik akun ikut terhapus (CASCADE, lihat db.py).
        Cakupan besar otomatis dibackup dulu supaya tidak menyesal.
        """
        b = self.read_json()
        ids = b.get("ids") or None
        platform = b.get("platform") or None
        semua = bool(b.get("all"))
        if not ids and not platform and not semua:
            return self.send_json(
                {"error": "kirim ids[], platform, atau all=true"}, 400)
        if platform and platform not in ("tiktok", "instagram", "threads",
                                         "facebook"):
            return self.send_json({"error": "platform tidak dikenal"}, 400)
        if ids:
            ids = [int(i) for i in ids if str(i).isdigit()]
            if not ids:
                return self.send_json({"error": "ids tidak valid"}, 400)
            # Jangan sampai user mengirim ribuan id sekaligus.
            ids = ids[:2000]
        if platform and semua:
            return self.send_json(
                {"error": "pilih salah satu: platform ATAU all"}, 400)
        n = db.count_accounts_deletable(ids, platform)
        if not n["accounts"]:
            return self.send_json({"ok": True, **n, "msg": "Tidak ada akun untuk dihapus."})
        # Cakupan besar -> backup dulu
        backup = None
        if (semua or platform or len(ids or []) > 5) and b.get("backup", True):
            backup = db.backup_db("-sebelum-hapus-akun")
        hasil = db.delete_accounts(ids, platform)
        self.send_json({"ok": True, "deleted": hasil, "backup": backup})

    def posts_delete(self):
        """Hapus posting + metrik sesuai cakupan.

        Cakupan: post | account | platform | periode | all.
        Untuk 'all'/'periode' yang berbahaya, backup database dibuat dulu.
        Akun TIDAK PERNAH ikut terhapus.
        """
        b = self.read_json()
        scope = b.get("scope") or "all"
        if scope not in ("post", "account", "platform", "periode", "all"):
            return self.send_json({"error": "scope tidak dikenal"}, 400)
        platform = b.get("platform") or None
        account_id = b.get("account_id")
        sejak, sampai = b.get("sejak"), b.get("sampai")
        if scope == "platform" and platform not in ("tiktok", "instagram",
                                                   "threads", "facebook"):
            return self.send_json({"error": "platform tidak dikenal"}, 400)
        if scope in ("post", "account") and not account_id:
            return self.send_json({"error": "account_id/post_id wajib diisi"}, 400)
        if scope == "periode" and not (sejak and sampai):
            return self.send_json({"error": "periode wajib diisi"}, 400)
        n = db.count_posts(scope, platform, account_id, sejak, sampai)
        if not n["posts"]:
            return self.send_json({"ok": True, **n, "msg": "Tidak ada data untuk dihapus."})
        # Cakupan besar -> backup dulu supaya tidak menyesal
        backup = None
        if scope in ("all", "periode") and b.get("backup", True):
            backup = db.backup_db("-sebelum-hapus")
        db.delete_posts(scope, platform, account_id, sejak, sampai)
        self.send_json({"ok": True, "deleted": n, "backup": backup})

    # ----- links: proses & simpan -----
    def links_process(self):
        """Scrape satu daftar link secara langsung (tanpa background job).

        Dibatasi 50 link DAN tetap diproses di worker thread supaya request
        tidak memblokir server.versi lama loops tanpa batas: 1000 link =
        ~100 menit dengan seluruh server terkunci (semua request lain, termasuk
        halaman dashboard, ikut tersendat karena ThreadingHTTPServer Beni
        satu thread ini).

        Untuk >50 link, UI otomatis memakai /api/links/scrape-job yang punya
        progress bar, checkpoint, retry, dan worker paralel per lane.
        """
        b = self.read_json()
        urls = []
        seen = set()
        for u in b.get("urls", []):
            u = (u or "").strip()
            if u and u not in seen:
                seen.add(u)
                urls.append(u)
        if not urls:
            return self.send_json({"items": [], "msg": "Tidak ada link."})
        potong = urls[:self.LINKS_PROC_MAX]
        sisa = urls[self.LINKS_PROC_MAX:]
        sessions = {p: session.get_stored(p) for p in session.PLATFORMS}
        out = []
        # satu lane per platform, sama seperti job besar, tapi in-process:
        # link platform berbeda tidak saling memblokir.
        lanes = {}
        for u in potong:
            lanes.setdefault(scrape.detect_platform(u) or "unknown", []).append(u)

        def proses(u):
            item = {"url": u, "platform": scrape.detect_platform(u)}
            try:
                d = scrape.scrape_with_retry(
                    u, cookies=sessions.get(item["platform"]))
                item.update({"ok": True, "author": d["author"],
                             "posted_at": d["posted_at"],
                             "caption": d["caption"][:120],
                             "views": d["views"], "komen": d["komen"],
                             "share": d["share"], "like": d["like"],
                             "repost": d["repost"], "_data": d})
                acc = db.find_account(d["platform"], d["author"])
                if not acc:
                    acc = db.find_account_by_profile_id(
                        d["platform"], d.get("actor_id"))
                item["matched_account"] = (
                    {"id": acc["id"], "kode": acc["kode"],
                     "username": acc["username"]} if acc else None)
            except Exception as e:
                item["ok"] = False
                item["error"] = str(e)[:200]
                item["retryable"] = bool(getattr(e, "retryable", False))
            with jobs_lock:
                out.append(item)

        for plat, lst in lanes.items():
            n = min(lane_workers(plat), len(lst))
            ths = [threading.Thread(target=_run_lane_list, args=(lst, proses),
                                    daemon=True) for _ in range(n)]
            for t in ths:
                t.start()
            for t in ths:
                t.join()
        urut = {u: i for i, u in enumerate(potong)}
        out.sort(key=lambda it: urut.get(it["url"], 0))
        # deteksi duplikat: URL kanonis hasil resolve + identitas (platform, post_key)
        # agar link pendek & link panjang dari postingan yg sama ketahuan
        canon = [(it["_data"]["url"], it["_data"]["platform"],
                  it["_data"].get("post_key", ""))
                 for it in out if it.get("ok") and it.get("_data")]
        known_urls = db.urls_exist([u for u, _, _ in canon])
        known_keys = db.keys_exist([(p, k) for _, p, k in canon])
        for it in out:
            if it.get("ok") and it.get("_data"):
                d = it["_data"]
                key = str(d.get("post_key") or "").strip()   # defensif: bisa int
                it["already_saved"] = (
                    d["url"] in known_urls
                    or (bool(key) and (d["platform"], key) in known_keys))
            else:
                it["already_saved"] = False
        pesan = ""
        if sisa:
            pesan = (f" {len(sisa)} link tidak diproses di sini "
                     f"(batas {self.LINKS_PROC_MAX}). "
                     f"Pakai job besar untuk memproses semuanya.")
        self.send_json({"items": out, "msg": pesan})

    def links_save(self):
        b = self.read_json()
        saved, updated, skipped = 0, 0, []
        for it in b.get("items", []):
            d = it.get("_data")
            aid = it.get("account_id")
            if not d or not aid:
                skipped.append(it.get("url"))
                continue
            pid, is_new = db.upsert_post(
                aid, d["platform"], d["url"], d["post_key"], d["author"],
                d["posted_at"], d["caption"])
            db.add_metrics(pid, d["views"], d["komen"], d["share"],
                           d["like"], d["repost"])
            if is_new:
                saved += 1
            else:
                updated += 1  # metrik di-refresh, baris tidak didobel
        msg = f"Tersimpan {saved} postingan."
        if updated:
            msg += f" {updated} diperbarui (sudah ada)."
        if skipped:
            msg += f" {len(skipped)} dilewati."
        self.send_json({"ok": True, "saved": saved, "updated": updated,
                        "skipped": skipped, "msg": msg})


def seed_accounts():
    import csv
    # salinan accounts.csv dibundel di paket ini (hasil generate 2026-10-10
    # dari spreadsheet PEMANTAUAN: 223 akun, kode 143-200)
    src = os.path.join(ROOT, "accounts.csv")
    n = 0
    with open(src, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            db.add_account(row.get("kode", ""), row["platform"],
                           row["username"], row.get("link_profile", ""))
            n += 1
    return n


URL_RE = re.compile(r"https?://[^\s<>'\")\],;]+", re.I)


def _is_post_url(url):
    """Heuristik: apakah URL ini link postingan (bukan link profil)?"""
    u = url.lower()
    if "tiktok.com" in u or "vt.tiktok" in u or "tt.site" in u:
        # /video/<id>, shortcode /t/ZSxxx atau /ZSxxx, dan shortlink vt./vm.
        if "/video/" in u or "vt.tiktok" in u or "tt.site" in u:
            return True
        path = urllib.parse.urlparse(u).path.rstrip("/")
        return bool(re.search(r"/(?:t/)?ZS[A-Za-z0-9]{6,}$", path, re.I))
    if "instagram.com" in u:
        # postingan: /(p|reel|tv)/<shortcode> — tolak tab profil /<user>/reels/
        path = urllib.parse.urlparse(u).path.rstrip("/")
        return bool(re.search(r"/(p|reel|tv|reels)/[A-Za-z0-9_-]{4,}$", path))
    if "threads.com" in u or "threads.net" in u:
        return "/post/" in u or "/share/" in u or "/t/" in u
    if "facebook.com" in u or "fb.watch" in u:
        # Halaman yang MEMANG _: video, watch, reels, photo, posts, share.
        # Modul ini sebelumnya tidak punya cabang Facebook sama sekali, jadi
        # SEMUA link FB dianggap link profil (terverifikasi 2026-10-12).
        host = urllib.parse.urlparse(u).netloc
        path = urllib.parse.urlparse(u).path.rstrip("/")
        # fb.watch/<kode> SELALU link video/postingan, tidak pernah profil.
        if host.endswith("fb.watch"):
            return bool(re.search(r"/[A-Za-z0-9_-]{4,}", path))
        if "/share/" in path or "/posts/" in path or "/permalink/" in path:
            return True
        if path.startswith("/watch") or path.startswith("/reel/") \
                or "/reels/" in path:
            return True
        if path.startswith("/photo") or "fbid=" in u:
            return True
        # /videos/<id> bisa preceded nama profil, dipisah '/' atau '.':
        #   /nama.videos/123   /username/videos/123   /videos/123
        if re.search(r"[/.]videos?/\d+", path) \
                or re.search(r"[/.]reels?/[A-Za-z0-9_-]+", path):
            return True
        if re.search(r"/story_fbid=|/permalink\.php", u):
            return True
        return False
    return False


def extract_links_from_excel(file_bytes, filename="", max_links=2000):
    """Pindai SEMUA sheet & sel -> kumpulkan URL postingan.

    Membaca teks sel DAN hyperlink sel. Mengembalikan dict:
    links (postingan, dedupe, urutan kemunculan), total_ditemukan,
    per_platform, dilewati_profil, dilewati_facebook, dipotong.
    """
    sheets = sheetio.read_sheets(file_bytes, filename, hyperlinks=True)
    found, seen = [], set()
    for sh in sheets:
        for row in sh.rows:
            for cell in row:
                texts = []
                v = getattr(cell, "value", None)
                if isinstance(v, str):
                    texts.append(v)
                hl = getattr(cell, "hyperlink", None)
                if hl and isinstance(getattr(hl, "target", None), str):
                    texts.append(hl.target)
                if not texts and isinstance(cell, str):
                    texts.append(cell)  # csv/xls: nilai sudah berupa teks
                for t in texts:
                    for m in URL_RE.findall(t):
                        url = m.rstrip(".,;!?)")
                        if url not in seen:
                            seen.add(url)
                            found.append(url)
    links, skipped_profile, skipped_fb, per_plat = [], 0, 0, {}
    for url in found:
        plat = scrape.detect_platform(url)
        if not plat:
            continue
        per_plat[plat] = per_plat.get(plat, 0) + 1
        if _is_post_url(url):
            links.append(url)
        elif plat == "facebook":
            # Link profil/grup Facebook BUKAN postingan -> lewati, tapi tetap
            # dihitung supaya user tahu kenapa tidak masuk.
            # CATATAN: dulu SEMUA link FB dilewati dengan komentar "gagal pasti
            # tanpa login". Itu tidak lagi benar - FB bisa di-scrape selama
            # cookie sesi ada (terverifikasi 2026-10-12: author, like, komen,
            # share, tanggal semua terbaca). Yang tetap tidak bisa hanyalah
            # halaman profil, dan itu memang bukan postingan.
            skipped_fb += 1
        else:
            skipped_profile += 1
    return {
        "links": links[:max_links],
        "total_ditemukan": len(found),
        "per_platform": per_plat,
        "dilewati_profil": skipped_profile,
        "dilewati_facebook": skipped_fb,
        "dipotong": max(0, len(links) - max_links),
    }


HEADER_WORDS = ("username", "user name", "akun", "nama akun")
SKIP_USERNAMES = {"username", "user", "akun", "nama", "nama akun", "-", "—", ""}


def _first_url_in(row):
    for c in row:
        if isinstance(c, str):
            m = URL_RE.search(c)
            if m:
                return m.group(0).rstrip(".,;!?)")
    return ""


def import_excel_accounts(file_bytes, filename=""):
    """Baca file .xlsx / .xls / .csv -> upsert akun.

    Xlsx: satu sheet per platform (INSTAGRAM/TIKTOK/THREADS/FACEBOOK),
    kolom: A=No(kode), B=Username, C=Link Profile; baris judul dilewati
    otomatis. Csv: kolom 'platform' opsional (atau dari nama file).
    """
    sheets = sheetio.read_sheets(file_bytes, filename)
    n, per_plat, tanpa_platform = 0, {}, 0
    for sh in sheets:
        header, rows = sh.prepare(HEADER_WORDS)
        plat_sheet = sheetio.platform_from_name(sh.name)
        plat_from_name = plat_sheet or sheetio.platform_from_name(
            os.path.splitext(os.path.basename(filename or ""))[0])
        c_kode = sheetio.col_index(header, ("no", "kode", "id"), 0)
        c_user = sheetio.col_index(header, ("username", "user", "akun",
                                            "nama"), 1)
        c_link = sheetio.col_index(header, ("link", "url", "profil",
                                            "profile"), 2)
        c_plat = sheetio.col_index(header, ("platform", "sosmed"), -1)
        for row in rows:
            username = sheetio.cell(row, c_user)
            if not isinstance(username, str):
                continue
            username = username.strip()
            if username.lower() in SKIP_USERNAMES:
                continue
            plat = (sheetio.platform_from_name(sheetio.cell(row, c_plat))
                    or plat_from_name)
            if not plat:
                tanpa_platform += 1
                continue
            kode = sheetio.cell(row, c_kode)
            try:
                kode_s = str(int(float(kode))) if kode is not None else ""
            except (TypeError, ValueError):
                kode_s = str(kode).strip() if kode is not None else ""
            link = sheetio.cell(row, c_link)
            link_s = str(link).strip() if isinstance(link, str) else ""
            if not link_s:
                link_s = _first_url_in(row)
            db.add_account(kode_s, plat, username, link_s)
            per_plat[plat] = per_plat.get(plat, 0) + 1
            n += 1
    if not n:
        raise ValueError(
            "Tidak ada akun yang terbaca dari file itu. Pastikan: "
            "(1) format .xlsx atau .csv; "
            "(2) ada kolom 'Username'; "
            "(3) platform terdeteksi — sheet/bernama file berisi "
            "INSTAGRAM/TIKTOK/THREADS/FACEBOOK, atau ada kolom 'Platform'"
            + (f". {tanpa_platform} baris dilewati karena platformnya tidak "
               "dikenali." if tanpa_platform else "."))
    return {"imported": n, "per_platform": per_plat,
            "tanpa_platform": tanpa_platform}


# ---------------- logging ----------------
_LOG_READY = False


def setup_logging():
    """Log ke data/app.log (rotasi 2 MB x 3) + stdout.

    Tanpa ini, kalau aplikasi dijalankan sebagai service/systemd, riwayat
    error hilang begitu terminal ditutup — padahal scraping berjalan
    puluhan menit dan error justru yang paling perlu ditelusuri.
    """
    global _LOG_READY
    if _LOG_READY:
        return
    import logging
    from logging.handlers import RotatingFileHandler
    try:
        os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
        h = RotatingFileHandler(os.path.join(ROOT, "data", "app.log"),
                                maxBytes=2 * 1024 * 1024, backupCount=3,
                                encoding="utf-8")
        h.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        logging.basicConfig(level=logging.INFO, handlers=[h, logging.StreamHandler()])
        try:
            os.chmod(os.path.join(ROOT, "data", "app.log"), 0o600)
        except OSError:
            pass
    except OSError:
        logging.basicConfig(level=logging.INFO)      # minimal ke stdout
    _LOG_READY = True


def install_shutdown_handlers():
    """SIGTERM/SIGINT -> tandai job yang jalan, lalu keluar rapi.

    Job 40 menit yang sedang jalan tidak bisa di-serialize, tapi penandaan
    membuat UI bisa menampilkan sisa link untuk diulang (retry_link_job).
    """
    import signal

    def berhenti(signum, _frm):
        with jobs_lock:
            jalan = [j["id"] for j in jobs.values()
                     if j.get("status") == "running"]
        for jid in jalan:
            try:
                save_job_checkpoint(jid)
                with jobs_lock:
                    jobs[jid]["status"] = "stopped"
                    jobs[jid]["result"] = {
                        "ok": jobs[jid]["ok"], "fail": jobs[jid]["fail"],
                        "stopped": True}
            except Exception:  # noqa: BLE001
                pass
        print(f"\n[PantauAkun] signal {signum}: {len(jalan)} job ditandai "
              f"terhenti & checkpoint disimpan. Sisa link bisa diulang dari UI.")
        sys.exit(0)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, berhenti)
        except (ValueError, OSError):
            pass          # bukan main thread / tidak didukung


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    setup_logging()
    db.init()
    install_shutdown_handlers()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"PantauAkun jalan di http://localhost:{args.port}")
    print(f"Database: {db.DB_PATH}")
    print(f"Log     : {os.path.join(ROOT, 'data', 'app.log')}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
