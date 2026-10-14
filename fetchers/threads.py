#!/usr/bin/env python3
"""Fetcher Threads TANPA login — SSR threads.com dengan UA crawler.

Terbukti jalan di sandbox 2026-10-10 thd @contoh.akun (read-only).
Satu GET per akun -> <script type="application/json" data-sjs> ->
thread_items[].post: pk, code, taken_at, caption.text, like_count,
text_post_app_info.{direct_reply_count, repost_count, quote_count}.

Kunci: User-Agent crawler (Googlebot). UA browser biasa justru kena login wall.

Keterbatasan (jujur, terverifikasi):
- Views per post TIDAK diekspos publik (view_count=None).
- Share count (reshare_count) TIDAK diekspos; padanannya: repost_count + quote_count.
- Jendela SSR: ~15 post terbaru per request (cukup bila akun <= ~15 post/minggu).
"""
import datetime
import html
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wibtime as wib  # noqa: E402

CRAWLER_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
SJS_RE = re.compile(r'<script type="application/json"[^>]*>(.*?)</script>', re.S)


def fetch_profile(username, timeout=40):
    url = f"https://www.threads.com/@{username}"
    req = urllib.request.Request(url, headers={
        "User-Agent": CRAWLER_UA,
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", errors="replace")


def _walk(o, depth=0):
    if depth > 30:
        return
    if isinstance(o, dict):
        ti = o.get("thread_items")
        if isinstance(ti, list) and ti and isinstance(ti[0], dict) and "post" in ti[0]:
            yield ti
        for v in o.values():
            yield from _walk(v, depth + 1)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v, depth + 1)


def _find_user(o, depth=0):
    if depth > 30:
        return None
    if isinstance(o, dict):
        if "username" in o and "follower_count" in o and "biography" in o:
            return o
        for v in o.values():
            r = _find_user(v, depth + 1)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_user(v, depth + 1)
            if r:
                return r
    return None


def parse(src, username):
    posts, seen = [], set()
    user = None
    for m in SJS_RE.finditer(src):
        try:
            d = json.loads(html.unescape(m.group(1)))
        except Exception:
            continue
        if user is None and "follower_count" in m.group(1):
            user = _find_user(d)
        for ti in _walk(d):
            for item in ti:
                p = item.get("post") or {}
                pk = str(p.get("pk", ""))
                if not pk or pk in seen:
                    continue
                seen.add(pk)
                tpi = p.get("text_post_app_info") or {}
                ts = p.get("taken_at")
                code = p.get("code")
                posts.append({
                    "post_id": pk,
                    "permalink": (f"https://www.threads.com/@{username}/post/{code}"
                                  if code else None),
                    "caption": ((p.get("caption") or {}).get("text") or "")[:200],
                    "epoch": int(ts) if ts else 0,
                    "posted_at_utc": wib.to_wib_str(ts),
                    # views: tanpa login tidak diekspos; DENGAN sesi login,
                    # Threads menyertakan salah satu field ini
                    "views": next((p.get(k) for k in
                                   ("view_count", "video_view_count", "play_count")
                                   if isinstance(p.get(k), int)), None),
                    "like": p.get("like_count"),
                    "komen": (tpi.get("direct_reply_count")),
                    "share": None,  # reshare_count tidak diekspos
                    "repost": (tpi.get("repost_count") or 0) + (tpi.get("quote_count") or 0),
                    "quote": tpi.get("quote_count"),
                    "is_reply": bool(tpi.get("is_reply")),
                    "tipe": "post",
                })
    posts.sort(key=lambda x: x["epoch"], reverse=True)
    profile = None
    if user:
        profile = {"id": str(user.get("pk")), "username": user.get("username"),
                   "followers": user.get("follower_count")}
    return profile, posts


def fetch_account(username):
    """Ambil profil + daftar post (<= ~15 terbaru). Raises on failure."""
    status, src = fetch_profile(username)
    if status != 200 or "thread_items" not in src:
        raise ValueError(f"HTTP {status}, tidak ada data SSR (login wall? akun privat?)")
    profile, posts = parse(src, username)
    if not profile:
        raise ValueError("profil tidak ketemu (akun tidak ada / privat?)")
    return profile, posts
