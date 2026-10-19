#!/usr/bin/env python3
"""Pekerja scraping PantauAkun — memakai ulang fetchers/ dari akun-monitor.

Fungsi utama:
  detect_platform(url) -> 'tiktok' | 'instagram' | 'threads' | 'facebook' | None
  scrape_post(url)     -> dict metrik satu postingan (tanpa login)
  fetch_threads_account(username, sejak, sampai) -> daftar postingan dlm rentang
"""
import datetime
import os
import random
import re
import socket
import threading
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import textsafe
import wibtime as wib
from fetchers import tiktok as ft_tiktok
from fetchers import instagram as ft_instagram
from fetchers import threads as ft_threads

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def detect_platform(url):
    u = (url or "").lower()
    if "tiktok.com" in u or "tt.site" in u or "vt.tiktok" in u:
        return "tiktok"
    if "instagram.com" in u:
        return "instagram"
    if "threads.com" in u or "threads.net" in u:
        return "threads"
    if "facebook.com" in u or "fb.watch" in u:
        return "facebook"
    return None


GBOT_UA = ("Mozilla/5.0 (compatible; Googlebot/2.1; "
            "+http://www.google.com/bot.html)")


def resolve_url(url, timeout=30, ua=None):
    """Ikuti redirect (link pendek vt.tiktok.com / tt.site / share threads)."""
    req = urllib.request.Request(url, headers={"User-Agent": ua or UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl()


# ---------- normalisasi URL ----------
# Dipakai SEBELUM resolve: beberapa bentuk link umum tidak bisa dibuka TikTok
# walau shortcode-nya sama (lihat test_url_variants).

RE_TT_SHORT = re.compile(
    r"^(https?://(?:www\.|m\.)?tiktok\.com)/(ZS[A-Za-z0-9]{6,})/?$", re.I)


def normalize_tiktok_url(url):
    """'tiktok.com/ZSxxx' -> 'tiktok.com/t/ZSxxx'.

    Tanpa '/t/', TikTok menjawab 404 meski shortcode-nya valid. Hanya
    domain www./m. yang perlu; vt./vm. sudah benar sejak awal.
    """
    m = RE_TT_SHORT.match((url or "").strip())
    if m:
        return f"{m.group(1)}/t/{m.group(2)}"
    return url


def normalize_url(url):
    """Rapikan URL sebelum scrape (per platform)."""
    u = (url or "").strip()
    if u and "://" not in u:      # 'tiktok.com/x' -> tambahkan skema
        u = "https://" + u
    plat = detect_platform(u)
    if plat == "tiktok":
        return normalize_tiktok_url(u)
    if plat == "instagram":
        # '/reels/<code>' (tab profil) -> '/reel/<code>' (permalink)
        return ft_instagram.normalize_url(u)
    return u


class ScrapeFailed(Exception):
    """Kegagalan scrape yang sudah diklasifikasikan.

    retryable=False -> permanen (jangan buang waktu retry):
      platform tak dikenal, Facebook tanpa login, link bukan postingan.
    retryable=True (default) -> transien: timeout, 429/5xx, putus koneksi.
    """
    def __init__(self, message, retryable=True):
        super().__init__(message)
        self.retryable = retryable


def _is_retryable(exc):
    if isinstance(exc, ScrapeFailed):
        return exc.retryable
    if isinstance(exc, ft_tiktok.WAFChallenge):
        return True   # rate limit sementara — retry berguna
    if isinstance(exc, ValueError):
        # "blob tidak ditemukan" tanpa tanda 404/login/WAF = struktur berubah
        return False
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in (408, 425, 429, 500, 502, 503, 504)
    if isinstance(exc, (TimeoutError, ConnectionResetError,
                        ConnectionRefusedError, ConnectionAbortedError)):
        return True
    if isinstance(exc, urllib.error.URLError):
        return True  # bukan HTTPError -> murni masalah jaringan
    return False


def _retry_after_seconds(exc, default, cap=300):
    """Baca header Retry-After (detik / tanggal HTTP). Nilai server bersifat
    otoritatif — patuhi persis; fallback ke default bila tidak ada."""
    try:
        val = (exc.headers or {}).get("Retry-After")
        if not val:
            return default
        val = val.strip()
        if val.isdigit():
            return min(int(val), cap)
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)  # "-0000" = tak diketahui -> anggap UTC
        secs = (dt - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
        return min(max(secs, 0), cap)
    except Exception:
        return default


def scrape_with_retry(url, attempts=3, base_delay=2.0, cookies=None):
    """Scrape satu URL dengan retry + exponential backoff + jitter.

    429/503: hormati header Retry-After bila ada (otoritatif).
    cookies: dict cookie sesi untuk platform URL ini (opsional).
    Kembalikan dict hasil (dengan kunci _attempts). Bila semua gagal,
    lempar ScrapeFailed terakhir (membawa atribut .retryable).
    """
    last = None
    for a in range(1, attempts + 1):
        try:
            d = scrape_post(url, cookies=cookies)
            d["_attempts"] = a
            return d
        except Exception as e:  # noqa: BLE001 - klasifikasi di bawah
            last = e
            if not _is_retryable(e) or a == attempts:
                break
            if isinstance(e, urllib.error.HTTPError) and e.code in (429, 503):
                delay = _retry_after_seconds(e, base_delay * (2 ** (a - 1)))
            else:
                delay = base_delay * (2 ** (a - 1))
            time.sleep(delay + random.uniform(0, 1.5))
    err = ScrapeFailed(str(last)[:200], retryable=_is_retryable(last))
    err.attempts = attempts          # supaya UI bisa menampilkan jumlah percobaan
    raise err


# Keandalan tanggal per platform (dipakai fitur audit di UI).
#
# "exact" = timestamp asli dari epoch (detik), jam & menit trustworthy.
# "day"   = HANYA tanggal yang dikirim platform, TIDAK ADA jam sama sekali;
#           jam 00:00 yang tersimpan adalah placeholder, bukan waktu unggah sebenarnya.
#           Terverifikasi 2026-10-11: Instagram tidak punya taken_at_timestamp,
#           JSON-LD datePublished, maupun uploadDate — og:date hanya berisi
#           "October 1, 2026". Posting IG jam 23:00 WIB bisa saja tercatat
#           00:00, jadi tanggalnya benar tapi jamnya tidak dapat dipercaya.
# "none"  = tanggal tidak ditemukan sama sekali.
DATE_PRECISION = {"tiktok": "exact", "threads": "exact", "facebook": "exact",
                  "instagram": "day"}


def date_precision(platform, posted_at):
    """Tingkat keyakinan tanggal: 'exact' | 'day' | 'none'."""
    if not posted_at:
        return "none"
    return DATE_PRECISION.get(platform, "exact")


def scrape_post(url, cookies=None):
    """Scrape satu URL postingan. Return dict siap simpan.

    cookies: dict cookie sesi (opsional). Tanpa cookie = mode tanpa login.
    Dengan cookie: Facebook bisa dibaca; Threads berpotensi menyertakan views.

    Raises ScrapeFailed bila platform tak didukung / gagal.
    """
    url = normalize_url(url)
    platform = detect_platform(url)
    if platform == "tiktok":
        final = resolve_url(url)
        d = ft_tiktok.fetch_video(final)
        return {"platform": "tiktok", "url": url.strip(),
                "date_precision": date_precision("tiktok", d.get("posted_at_utc")),
                "post_key": d.get("post_id") or "",
                "author": d.get("author") or "",
                "posted_at": d.get("posted_at_utc"),
                "caption": d.get("caption") or "",
                "views": d.get("views"), "komen": d.get("komen"),
                "share": d.get("share"), "like": d.get("like"),
                "repost": d.get("repost")}
    if platform == "instagram":
        d = ft_instagram.fetch_post(url.strip())
        return {"platform": "instagram", "url": url.strip(),
                "date_precision": date_precision("instagram", d.get("posted_at_utc")),
                "post_key": d.get("post_id") or "",
                "author": d.get("owner") or "",
                "posted_at": d.get("posted_at_utc"),
                "caption": d.get("caption") or "",
                "views": d.get("views"), "komen": d.get("komen"),
                "share": d.get("share"), "like": d.get("like"),
                "repost": d.get("repost")}
    if platform == "threads":
        # Permalink (/@user/post/<code>) tidak perlu resolve — sudah final.
        # Hanya link /share/ yang harus diikutkan (hemat 1 request/link).
        if re.search(r"threads\.(?:com|net)/@[^/]+/post/[A-Za-z0-9_-]+",
                     url.split("?")[0]):
            final = url.strip()
        else:
            final = resolve_url(url, ua=GBOT_UA)
        m = re.search(r"threads\.(?:com|net)/@([^/]+)/post/([A-Za-z0-9_-]+)", final)
        if not m:
            if "error=invalid_post" in final:
                raise ScrapeFailed(
                    "link Threads mati (error=invalid_post) — posting "
                    "dihapus atau link share-nya sudah tidak berlaku.",
                    retryable=False)
            if "/login" in final.lower():
                raise ScrapeFailed("Threads meminta login — sesi tidak cukup",
                                   retryable=False)
            if "/share/" in final:
                # Threads tidak redirect DAN tidak bilang error -> kode share
                # ini sudah tidak berlaku (dihapus / salah ketik).
                raise ScrapeFailed(
                    "link share Threads tidak bisa di-resolve (Threads tidak "
                    "mengarahkan ke postingan) — kemungkinan posting sudah "
                    "dihapus. Coba link /@user/post/<code> bila ada.",
                    retryable=False)
            raise ScrapeFailed(
                f"link Threads tidak dikenali (akhirnya {final[:60]})",
                retryable=False)
        username, code = m.group(1), m.group(2)
        d = scrape_threads_single(final, cookies=cookies)
        d["author"] = username
        d["url"] = f"https://www.threads.com/@{username}/post/{code}"
        d["date_precision"] = date_precision("threads", d.get("posted_at"))
        return d
    if platform == "facebook":
        if not cookies:
            raise ScrapeFailed("Facebook butuh sesi login — isi cookie di Pengaturan, atau isi manual",
                               retryable=False)
        return scrape_facebook_post(url.strip(), cookies)
    raise ScrapeFailed("platform tidak dikenali dari URL", retryable=False)


def _threads_crawler_html(post_url, cookies=None):
    """HTML Threads dengan UA crawler — sumber UTAMA metrik posting.

    WAJIB UA crawler: dengan UA browser biasa, Threads serving JS shell
    (~276KB) tanpa field metrik sama sekali.

    Cookie BOLEH dan justru LEBIH BAIK: dengan cookie + UA crawler Threads
    mengirim SSR lengkap (773KB) termasuk VIEW COUNT ("3 views" pada span).
    Verified 2026-10-11: tanpa cookie 620KB tanpa views; dengan cookie
    773KB + views. View count hanya ada untuk akun yang mengaktifkan
    view publik (butuh >10rb views/30 hari — lihat catatan di README).
    """
    h = {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; "
                       "+http://www.google.com/bot.html)",
         "Accept-Language": "en-US,en;q=0.9"}
    if cookies:
        h["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    req = urllib.request.Request(post_url, headers=h)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", errors="replace")


THREADS_VIEW_RE = re.compile(r'>\s*([\d.,]+\s?[KMB]?)\s+views\s*<', re.I)


def _threads_html_variants(post_url, cookies):
    """Urutan percobaan diambil, dari yang PALING mungkin memberi views.

    1. UA crawler + cookie -> satu-satunya kombinasi yang menghasilkan views
    2. UA crawler tanpa cookie (cadangan)
    """
    out = []
    if cookies:
        out.append(("cookie", lambda: _threads_crawler_html(post_url, cookies)))
    out.append(("anon", lambda: _threads_crawler_html(post_url)))
    return out


def scrape_threads_single(post_url, cookies=None, tries=3):
    """Scrape satu halaman postingan Threads.

    Views Threads TERKADANG hilang pada respons pertama: Threads sesekali
    mengirim SSR tanpa blok viewer (JS shell) walau cookie masih valid.
    Karena itu bila field 'views' belum muncul, halaman diambil lagi sampai
    `tries` kali. Metrik lain (like/reply/repost) tidak suffers - hanya views
    yang bergantung pada render logged-in.

    Retry HANYA untuk kasus "field hilang", bukan untuk 404 / Posting mati
    (itu langsung gagal final, hemat waktu).
    """
    variants = _threads_html_variants(post_url, cookies)
    primary_label, primary_fetch = variants[0]
    data = None
    n_sukses = 0          # berapa fetch yang benar-benar dapat HTML
    err_terakhir = None
    for attempt in range(tries):
        # SELALU pakai varian cookie untuk retry. Beralih ke varian tanpa
        # cookie tidak akan pernah menghasilkan views (padahal itu tujuan
        # retry-nya) - itu bug yang sempat terjadi.
        label, fetch = primary_label, primary_fetch
        src = None
        try:
            src = fetch()
        except Exception as e:  # noqa: BLE001 - cookie/network gagal -> anon
            err_terakhir = e
            if len(variants) > 1:
                label, fetch = variants[-1]
                try:
                    src = fetch()
                except Exception as e2:  # noqa: BLE001
                    err_terakhir = e2
                    continue
            else:
                continue
        n_sukses += 1
        data = _threads_parse(src)
        if data is None:
            # Respons tanpa satu pun field interaksi. Dulu langsung dianggap
            # "posting mati" -> gagal permanen. TapiKENYATAANNYA sering hanya
            # respons JS-shell sesaat: link yang sama berhasil 5/5 saat diuji
            # serial (terverifikasi 2026-10-11, post DeTePQKEuR9 gagal 1x
            # pada batch paralel lalu OK 5x berturut-turut). Jadi coba lagi
            # dulu; baru setelah semua percobaan gagal dia dianggap permanen.
            if attempt + 1 < tries:
                time.sleep(0.8 + attempt * 0.7)
                continue
            break
        if data.get("views") is None and attempt + 1 < tries:
            time.sleep(1.0 + attempt * 0.7)   # jeda singkat, hindari WAF
            continue
        data["_views_source"] = label
        return data
    if data is None:
        # PENTING: bedakan "halaman TZ-nya benar-benar tidak ada data"
        # (permanen) dari "semua fetch gagal" (sementara). Versi lama
        # menandai keduanya retryable=False, jadi timeout/DNS membuat
        # scrape_with_retry menyerah tanpa mencoba lagi -> posting hilang
        # hanya karena jaringan sesaat.
        if n_sukses == 0:
            raise ScrapeFailed(
                "gagal membuka halaman Threads ("
                + (type(err_terakhir).__name__ if err_terakhir else "tidak diketahui")
                + ") — masalah jaringan/DNS, mencoba lagi mungkin berhasil.",
                retryable=True)
        raise ScrapeFailed(
            "Threads tidak mengirim data interaksi untuk Posting ini "
            "(privat / dihapus / tidak ada).", retryable=False)
    data["_views_source"] = "tidak ditemukan"
    return data


def _clean_text(s):
    """Bersihkan escape JSON dari teks: \\n -> baris baru, \\" -> ", \\uXXXX."""
    if not s:
        return ""
    s = re.sub(r'\\u([0-9a-fA-F]{4})',
               lambda m: chr(int(m.group(1), 16)), s)
    s = s.replace("\\n", "\n").replace("\\t", " ").replace("\\r", " ")
    s = s.replace('\\"', '"').replace("\\\\", "\\")
    return textsafe._fix_surrogates(s)


def _threads_parse(src):
    """Parse payload Threads -> dict metrik, atau None kalau tidak ada data."""

    def one(pat):
        m = re.search(pat, src)
        return m.group(1) if m else None

    def num(pat):
        """Angka -> int, atau None kalau field-nya memang tidak ada."""
        v = one(pat)
        return int(v) if v is not None else None

    # post_key: ambil dari URL (pasti milik postingan ini), bukan dari
    # "code" pertama di halaman — yang bisa milik artikel lain.
    code = one(r"/post/([A-Za-z0-9_-]{6,})") or one(r'"code":"([A-Za-z0-9_-]{6,})"')
    like = num(r'"like_count":(\d+)')
    komen = num(r'"direct_reply_count":(\d+)')
    repost = num(r'"repost_count":(\d+)')
    quote = num(r'"quote_count":(\d+)')
    views = num(r'"view_count":(\d+)')
    if views is None:
        views = num(r'"video_view_count":(\d+)')
    if views is None:
        # View count hanya dirender di HTML saat PENGGUNA LOGGED IN, dan
        # bentuknya teks berformat: "<span ...>3 views</span>".
        # Verified 2026-10-11: tanpa cookie -> tidak ada; dengan cookie ->
        # muncul. Hanya akun dengan view publik (>10rb views/30 hari).
        m = THREADS_VIEW_RE.search(src)
        if m:
            views = _parse_compact(m.group(1))
    share = num(r'"share_count":(\d+)')
    caption = _clean_text(
        one(r'"caption":\{"text":"((?:[^"\\]|\\.)*)"') or "")[:200]
    ts = one(r'"taken_at":(\d+)')
    epoch = int(ts) if ts else 0
    posted = wib.to_wib_str(epoch)
    if not any(v is not None for v in (like, komen, repost)):
        return None
    return {"platform": "threads", "url": "",
            "post_key": code or "", "author": "",
            "posted_at": posted, "caption": caption,
            "views": views, "komen": komen,
            "share": share, "like": like,
            "repost": (repost or 0) + (quote or 0)}


def fetch_threads_account(username, sejak, sampai):
    """Ambil postingan 1 akun Threads, filter rentang tanggal (date UTC).

    sejak/sampai: 'YYYY-MM-DD'. Return list[dict] siap simpan.
    """
    prof, posts = ft_threads.fetch_account(username)
    out = []
    for p in posts:
        d = (p.get("posted_at_utc") or "")[:10]
        if sejak <= d <= sampai:
            out.append({"platform": "threads",
                        "url": p.get("permalink") or "",
                        "post_key": p.get("post_id") or "",
                        "author": username,
                        "posted_at": p.get("posted_at_utc"),
                        "caption": p.get("caption") or "",
                        "views": None, "komen": p.get("komen"),
                        "share": None, "like": p.get("like"),
                        "repost": p.get("repost")})
    return out


# ---------------- sesi login: listing per akun & Facebook ----------------
# Semua fungsi di bawah BUTUH cookie sesi login (akun admin). Tanpa cookie
# = mode tanpa login seperti sebelumnya.


def fetch_instagram_account(username, cookies, limit=30):
    """Daftar postingan akun IG (~30 terbaru) — BUTUH sesi login.

    Pakai endpoint web_profile_info yang 429 tanpa sesi.
    Kembalikan list dict {url, post_key, posted_at}.
    """
    import session as _sess
    import json as _json
    s, body, _u = _sess.fetch(
        "https://i.instagram.com/api/v1/users/web_profile_info/?username="
        + username.lstrip("@").strip(),
        cookies,
        headers={"X-IG-App-ID": "936619743392459", "Accept": "application/json"},
        timeout=30)
    if s != 200:
        raise ScrapeFailed(f"Instagram HTTP {s} — sesi mungkin kedaluwarsa / kena limit",
                           retryable=s in (429, 503))
    try:
        media = _json.loads(body)["data"]["user"]["edge_owner_to_timeline_media"]
    except (KeyError, ValueError) as e:
        raise ScrapeFailed(f"respons IG tak dikenal: {e}", retryable=False)
    out = []
    for e in (media.get("edges") or [])[:limit]:
        n = e.get("node") or {}
        code = n.get("shortcode")
        if not code:
            continue
        ts = n.get("taken_at_timestamp")
        out.append({
            "url": f"https://www.instagram.com/p/{code}/",
            "post_key": code,
            "posted_at": wib.to_wib_str(ts),
        })
    if not out:
        raise ScrapeFailed("daftar postingan kosong — akun privat / sesi tidak cukup",
                           retryable=False)
    return out


# ---------------- cek follow (relasi terhadap akun PEMILIK SESI) ----------------
# Riset 2026-10-19 (hasil terverifikasi):
#   * Instagram TIDAK mengekspos relasi follow secara publik. Tidak ada jalur
#     tanpa login: `web_profile_info` kini sering balas HTTP 400 "make sure you
#     are logged in", dan daftar follower/following ditutup untuk scraper.
#   * Satu-satunya jalur = private API dengan cookie sesi.
#   * `friendships/show/<id>/` mengembalikan relasi RELATIF terhadap akun
#     PEMILIK SESI (akun admin), BUKAN relasi antar dua akun sembarang:
#         following        -> akun admin sudah follow target
#         followed_by      -> target follow balik akun admin
#         outgoing_request -> permintaan follow admin menunggu (target privat)
#         incoming_request -> target minta follow admin
#     Ref: instagram_private_api docs -> friendships.show()
#   * Karena itu fitur "cek follow" hanya bermakna untuk relasi vs akun admin.
#     Untuk "A follow B" antar akun sembarang, dibutuhkan sesi akun A.
#   * Jalur ini bukan API resmi: patuhi jeda sopan, dan pahami risikonya
#     (rate-limit / pembatasan akun admin). Lihat README.

IG_APP_ID = "936619743392459"      # web app id (sama dgn listing akun IG)


def _ig_private_api(path, cookies, timeout=30):
    """GET ke i.instagram.com/api/v1/<path> memakai cookie sesi login."""
    import session as _sess
    return _sess.fetch("https://i.instagram.com/api/v1/" + path.lstrip("/"),
                       cookies,
                       headers={"X-IG-App-ID": IG_APP_ID,
                                "Accept": "application/json"},
                       timeout=timeout)


def _ig_json(status, body, what):
    """Parse JSON respons IG dengan pesan kesalahan yang jujur.

    Pesan sengaja memuat frasa "sesi login" supaya deteksi sesi-mati di
    app.py (_AUTH_HINTS) mengenalinya dan lane berhenti, bukan gagal
    diam-diam satu per satu.
    """
    import json as _json
    if status != 200:
        raise ScrapeFailed(
            f"sesi login Instagram bermasalah (HTTP {status}) saat {what} — "
            f"cookie kedaluwarsa, kena rate-limit, atau akun dibatasi. "
            f"Isi ulang cookie di Pengaturan.",
            retryable=status in (429, 500, 502, 503, 504))
    try:
        return _json.loads(body or "{}")
    except ValueError:
        raise ScrapeFailed(f"respons Instagram tak dikenal saat {what}",
                           retryable=False)


def fetch_instagram_self(cookies):
    """Akun yang sedang login (label "akun admin"). None bila gagal.

    Tidak pernah melempar: kegagalan di sini hanya berarti label admin
    tidak tersedia, bukan kegagalan cek follow.
    """
    try:
        status, body, _ = _ig_private_api(
            "accounts/current_user/?edit=false", cookies, timeout=20)
        if status != 200:
            return None
        u = (__import__("json").loads(body or "{}") or {}).get("user") or {}
        if not u:
            return None
        return {"id": str(u.get("pk") or u.get("id") or ""),
                "username": u.get("username") or "",
                "full_name": u.get("full_name") or ""}
    except Exception:  # noqa: BLE001 - label opsional
        return None


def fetch_instagram_profile(username, cookies, timeout=30):
    """Profil ringkas IG (id, jumlah follower/following, privat) — BUTUH sesi."""
    status, body, _ = _ig_private_api(
        "users/web_profile_info/?username=" + username.lstrip("@").strip(),
        cookies, timeout)
    d = _ig_json(status, body, f"membaca profil @{username.lstrip('@')}")
    u = (d.get("data") or {}).get("user")
    if not u:
        raise ScrapeFailed(
            f"profil @{username.lstrip('@')} tidak dikembalikan Instagram "
            f"(akun dihapus/diblokir, atau sesi tidak cukup)", retryable=False)
    return {"id": str(u.get("id") or ""),
            "username": u.get("username") or username.lstrip("@"),
            "full_name": u.get("full_name") or "",
            "is_private": bool(u.get("is_private")),
            "is_verified": bool(u.get("is_verified")),
            "follower_count": (u.get("edge_followed_by") or {}).get("count"),
            "following_count": (u.get("edge_follow") or {}).get("count")}


def fetch_instagram_friendship(target_user_id, cookies, timeout=30):
    """Relasi akun sesi (admin) dengan target_user_id — BUTUH sesi.

    Kembalikan dict boolean (None = Instagram tidak mengirim field itu).
    """
    status, body, _ = _ig_private_api(
        f"friendships/show/{target_user_id}/", cookies, timeout)
    d = _ig_json(status, body, "cek relasi follow")

    def _b(k):
        v = d.get(k)
        return None if v is None else bool(v)

    return {"following": _b("following"),
            "followed_by": _b("followed_by"),
            "outgoing_request": _b("outgoing_request"),
            "incoming_request": _b("incoming_request"),
            "is_private": _b("is_private"),
            "blocking": _b("blocking")}


def new_rank_token():
    """UUID untuk penelusuran daftar following.

    rank_token harus UUID valid (instagram_private_api memanggil
    raise_if_invalid_rank_token) dan harus SAMA untuk semua halaman dalam
    satu penelusuran.
    """
    return str(uuid.uuid4())


def fetch_instagram_following_page(user_id, cookies, rank_token,
                                   max_id=None, timeout=30):
    """Satu halaman daftar "following" (siapa yang diikuti) milik user_id.

    BUTUH sesi — tetapi TIDAK harus sesi milik user_id: satu sesi sehat
    cukup untuk membaca daftar following akun PUBLIK mana pun. Inilah yang
    membuat "akun sumber" bisa dipilih bebas, bukan cuma akun admin.

    Ref: instagram_private_api docs -> user_following(); instagrapi
    `user_following_v1_chunk`. Jalur public GraphQL query_hash sudah MATI
    (edges selalu kosong walau sesi valid) — instagrapi issue #2798.

    Kembalikan {"users": [{"id", "username"}], "next_max_id", "more"}.
    """
    q = "rank_token=" + urllib.parse.quote(str(rank_token))
    if max_id:
        q += "&max_id=" + urllib.parse.quote(str(max_id))
    status, body, _ = _ig_private_api(
        f"friendships/{user_id}/following/?{q}", cookies, timeout)
    d = _ig_json(status, body, "membaca daftar following")
    users = d.get("users") or []
    return {
        "users": [{"id": str(u.get("pk") or u.get("id") or ""),
                   "username": (u.get("username") or "").lower()}
                  for u in users if isinstance(u, dict)],
        "next_max_id": d.get("next_max_id") or None,
        "more": bool(d.get("next_max_id")),
    }


# Host Facebook yang dicoba berurutan. www.facebook.com adalah yang utama,
# tapi di beberapa jaringan (dumps DNS, firewall kantor, sandbox) host itu
# diblokir sementara m./free./mbasic tetap hidup — markup mbasic jauh lebih
# sederhana sehingga metriknya justru lebih mudah dibaca.
FB_HOSTS = ("www.facebook.com", "m.facebook.com", "free.facebook.com",
            "mbasic.facebook.com", "web.facebook.com")


def _fb_host_variants(url):
    """URL yang sama dengan host FB lain (untuk 邮编 dodge pemblokiran host)."""
    p = urllib.parse.urlsplit(url)
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    seen = [url]
    for h in FB_HOSTS:
        alt = urllib.parse.urlunsplit(("https", h, path, "", ""))
        if alt not in seen:
            seen.append(alt)
    return seen


def _fb_login_wall(html, final):
    """Apakah respons ini login wall / tidak terautentikasi?"""
    low = (final or "").lower()
    if "/login" in low or "login.php" in low or "/checkpoint" in low:
        return True
    head = html[:4000]
    if re.search(r"<title>\s*Log in", head, re.I):
        return True
    # mbasic/free sering balas "Error"/"Kesalahan" atau halaman login pendek
    if len(html) < 25000 and re.search(
            r'name="login_form"|"LoginConnect"|href="/login', head):
        return True
    return False


# Pola metrik Facebook. Facebook sering berubah markup, jadi tiap metrik
# punya beberapa pola; yang pertama ketemu yang dipakai.
FB_PATTERNS = {
    "like": [
        # Manifest 2026-11: field reaction_count lama DIHAPUS, diganti
        # unified_reactors.count (verified di HTML reel live).
        r'"unified_reactors"\s*:\s*\{\s*"count"\s*:\s*(\d+)',
        r'"reaction_count"\s*:\s*\{\s*"count"\s*:\s*(\d+)',
        r'"reaction_count_reduced"\s*:\s*"([\d.,]+[KMB]?)"',
        r'"i18n_reaction_count"\s*:\s*\{"count"\s*:\s*(\d+)',
        r'"reaction_count"\s*:\s*(\d+)',
        r'([\d.,]+[KMB]?)\s+[Rr]eactions?\b',
        r'([\d.,]+[KMB]?)\s+[Ll]ikes?\b',
    ],
    "komen": [
        # Post biasa (bukan reel) memakai "comments":{"total_count":N}
        # (verified 2026-10-11 pada /posts/<id>/).
        r'"comments"\s*:\s*\{\s*"total_count"\s*:\s*(\d+)',
        r'"total_comment_count"\s*:\s*(\d+)',
        r'"aggregated_comment_count"\s*:\s*(\d+)',
        r'"comment_count"\s*:\s*\{\s*"count"\s*:\s*(\d+)',
        r'"i18n_comment_count"\s*:\s*"?(\d+)"?',
        r'"comment_count"\s*:\s*(\d+)',
        r'"comments_count"\s*:\s*(\d+)',
        r'([\d.,]+[KMB]?)\s+[Cc]omments?\b',
    ],
    "share": [
        r'"share_count_reduced"\s*:\s*"([\d.,]+[KMB]?)"',
        r'"share_count"\s*:\s*\{\s*"?count"?\s*:\s*(\d+)',
        r'"i18n_share_count"\s*:\s*"?(\d+)"?',
        r'"share_count"\s*:\s*(\d+)',
        r'"shares_count"\s*:\s*(\d+)',
        r'"reshare_count"\s*:\s*\{"count"\s*:\s*(\d+)',
        r'([\d.,]+[KMB]?)\s+[Ss]hares?\b',
    ],
    "views": [
        r'"video_view_count"\s*:\s*(\d+)',
        r'"video_play_count"\s*:\s*(\d+)',
        r'"play_count"\s*:\s*(\d+)',
        r'"view_count"\s*:\s*(\d+)',
        r'([\d.,]+[KMB]?)\s+[Vv]iews?\b',
    ],
}

FB_DATE_PATTERNS = [
    r'"creation_time"\s*:\s*(\d{9,12})',
    r'"publish_time"\s*:\s*(\d{9,12})',
    r'"created_time"\s*:\s*(\d{9,12})',
    r'"publish_time"\s*:\s*"?(\d{9,12})"?',
    r'data-utime="(\d{9,12})"',
    r'"timestamp"\s*:\s*"?(1[5-9]\d{8})"?',
]

FB_ID_PATTERNS = [
    r'"post_id"\s*:\s*"(\d{6,})"',
    r'"feedback_id"\s*:\s*"post[:/](\d{6,})"',
    r'/posts/(\d{6,})',
    r'story_fbid=(\d{6,})',
    r'[?&]fbid=(\d{6,})',
    r'/videos/(\d{6,})',
    r'"top_level_post_id"\s*:\s*"(\d{6,})"',
]

# Halaman FB (terutama /reel/) menyertakanazioniyyy SRIP dari posting lain
# ("related stories"). Metrik harus diambil dari blok story yang COCOK dengan
# id primarias halaman, bukan kemunculan pertama — kalau tidak, angka yang
# masuk adalah angka neighboring post.
FB_STORY_MARK = re.compile(r'"creation_story"')
FB_PRIMARY_ID = re.compile(
    r'/(?:reel|videos)/(\d{6,})|/posts/(\d{6,})'
    r'|story_fbid=(\d{6,})|[?&]fbid=(\d{6,})')
FB_FEEDBACK_ID = re.compile(r'"feedback"\s*:\s*\{\s*"id"\s*:\s*'
                            r'"([A-Za-z0-9+/=]{8,})"')
FB_FEEDBACK_ID2 = re.compile(r'"id"\s*:\s*"([A-Za-z0-9+/=]{12,})"')


def _fb_post_id(text, url):
    """Id post yang dibuka (dari URL, fallback dari HTML)."""
    cands = _fb_post_ids(text, url)
    return next(iter(cands), None)


def _fb_post_ids(text, url):
    """KUMPULAN kandidat id untukcaaMILKI posting yang sedang dibuka.

    PENTING (bug terverifikasi 2026-10-12): Facebook memakai LEBIH DARI SATU
    sistem id untuk satu posting, dan keduanya muncul di halaman:

      /share/r/...  -> final URL = /reel/1454616163187868  (id REEL)
                       tapi token feedback = feedback:122115930873407588 (id POST)
      /share/p/...  -> final URL = /posts/pfbid0ySz...     (TIDAK ada id angka)
      /share/v/...  -> final URL = /story.php?story_fbid=... (tidak ada
                       feedback sama sekali)

    Versi lama hanya mengambil SATU id dari URL, sehingga untuk reel hasilnya
    tidak cocok dengan token feedback -> anchoring gagal -> parser jatuh ke
    SELURUH halaman -> angka Rekomendasi/post lain ikut terbaca. Terukur:
    halaman share/r/1CxrPBSRt9 punya reaction ['0', '3501'] dan yang 3501
    milik posting orang lain. Itulah "angka besar" yang dikeluhkan user.

    Di sini semua sumber id digabung supaya _fb_story_slice bisa mencoba
    semuanya.
    """
    out = []
    m = FB_PRIMARY_ID.search(url or "")
    if m:
        g = next((x for x in m.groups() if x), None)
        if g:
            out.append(g)
    for rx in (r'"post_id"\s*:\s*"(\d{6,})"',
               r'"top_level_post_id"\s*:\s*"(\d{6,})"'):
        out += re.findall(rx, text or "")
    seen, urut = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            urut.append(x)
    return urut


def _fb_viewer(text):
    """(id, nama) akun yang sedang login — dari HALAMAN YANG SAMA.

    Dipakai untuk MENOLAK nama viewer yang bisa salah tertangkap sebagai
    penulis posting. Tidak perlu request tambahan: blok
    `CurrentUserInitialData` sudah ada di setiap halaman Facebook.
    """
    mid = re.search(r'"ACCOUNT_ID"\s*:\s*"(\d+)"', text)
    mnm = re.search(r'"NAME"\s*:\s*"([^"]{2,60})"', text)
    return (mid.group(1) if mid else None,
            mnm.group(1) if mnm else None)


def _fb_actor_id(text, story, final):
    """Id aktor utama posting ini.

    Node story Facebook modern TIDAK memuat nama aktor, hanya id+url:
        "actors":[{"__typename":"User","url":".../id=12345678900000",
                   "id":"12345678900000"}]
    Karena itu nama harus dicari lewat id, bukan diambil bebas dari HTML.
    """
    story = story or ""      # _fb_story_slice boleh mengembalikan None
    # 1) actorID dari props/URL (paling presisi untuk story.php & posts/)
    m = re.search(r'"actorID"\s*:\s*(\d+)', story) \
        or re.search(r'"actorID"\s*:\s*(\d+)', text) \
        or re.search(r'[?&]id=(\d{6,})', final or "")
    if m:
        return m.group(1)
    # 2) entri pertama actors[] di dalam story/post yang dibuka
    m = re.search(r'"actors":\[\{"__typename":"(?:User|Page|Profile)",'
                  r'[^}]*?"id":"(\d+)"', story)
    if m:
        return m.group(1)
    m = re.search(r'"actors":\[\{"__typename":"(?:User|Page|Profile)",'
                  r'[^}]*?"id":"(\d+)"', text)
    return m.group(1) if m else None


def _fb_name_for_id(text, pid):
    """Nama profil yang terhubung ke id tsb (id -> name atau name -> id)."""
    for pat in (r'%s[^{}]{0,220}?"name"\s*:\s*"([^"]{2,60})"' % pid,
                r'"name"\s*:\s*"([^"]{2,60})"[^{}]{0,160}?%s' % pid):
        for m in re.finditer(pat, text):
            # _clean_text sudah men-decode \uXXXX, \", dll.
            nm = _clean_text(m.group(1)).strip()
            if len(nm) < 2 or nm.isdigit():
                continue
            return nm
    return None


def _fb_author(text, story, final):
    """Penulis posting Facebook.

    BUG lama (terverifikasi 2026-10-11): parser mencari nama di SELURUH
    HTML, jadi capturing blok `CurrentUserInitialData` -> nama akun yang
    sedang login. Semua posting orang lain terbaca sebagai nama "akun admin".
    Bukti: nama itu muncul 20x di seluruh HTML tapi 0x di story slice.

    Perbaikan: anchor ke actor-id posting ini dulu, baru cari nama di dekat
    id tersebut; nama yang sama dengan viewer DITOLAK.
    """
    pid = _fb_actor_id(text, story, final)
    viewer_id, viewer_name = _fb_viewer(text)
    if pid:
        # Posts milik sendiri legitimately bernama seperti viewer -> jangan tolak
        if pid and viewer_id and pid == viewer_id:
            pass                      # posting sendiri, nama viewer itu benar
        else:
            nm = _fb_name_for_id(text, pid)
            if nm:
                return nm
    # cadangan: nama di dalam node story (beberapa markup lama punya)
    story = story or ""          # _fb_story_slice boleh mengembalikan None
    for pat in (r'"actor"\s*:\s*\{[^}]{0,300}?"name"\s*:\s*"([^"]+)"',
                r'"owner"\s*:\s*\{[^}]{0,300}?"name"\s*:\s*"([^"]+)"',
                r'"profile_name"\s*:\s*"([^"]{2,60})"'):
        m = re.search(pat, story)
        if m:
            return m.group(1)
    # terakhir: dari og:title "«Nama» on Facebook"
    if re.search(r'on Facebook', _fb_og(text, "og:title")):
        nm = _fb_strip_fb_suffix(_fb_og(text, "og:title"))
        if nm and nm != viewer_name:
            return nm
    return ""


def _fb_og(html_text, prop):
    """Isi satu <meta property="..."> dengan_entities di-escape."""
    import html as _html
    m = re.search(r'<meta property="%s" content="([^"]*)"' % re.escape(prop),
                  html_text)
    return _html.unescape(m.group(1)).strip() if m else ""


def _fb_strip_fb_suffix(s):
    """'Contoh Akun on Facebook' -> 'Contoh Akun'."""
    return re.sub(r"\s*[-–|]\s*Facebook\s*$|\s+on\s+Facebook\s*$", "",
                  (s or "").strip()).strip()


def _fb_caption(text, story, author):
    """Caption genuinely Facebook — JAUH lebih baik daripada menebak.

    Urutan sumber:
      1. field message/feedback story milik posting yang dibuka
      2. og:description (kalau bukan sekadar ringkasan "N likes")
      3. og:title SETELAH sufiks "on Facebook" dibuang, tapi HANYA kalau
         sisanya TIDAK sama dengan nama author (kalau sama, itu nama akun)
    Kalau tidak ada yang cocok -> "" (jujur), bukan nama akun.
    """
    for pat in (r'"message"\s*:\s*\{[^{}]{0,80}?"text"\s*:\s*"((?:[^"\\]|\\.)*)"',
                r'"message"\s*:\s*"((?:[^"\\]|\\.){3,600})"'):
        m = re.search(pat, story or "")
        if not m:
            continue
        val = _clean_text(m.group(1)).strip()
        if len(val) >= 3:
            return val[:500]

    # og:description: Facebook menaruh dua jenis isi di sini.
    #  (a) ringkasan metrik  -> "1,234 likes · 56 comments" / "2,5 rb suka · 45 komentar"
    #  (b) cuplikan teks    -> kalimat pertama dari caption
    # Yang (a) BUKAN caption, jadi harus ditolak lebih dulu. Entities HARUS
    # di-unescape sebelum pencocokan, kalau tidak pola metrik tidak mengenali
    # "&#183;" sehingga ringkasan lalu-lolos jadi caption (bug terverifikasi).
    og = _fb_og(text, "og:description")
    if og and not _fb_is_metric_summary(og):
        if len(og) >= 3:
            return og[:500]

    title = _fb_strip_fb_suffix(_fb_og(text, "og:title"))
    if title and len(title) > 2 and title.casefold() != (author or "").casefold():
        return title[:500]
    return ""


# Kata kunci ringkasan metrik Facebook, EN & ID (dipakai untuk menyaring
# og:description supaya angka like/komentar tidak pernah jadi caption).
_FB_METRIC_WORDS = re.compile(
    r"\b(likes?|liked|reactions?|comments?|shares?|suka|disukai|komentar|"
    r"komentar\b|bagikan|share[ds]?|menyukai)\b", re.I)


def _fb_is_metric_summary(s):
    """Apakah teks ini ringkasan metrik ('N likes · M comments'), bukan caption?"""
    s = (s or "").strip()
    if not s:
        return True
    if not _FB_METRIC_WORDS.search(s):
        return False
    # Ada kata metrik. Caption asli bisa jadi memuat kata itu juga
    # ("Ucapan terima kasih atas 100 komentar"), jadi bedakan dari bentuk:
    # ringkasan = ANGKA di depan kata metrik.
    ada_angka_dulu = re.search(r"\d[\d.,]*\s*[KMB]?\s*(?:rb|ribu|jt|juta)?\s*"
                               r"\b(likes?|liked|reactions?|comments?|shares?|suka|"
                               r"disukai|komentar|bagikan|shares?)\b", s, re.I)
    if ada_angka_dulu:
        return True
    # sisa hanya angka/separator/mata uang -> pastilah ringkasan
    return not re.search(r"[A-Za-z]{3,}", re.sub(
        r"\b(likes?|liked|reactions?|comments?|shares?|suka|disukai|komentar|"
        r"komentar|bagikan|menyukai|rb|ribu)\b", "", s, flags=re.I))


def _fb_story_slice(text, url):
    """Potong HTML jadi blok milik POSTING yang dibuka saja.

    Halaman Facebook memuat banyak posting lain (rekomendasi, related).
    Verified 2026-10-11: halaman reel punya 4 story; story rekomendasi punya
    komentar 826 & share 869 sementara posting yang dibuka cuma 0/0.

    Anchor paling presisi = feedback id, yang adalah base64 dari
    "feedback:<post_id>" — jadi kita bisa mengunci ke posting yang tepat
    tanpa tebakan posisi.

    MENGEMBALIKAN (blok, id_yang_dijangkar). Id itu dipakai sebagai post_key
    supaya identitas posting yang tercatat PUNYA yang metriknya dibaca — bukan
    sekadar "post_id pertama di halaman", yang bisa belonging posting lain.

    PENTING (2026-10-12): kalau TIDAK ada anchor yang cocok, fungsi ini
    mengembalikan (None, None) — BUKAN seluruh halaman. Seluruh halaman memuat
    posting orang lain, jadi membaca metrik dari sana menghasilkan angka yang
    milik orang (terukur: share/r/1CxrPBSRt9 punya reaction ['0','3501'],
    angka 3501 milik posting rekomendasi). Tidak dapat metrik (None) jauh
    lebih baik daripada metrik yang salah.
    """
    import base64
    METRIC_MARKERS = ('reaction_count', '"comments":{"total_count"',
                      'share_count', 'total_comment_count',
                      'unified_reactors', 'share_count_reduced')
    # Semua kandidat id dicoba, bukan hanya satu (lihat _fb_post_ids).
    for pid in _fb_post_ids(text, url):
        # Kumpulkan SEMUA kemunculan token posting ini, lalu ambil yang
        # window-nya benar-benar punya field metrik (verifikasi 2026-10-11:
        # token yang sama muncul beberapa kali, sebagian tanpa metrik).
        hits = []
        for rx in (FB_FEEDBACK_ID, FB_FEEDBACK_ID2):
            for m in rx.finditer(text):
                tok = m.group(1)
                try:
                    dec = base64.b64decode(
                        tok + "=" * (-len(tok) % 4)).decode()
                except Exception:  # noqa: BLE001
                    continue
                if dec == f"feedback:{pid}":
                    hits.append(m)
        best, best_score = None, 0
        for m in hits:
            lo = max(0, m.start() - 3000)
            # jendela harus cukup lebar: pada post biasa, reaction_count
            # berada ~7.500 char SESUDAH token (terukur), bukan bersebelahan.
            win = text[lo:m.end() + 12000]
            # skor = berapa banyak JENIS metrik yang ada (bukan cuma satu)
            score = sum(1 for k in METRIC_MARKERS if k in win)
            if score > best_score:
                best, best_score = win, score
        if best:
            return best, pid
    # Cadangan: blok creation_story yang punya field metrik. HANYA aman bila
    # halaman memang cuma punya SATU story; kalau ada beberapa, kita tidak
    # bisa tahu yang mana yang benar -> jangan menebak.
    marks = [m.start() for m in FB_STORY_MARK.finditer(text)]
    if len(marks) == 1:
        return text[marks[0]:marks[0] + 12000], None
    if len(marks) > 1:
        markers = ('unified_reactors', 'total_comment_count',
                   'share_count_reduced', 'reaction_count',
                   '"comments":{"total_count"')
        bermetrik = [i for i in range(len(marks) - 1)
                     if any(k in text[marks[i]:marks[i + 1]] for k in markers)]
        if len(bermetrik) == 1:      # hanya satu yang punya metrik -> aman
            i = bermetrik[0]
            return text[marks[i]:marks[i + 1]], None
    return None, None               # <-- jujur: tidak bisa dipastikan


def _fb_pick(patterns, text, compact=True):
    """Cari nilai pertama yang cocok di antara beberapa pola."""
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        raw = m.group(1)
        if not raw:
            continue
        try:
            return _parse_compact(raw) if compact else int(raw)
        except (TypeError, ValueError):
            continue
    return None


def _run_with_deadline(fn, seconds):
    """Jalankan fn di thread daemon, potong setelah `seconds`.

    PENTING: socket timeout TIDAK berlaku untuk resolusi DNS. Terverifikasi
    2026-10-11: satu request ke www.facebook.com dengan timeout 12s tetap
    memakan 99 detik karena getaddrinfo() membeku. Karena itu setiap probe
    dibungkus batas waktu keras di level thread.

    CATATAN BATASANNYA: Python tidak bisa membunuh thread yang sedang berjalan.
    Jadi setelah deadline, thread itu BELUM MATI — hanya tidak lagi ditunggu
    (terukur: deadline 1s atas fungsi 30s -> thread masih hidup). Thread yang
    menggantung tetap memegang socket dan bisa menumpuk untuk batch besar.

    Karena itu pemanggil WAJIB membatasi jumlah probe yang dibuat, bukan
    hanya lamanya. Jangan menambah panggilan tanpa batas waktu keras.
    """
    box = {}

    def run():
        try:
            box["v"] = fn()
        except Exception as e:  # noqa: BLE001
            box["v"] = e
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(seconds)
    return box.get("v")      # None = lewat batas waktu


_DNS_CACHE = {}
_DNS_LOCK = threading.Lock()


def _resolvable(host, seconds=4):
    """Cek DNS dengan batas waktu keras (getaddrinfo bisa membeku).

    Hasil di-cache supaya host yang sama tidak dicek berulang. Tanpa cache,
    satu link Facebook memanggil _resolvable 2x5 host = 10 lookup, dan tiap
    lookup untuk host yang diblokir jaringan bisa menyedot 4 detik penuh.

    TTL singkat (60 detik) supaya DNS yang pulih tidak tertahan lama.
    """
    now = time.time()
    with _DNS_LOCK:
        hit = _DNS_CACHE.get(host)
        if hit and now - hit[0] < 60:
            return hit[1]
    # getaddrinfo (bukan gethostbyname) supaya jalur IPv6 ikut tertutup —
    # di jaringan IPv6-only gethostbyname gagal padahal host hidup.
    val = _run_with_deadline(
        lambda: (socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM) or True),
        seconds)
    ok = val is not None and not isinstance(val, Exception)
    with _DNS_LOCK:
        _DNS_CACHE[host] = (now, ok)
    return ok


FB_JUNK = ("zero/policy", "checkpoint", "/login", "policy/optin",
           "facebook.com/error", "www.keepconnection")


def _fb_is_junk(html, final):
    """Halaman ini halaman Policies/consent/error, BUKAN halaman posting.

    Terverifikasi 2026-10-11: share/v/18dRKSxFvW/ dialihkan free.facebook.com
    ke /zero/policy/optin/ (9,8 KB) sementara www bisa 3,8 MB. Kalau halaman
    kecil ini diterima, parser gagal dengan pesan menyesatkan.
    """
    low = (final or "").lower()
    if any(j in low for j in FB_JUNK):
        return True
    if len(html) > 40000:
        return False
    head = html[:6000]
    return bool(re.search(r'"?error"?\s*[:=]', head)
                or "policy" in low or "consent" in low)


def _fb_probe_host(candidate, cookies, timeout):
    """Coba satu host Facebook. Return (html, final, netloc) atau None."""
    import session as _sess
    host = urllib.parse.urlsplit(candidate).netloc
    if not _resolvable(host, 3):
        return None
    try:
        s, html, final = _sess.fetch(candidate, cookies, timeout=timeout)
    except Exception:  # noqa: BLE001 - DNS/network gagal, coba host lain
        return None
    if s != 200 or not html:
        return None
    if _fb_is_junk(html, final):
        return None
    return html, final, host


def _fb_fetch_any(url, cookies, timeout=25, rounds=1):
    """Ambil HTML Facebook dari host mana pun yang hidup — dengan PARALEL.

    Semua host ditembak BERSAMAAN di thread daemon dengan batas waktu keras.
    Versi lama mencoba host BERURUTAN -> satu host dengan DNS beku menahan
    99 detik sendirian (terukur).

    Timeout default 25 detik (bukan 12) karena halaman FB logout itu BESAR
    (terukur 1,7-3,8 MB); dengan 12 detik jalur cepat selalu gagal dan kita
    jatuh ke 5 host sekaligus — jauh lebih lambat.

    Host yang balas halaman besar (>40KB = SSR asli) langsung dipakai.
    Halaman policy/consent/error (_fb_is_junk) DILEWATI supaya tidak
    menggantikan halaman posting yang sehat.
    """
    variants = _fb_host_variants(url)
    hosts = [urllib.parse.urlsplit(v).netloc for v in variants]
    primary = hosts[0]

    # Jalur cepat: host utama sehat -> 1 request saja. Hanya kalau gagal
    # (DNS/memblokir/timeout) kita menyalakan semua host secara paralel.
    if _resolvable(primary, 3):
        res = _run_with_deadline(
            lambda: _fb_probe_host(variants[0], cookies, timeout), timeout + 6)
        if isinstance(res, tuple):
            html, final, host = res
            if len(html) > 40000:          # SSR asli -> selesai, 1 request
                return html, final, host

    # Gerbang DNS cepat: kalau tidak satu pun host yang bisa di-resolve,
    # gagal SEKALI dengan pesan jelas — jangan tunggu semua timeout.
    import concurrent.futures as _cf
    with _cf.ThreadPoolExecutor(max_workers=len(hosts)) as ex:
        dns = list(ex.map(lambda h: _resolvable(h, 4), hosts))
    live = [v for v, ok in zip(variants, dns) if ok]
    if not live:
        raise ScrapeFailed(
            "tidak ada satu pun host Facebook yang bisa di-resolve ("
            + ", ".join(hosts) + ") — masalah DNS/jaringan, bukan cookie. "
            "Cek: python3 cek_facebook.py", retryable=True)
    variants = live

    def probe_all():
        import concurrent.futures as _cf
        ex = _cf.ThreadPoolExecutor(max_workers=len(variants))
        out = []
        futs = {ex.submit(_fb_probe_host, v, cookies, timeout): i
                for i, v in enumerate(variants)}
        try:
            for f in _cf.as_completed(futs, timeout=timeout + 5):
                try:
                    out.append((futs[f], f.result()))
                except Exception:  # noqa: BLE001
                    pass
                # Halaman SSR asli ketemu -> BERHENTI, jangan tunggu sisa.
                # out[-1][1] adalah tuple (html, final, host); panjang HTML
                # ada di [0]. Versi lama menulis len(out[-1][1]) yang selalu
                # bernilai 3, sehingga early-break TIDAK PERNAH aktif dan kita
                # menunggu deadline penuh walau jawabannya sudah masuk.
                # Terukur 2026-10-11: 30,03s -> 2,59s per link Facebook.
                if any(r and len(r[0]) > 40000 for _i, r in out):
                    break
        except Exception:  # noqa: BLE001 - deadline as_completed
            pass
        finally:
            ex.shutdown(wait=False)   # jangan tunggu host yang beku
        return out

    for rnd in range(rounds):
        results = _run_with_deadline(probe_all, timeout + 6) or []
        small = None
        for _i, res in sorted(results):
            if not res:
                continue
            if len(res[0]) > 40000:      # SSR asli -> menang
                return res
            small = small or res
        # Hanya hasil kecil yang tersisa: pakai, TAPI hanya kalau halaman itu
        # kelihatan punya data posting. Selain itu, tunggu ronde berikutnya.
        if small and not _fb_is_junk(small[0], small[1]):
            return small
        if rnd + 1 < rounds:
            time.sleep(1.0)
    raise ScrapeFailed(
        "tidak bisa membaca halaman Facebook dari host mana pun ("
        + ", ".join(hosts) + ") — semua host mengembalikan halaman "
        "policy/consent/error, bukan halaman posting. "
        "Cek: python3 cek_facebook.py", retryable=True)


def scrape_facebook_post(url, cookies):
    """Scrape satu postingan Facebook — BUTUH sesi login.

   Beberapa markup (HTML desktop / mbasic / JSON terstruktur) dicoba satu
    per satu; metrik yang tidak ditemukan = None (jujur), bukan 0.
    """
    html, final, host = _fb_fetch_any(url, cookies)
    if _fb_login_wall(html, final):
        raise ScrapeFailed(
            "sesi Facebook tidak valid — Facebook mengarahkan ke login "
            "(cookie kedaluwarsa). Ambil ulang cookie di Pengaturan.",
            retryable=False)

    text = html.replace('\\"', '"')
    # Metrik diambil dari blok story milik posting utama (lihat _fb_story_slice).
    # story=None berarti blok itu TIDAK bisa dipastikan -> metrik dibiarkan None
    # (tidak dikira dari seluruh halaman, karena itu akan mengambil angka
    # posting orang lain — bug "angka besar" yang dikeluhkan user).
    story, story_pid = _fb_story_slice(text, final or url)
    if story:
        like = _fb_pick(FB_PATTERNS["like"], story)
        komen = _fb_pick(FB_PATTERNS["komen"], story)
        share = _fb_pick(FB_PATTERNS["share"], story)
        views = _fb_pick(FB_PATTERNS["views"], story)
    else:
        like = komen = share = views = None

    # og:description sebagai cadangan (UI lama: "1,234 likes · 56 comments")
    if None in (like, komen, share):
        import html as _html
        m = re.search(r'<meta property="og:description" content="([^"]*)"', text)
        if m:
            og = _html.unescape(m.group(1))
            if like is None:
                like = _fb_pick([r"([\d.,]+[KMB]?)\s+[Ll]ikes?",
                                 r"([\d.,]+[KMB]?)\s+[Rr]eactions?"], og)
            if komen is None:
                komen = _fb_pick([r"([\d.,]+[KMB]?)\s+[Cc]omments?"], og)
            if share is None:
                share = _fb_pick([r"([\d.,]+[KMB]?)\s+[Ss]hares?"], og)

    epoch = 0
    for pat in FB_DATE_PATTERNS:
        m = re.search(pat, text)
        if m:
            try:
                epoch = int(m.group(1))
            except ValueError:
                epoch = 0
            if epoch:
                break
    # post_key SELALU string di semua platform. Versi lama mengembalikan
    # hasil _fb_pick(compact=False) yang berupa INT untuk Facebook, lalu
    # pemanggil melakukan .strip() -> AttributeError: 'int' object has no
    # attribute 'strip' yang mematikan seluruh thread job (2026-10-12).
    # post_key diutamakan dari id yang BENAR-BENAR di-anchor (identitas posting yang
    # metriknya kita baca). Kalau tidak ter-anchor, pakai id dari URL final.
    _ids = _fb_post_ids(text, final or url)
    post_key = (str(story_pid).strip() if story_pid else
                (_ids[0] if _ids else str(
                    _fb_pick(FB_ID_PATTERNS, text, compact=False) or "").strip()))
    author = _fb_author(text, story, final)
    # author kosong bukan akhir: coba og:title halaman ini (fallback)
    if not author:
        author = _fb_strip_fb_suffix(_fb_og(text, "og:title"))[:120]
    # Caption: og:title SELALU berisi pola "<teks> on Facebook" untuk tautan
    # profil/photo — jadi nilainya bisa berupa NAMA AKUN, bukan caption
    # (-> "Contoh Akun on Facebook" masuk ke kolom caption, terverifikasi).
    # Buang sufiks "on Facebook" dan, kalau sisa akhirnya identik dengan
    # author, itu bukti og:title memang nama akun -> cari sumber lain.
    caption = _fb_caption(text, story, author)

    if like is None and komen is None and share is None and views is None:
        # Tidak boleh gagal total kalau halaman-nya jelas valid (ada penulis
        # atau tanggal): lebih baik posting tersimpan dengan metrik "—" daripada
        # hilang total. "—" berarti tidak terverifikasi, bukan nol.
        # Gagal total hanya kalau halaman memang tidak memberi identitas.
        if not author and not epoch:
            raise ScrapeFailed(
                "Facebook tidak mengirim metrik untuk postingan ini lewat host "
                f"{host}. Kemungkinan konten privat, sudah dihapus, atau markup "
                "Facebook berubah lagi.", retryable=False)

    posted = wib.to_wib_str(epoch)
    return {"platform": "facebook", "url": final or url, "post_key": post_key,
            "author": author, "posted_at": posted, "caption": caption,
            "views": views, "komen": komen, "share": share,
            "like": like, "repost": None,
            "date_precision": date_precision("facebook", posted),
            # Id profil/null (12345678900000). Facebook tidak selalu mengirim
            # NAMA di halaman (terukur: /share/v/ sama sekali tidak memuat
            # nama), tapi id profil selalu ada di URL story.php?id=...
            # Ini dipakai sebagai cadangan untuk dipasangkan ke akun.
            "actor_id": str(_fb_actor_id(text, story, final) or "")}


def _parse_compact(s):
    """'1,234' / '12.5K' / '3M' -> int."""
    s = (s or "").strip().upper().replace(",", "")
    m = re.match(r"([\d.]+)([KMB]?)", s)
    if not m:
        return None
    val = float(m.group(1))
    return int(val * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2)])
