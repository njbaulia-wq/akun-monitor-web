#!/usr/bin/env python3
"""Manajemen sesi login (cookie) PantauAkun.

Satu sesi login per platform — akun admin milik user — dipakai untuk membaca
akun-akun tim yang lain. Tool TIDAK PERNAH meminta atau menyimpan password;
hanya cookie yang user export sendiri dari browsernya.

Format cookie yang didukung:
  1. Header Cookie mentah:   sessionid=abc123; csrftoken=xyz
  2. File cookies.txt Netscape (ekstensi "Get cookies.txt" / "cookies.txt")

Cookie disimpan di SQLite settings (lokal saja, tidak dikirim ke mana pun
selain platformnya sendiri). Tidak pernah ditulis ke log.
"""

import json
import re
import http.client
import threading
import urllib.request
import urllib.error
import urllib.parse


class _KeepAlivePool:
    """Klien HTTP dengan koneksi yang DIPAKAI ULANG (keep-alive).

    urllib membuka koneksi TCP+TLS baru untuk SETIAP request. Terukur
    2026-10-11: ke www.threads.com, keep-alive memangkas 1122 ms -> 819 ms
    per request (-27%). Untuk 668 link x ~2 request itu ~7 menit.

    Satu koneksi per (host, thread). Kalau server menutup koneksi, dibuat
    ulang. Sengaja memakai Accept-Encoding: identity supaya tidak perlu
    golf dekompresi.
    """

    def __init__(self):
        self._local = threading.local()

    def get(self, host):
        conns = getattr(self._local, "conns", None)
        if conns is None:
            conns = self._local.conns = {}
        return conns.get(host)

    def put(self, host, conn):
        conns = getattr(self._local, "conns", None)
        if conns is None:
            conns = self._local.conns = {}
        old = conns.get(host)
        conns[host] = conn
        if old is not None:
            try:
                old.close()
            except Exception:
                pass

    def drop(self, host):
        conns = getattr(self._local, "conns", None)
        if conns and conns.pop(host, None) is not None:
            try:
                conns[host].close()
            except Exception:
                pass

    def request(self, url, method="GET", headers=None, timeout=30,
                data=None, max_redirects=5):
        """HTTP(S) dengan reuse. Return (status, body_bytes, final_url)."""
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or ""
        port = parts.port
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        for _ in range(max_redirects):
            conn = self.get(host)
            if conn is None:
                cls = (http.client.HTTPSConnection if parts.scheme == "https"
                       else http.client.HTTPConnection)
                conn = cls(host, port, timeout=timeout)
            try:
                h = dict(headers or {})
                h.setdefault("Accept-Encoding", "identity")
                h.setdefault("Connection", "keep-alive")
                conn.request(method, path, body=data, headers=h)
                resp = conn.getresponse()
                body = resp.read()
                status = resp.status
                loc = resp.getheader("Location")
                if resp.will_close:
                    self.drop(host)
                else:
                    self.put(host, conn)
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                self.drop(host)
                raise
            if loc and status in (301, 302, 303, 307, 308):
                nxt = urllib.parse.urljoin(url, loc)
                if urllib.parse.urlsplit(nxt).hostname != host:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    self.drop(host)
                url = nxt
                parts = urllib.parse.urlsplit(url)
                host = parts.hostname or ""
                port = parts.port
                path = parts.path or "/"
                if parts.query:
                    path += "?" + parts.query
                method, data = "GET", None
                continue
            return status, body, url
        return status, body, url


POOL = _KeepAlivePool()

PLATFORMS = ("instagram", "threads", "facebook")
# Catatan: TikTok SENGAJA tidak ada di sini. Riset 2026-10-11 membuktikan:
# daftar video profil TikTok tidak ada di SSR (struktural), API unsigned
# mengembalikan body kosong, endpoint lama /node/share 403, dan API signed
# butuh X-Bogus (dibangkitkan JS browser, rapuh). Sesi cookie via Python
# tidak membuka kapabilitas listing TikTok. Jalur resmi: TikTok Display API.

UA_DESKTOP = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Facebook (dan situs anti-bot lain) membalas HTTP 400 "Error" kalau
# header-nya terlihat seperti scraper. Verified 2026-10-11:
#   minimal (UA saja)       -> HTTP 400, 1.5 KB (tanpa data)
#   header browser lengkap  -> HTTP 200, 470 KB (HTML asli + metrik)
# Accept-Encoding: identity penting — memaksa server tidak mengompres.
BROWSER_HEADERS = {
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


# ---------- parsing ----------

def parse_cookie_header(text):
    """'a=1; b=2' -> {'a': '1', 'b': '2'}."""
    out = {}
    for part in (text or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        k, v = k.strip(), v.strip().strip('"')
        if k and v:
            out[k] = v
    return out


def parse_netscape(text):
    """.cookies.txt Netscape -> {name: value}.

    Baris '#HttpOnly...' adalah cookie valid (flag HttpOnly), bukan komentar;
    hanya baris komentar murni ('# ...') yang diabaikan.
    """
    out = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#HttpOnly"):
            line = line[len("#HttpOnly"):].strip()
        elif line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 7:
            name, value = cols[5].strip(), cols[6].strip()
            if name:
                out[name] = value
    return out


def parse_any(text):
    """Deteksi format otomatis -> dict cookie. Raise ValueError bila kosong."""
    text = (text or "").strip()
    if not text:
        raise ValueError("cookie kosong")
    d = parse_netscape(text) if "\t" in text else parse_cookie_header(text)
    # fallback silang: baris tab tapi gagal -> coba header
    if not d and "\t" in text:
        d = parse_cookie_header(text.replace("\t", "; "))
    if not d:
        raise ValueError("tidak ada cookie yang terbaca — cek formatnya")
    return d


def cookie_header(cookies):
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


# ---------- request dengan sesi ----------

def fetch(url, cookies, headers=None, timeout=30, data=None, method=None):
    """GET/POST dengan cookie sesi. Kembalikan (status, body_teks, final_url).

    Memakai koneksi keep-alive (lihat _KeepAlivePool).
    """
    h = {"User-Agent": UA_DESKTOP}
    h.update(BROWSER_HEADERS)
    h["Cookie"] = cookie_header(cookies)
    if headers:
        h.update(headers)
    try:
        status, body, final = POOL.request(
            url, method=method or "GET", headers=h, timeout=timeout,
            data=data)
    except urllib.error.HTTPError:  # ENGINE COMPAT — kalau ada, tetap aman
        return 0, "", url
    except Exception:  # noqa: BLE001 - error jaringan
        return 0, "", url
    return status, body.decode("utf-8", errors="replace"), final


# ---------- penyimpanan (via settings DB) ----------

def get_stored(platform):
    """Baca cookie sesi dari settings DB. Kembalikan dict (bisa kosong)."""
    import db  # deferred: hindari circular import
    raw = db.get_setting("session_" + platform, "")
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_stored(platform, cookies):
    import db
    db.set_setting("session_" + platform, json.dumps(cookies))


def clear_stored(platform):
    import db
    db.set_setting("session_" + platform, "")


# ---------- sesi PER AKUN (untuk "cek follow" dengan akun sumber bebas) ----------

def get_account(account_id):
    """Cookie sesi milik satu akun. Kembalikan dict (bisa kosong)."""
    import db
    raw = db.get_account_session(account_id)
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_account(account_id, platform, cookies):
    import db
    db.save_account_session(account_id, platform, json.dumps(cookies))


def clear_account(account_id):
    import db
    db.clear_account_session(account_id)


def accounts_with_session(platform=None):
    """{account_id: saved_at} — untuk badge di UI. Tanpa isi cookie."""
    import db
    return {r["account_id"]: r["saved_at"]
            for r in db.list_account_sessions(platform)}


def test_account(account_id, platform, username):
    """Uji cookie akun SEPKALIGUS pastikan ia memang milik akun itu.

    Salah tempel cookie itu mudah terjadi, dan akibatnya hasil cek follow
    jadi milik orang lain. Karena itu identitasnya diverifikasi: username
    akun yang dilaporkan cookie harus SAMA dengan akun yang dimaksud.
    """
    if platform != "instagram":
        return {"ok": False, "username": None,
                "detail": "sesi per akun saat ini hanya untuk Instagram"}
    cookies = get_account(account_id)
    if not cookies:
        return {"ok": False, "username": None,
                "detail": "belum ada cookie untuk akun ini"}
    import scrape  # deferred: hindari circular import
    me = scrape.fetch_instagram_self(cookies)
    if not me or not me.get("username"):
        # Cookie tidak terbaca / kedaluwarsa. test_session memberi pesan
        # kapabilitas yang lebih spesifik (HTTP berapa, dll).
        r = test_session(platform, cookies)
        return {"ok": False, "username": None, "detail": r.get("detail") or
                "cookie tidak bisa dipastikan"}
    if me["username"].lower() != (username or "").lstrip("@").lower():
        return {"ok": False, "username": me["username"],
                "detail": f"cookie ini milik @{me['username']}, "
                          f"BUKAN @{username} — jangan dipakai"}
    return {"ok": True, "username": me["username"],
            "detail": f"cookie cocok dengan @{me['username']}"}


# ---------- tes sesi ----------

def _looks_logged_out_threads(html):
    # Halaman logged-out memuat '"viewer":null' (terverifikasi);
    # sesi login yang valid memuat '"viewer":{"user":{...}}'.
    return '"viewer":null' in html


def test_session(platform, cookies):
    """Uji apakah cookie masih valid. Kembalikan dict {ok, username, detail}.

    Tes bersifat kapabilitas: memakai endpoint/fitur yang BENAR-BENAR
    dibutuhkan tool, bukan sekadar "bisa buka homepage".
    Tidak melempar untuk kegagalan jaringan/HTTP — dilaporkan di 'detail'.
    """
    if not cookies:
        return {"ok": False, "username": None,
                "detail": "belum ada cookie tersimpan"}
    try:
        if platform == "instagram":
            # Tes kapabilitas langsung: listing profil akun publik.
            # Tanpa sesi -> 429/401; sesi valid -> 200 + data user.
            s, b, _ = fetch(
                "https://i.instagram.com/api/v1/users/web_profile_info/?username=instagram",
                cookies, headers={"X-IG-App-ID": "936619743392459",
                                  "Accept": "application/json"}, timeout=15)
            if s == 200:
                try:
                    u = json.loads(b)["data"]["user"]["username"]
                    return {"ok": True, "username": None,
                            "detail": f"sesi valid — listing terbaca (tes: @{u})"}
                except Exception:
                    return {"ok": False, "username": None,
                            "detail": "respons tak terduga dari Instagram"}
            return {"ok": False, "username": None,
                    "detail": f"Instagram menolak sesi (HTTP {s}) — cookie mungkin kedaluwarsa"}

        if platform == "threads":
            # Tanpa sesi -> '"viewer":null' (terverifikasi).
            # Sesi valid -> '"viewer":{"user":{...}}'.
            s, b, _ = fetch("https://www.threads.com/", cookies, timeout=15)
            if s != 200:
                return {"ok": False, "username": None,
                        "detail": f"HTTP {s} — cookie mungkin kedaluwarsa"}
            if _looks_logged_out_threads(b):
                return {"ok": False, "username": None,
                        "detail": "masih terlihat sebagai pengunjung (belum login)"}
            m = re.search(r'"viewer":\{"user":\{"username":"([^"]+)"', b)
            u = m.group(1) if m else None
            return {"ok": True, "username": u,
                    "detail": "sesi valid" + (f" (@{u})" if u else "")}

        if platform == "facebook":
            s, b, final = fetch("https://www.facebook.com/", cookies, timeout=15)
            if "login" in final:
                return {"ok": False, "username": None,
                        "detail": "diarahkan ke halaman login — cookie kedaluwarsa"}
            if s != 200:
                return {"ok": False, "username": None,
                        "detail": f"HTTP {s} — cookie mungkin kedaluwarsa"}
            if re.search(r"<title>Log in", b, re.I):
                return {"ok": False, "username": None,
                        "detail": "masih terlihat sebagai pengunjung (belum login)"}
            return {"ok": True, "username": None,
                    "detail": "sesi valid (baca postingan seharusnya bisa)"}

        return {"ok": False, "username": None, "detail": "platform tak dikenal"}
    except Exception as e:  # jaringan dkk — bukan vonis cookie
        return {"ok": False, "username": None, "detail": f"gagal koneksi: {e}"[:150]}
