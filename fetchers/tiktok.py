#!/usr/bin/env python3
"""Fetcher TikTok TANPA login — ekstraksi SSR dari halaman video.

Terbukti jalan di sandbox 2026-10-10 thd @contoh_akun (read-only, tanpa signing).
Satu GET per video -> blob __UNIVERSAL_DATA_FOR_REHYDRATION__ ->
itemStruct: id, desc, createTime, stats{playCount, diggCount, commentCount,
shareCount, collectCount}.

Keterbatasan (jujur, terverifikasi):
- Daftar video per akun TIDAK bisa dari IP server (butuh X-Gnarly signing,
  rusak di semua lib publik sejak Jul 2026). -> URL video disuplai dari
  posts.csv (link setoran tim).
- Repost count TIDAK diekspos publik TikTok.
"""
import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wibtime as wib  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# UA mobile unlock-blok yang HANYA ada di tampilan web mobile:
# posting FOTO (/photo/) tidak punya SSR webapp.video-detail di desktop,
# tapi UA mobile serving <script id="api-data"> berisi itemStruct LENGKAP
# (stats{digg,comment,share,play,collect}, imagePost, createTime, author).
# Verified 2026-10-11: photo + UA mobile -> stats lengkap; photo + UA desktop -> kosong.
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
             "Mobile/15E148 Safari/604.1")

RE_API_DATA = re.compile(
    r'<script id="api-data"[^>]*>(.*?)</script>', re.S)

RE_BLOB = re.compile(
    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"'
    r' type="application/json">(.*?)</script>', re.S)


class WAFChallenge(Exception):
    """Captcha anti-bot TikTok (Slardar WAF) — transient, layak retry."""


def fetch(url, timeout=45, ua=None):
    req = urllib.request.Request(
        url, headers={"User-Agent": ua or UA,
                      "Accept": "text/html,application/xhtml+xml",
                      "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def parse_video(html):
    m = RE_BLOB.search(html)
    if not m:
        # Bedakan "halaman 404" dari "login wall/captcha" — jangan samakan
        # semuanya jadi "blob tidak ditemukan".
        low = html.lower()
        if ("/404" in low or "page not found" in low
                or "couldn't find this account" in low):
            raise ValueError("video tidak ditemukan (TikTok balas 404) — "
                             "link mungkin salah ketik atau video sudah dihapus")
        # SlardarWAF = challenge anti-bot TikTok (rate limit), BUKAN login wall.
        if "slardarwaf" in low or "wafchallengeid" in low or "please wait..." in low:
            raise WAFChallenge("TikTok memunculkan captcha anti-bot (rate "
                               "limit) — tunggu beberapa menit, kurangi "
                               "kecepatan scrape")
        if "captcha" in low and "itemstruct" not in low:
            raise WAFChallenge("TikTok meminta captcha — IP kena rate limit")
        # Halaman login beneran: small page, tak ada SSR sama sekali
        if "login" in low and len(html) < 20000:
            raise ValueError("TikTok meminta login — tidak bisa dibaca tanpa "
                             "sesi (coba pakai link /video/ yang panjang)")
        raise ValueError("blob SSR TikTok tidak ditemukan — struktur halaman "
                         "berubah atau IP di-flag")
    scope = json.loads(m.group(1)).get("__DEFAULT_SCOPE__") or {}
    vd = scope.get("webapp.video-detail")
    if vd is None:
        # Posting FOTO (/photo/) tidak punya webapp.video-detail di desktop —
        # biarkan pemanggil mencoba jalur mobile (api-data).
        raise ValueError("tidak ada webapp.video-detail di blob SSR desktop")
    # TikTok balas 200 dengan statusCode di dalam JSON untuk item tak valid
    if "statusCode" in vd and "itemInfo" not in vd:
        raise ValueError(f"video tidak valid ({vd.get('statusMsg', '?')}) — "
                         "link bukan link video TikTok yang benar")
    it = vd["itemInfo"]["itemStruct"]
    return _struct_to_metrics(it, "video")


def _struct_to_metrics(it, default_tipe="video"):
    """itemStruct TikTok -> dict metrik seragam."""
    st = it.get("stats") or {}
    epoch = int(it.get("createTime") or 0)
    is_photo = bool(it.get("imagePost"))
    return {
        "post_id": it.get("id"),
        "author": (it.get("author") or {}).get("uniqueId"),
        "caption": (it.get("desc") or "")[:200],
        "epoch": epoch,
        "posted_at_utc": wib.to_wib_str(epoch),
        "views": st.get("playCount"),
        "like": st.get("diggCount"),
        "komen": st.get("commentCount"),
        "share": st.get("shareCount"),
        "repost": None,  # tidak diekspos publik
        "saves": st.get("collectCount"),
        "is_reply": False,
        "tipe": "foto" if is_photo else default_tipe,
    }


def parse_api_data(html):
    """Payload <script id="api-data"> — HANYA ada di tampilan web MOBILE.

    Inilah sumber data posting FOTO: desktop tidak mengirim
    webapp.video-detail untuk /photo/, tapi mobile mengirim videoDetail
    lengkap (verified 2026-10-11). Return None kalau tidak ada.
    """
    m = RE_API_DATA.search(html)
    if not m:
        return None
    try:
        blob = json.loads(m.group(1))
    except ValueError:
        return None
    vd = blob.get("videoDetail") or {}
    if "itemInfo" not in vd:
        return None
    it = vd["itemInfo"].get("itemStruct") or {}
    return _struct_to_metrics(it) if it.get("id") else None


def clean_url(url):
    """Buang query stringafter resolve.

    PENTING: TikTok hanya mengirim <script id="api-data"> pada URL BERSIH.
    Redirect vt.tiktok.com menambah '?_r=1&_t=...' yang membuat halaman
    mobile kehilangan api-data (verified 2026-10-11).
    """
    return urllib.parse.urlsplit(url)._replace(query="", fragment="").geturl()


def fetch_video(url):
    """Ambil metrik satu video/foto TikTok dengan fallback berlapis.

    1. Desktop UA + blob __UNIVERSAL_DATA (jalur tercepat untuk /video/)
    2. Mobile UA + <script id="api-data"> (WAJIB untuk posting /photo/)
    Raises ValueError / WAFChallenge.
    """
    url = clean_url(url)
    try:
        return parse_video(fetch(url))
    except WAFChallenge:
        raise                      # rate limit: jangan pindah jalur, retry
    except ValueError as e:
        msg = str(e)
        # 404 / tidak valid = link memang salah -> tidak ada jalur lain
        if "404" in msg or "tidak valid" in msg:
            raise
    # Jalur 2: tampilan mobile
    d = parse_api_data(fetch(url, ua=UA_MOBILE))
    if d:
        return d
    raise ValueError("metrik TikTok tidak bisa dibaca untuk link ini")


def profile_info(handle):
    """Info agregat profil (followers, video count, total likes). Opsional."""
    scope = json.loads(RE_BLOB.search(fetch(f"https://www.tiktok.com/@{handle}"))
                         .group(1))["__DEFAULT_SCOPE__"]
    ui = scope["webapp.user-detail"]["userInfo"]
    u, st = ui["user"], ui["stats"]
    return {"username": u.get("uniqueId"), "nickname": u.get("nickname"),
            "followers": st.get("followerCount"), "following": st.get("followingCount"),
            "total_likes": st.get("heartCount"), "video_count": st.get("videoCount")}
