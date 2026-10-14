#!/usr/bin/env python3
"""Fetcher Instagram TANPA login — halaman embed + halaman postingan.

Terbukti jalan di sandbox 2026-10-10 (read-only, tanpa sesi).
Per postingan butuh 2 request:
  A. /{p|reel}/<shortcode>/embed/captioned/ -> like & komen & views (reels) PERSIS
     dari JSON: edge_liked_by.count, edge_media_to_comment.count, video_view_count
  B. /{p|reel}/<shortcode>/ -> tanggal posting dari og:description
     ("11K likes, 180 comments - user on September 18, 2025: ...")
     (PERHATIAN: field "timestamp" di halaman embed adalah junk konfigurasi,
     JANGAN dipakai.)

Wajib User-Agent crawler (facebookexternalhit); UA browser biasa -> halaman generik.

Keterbatasan (jujur, terverifikasi):
- Daftar postingan per akun TIDAK bisa tanpa login (semua endpoint API 429/
  diblokir dari IP server; HTML profil tidak memuat daftar postingan).
  -> shortcode/link disuplai dari posts.csv (catatan posting tim sendiri).
- Share & repost count TIDAK diekspos publik sama sekali oleh Instagram.
- Views hanya untuk reels/video; foto/carousel = n/a.
"""
import datetime
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import textsafe  # noqa: E402
import wibtime as wib  # noqa: E402

CRAWLER_UA = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
RE_SHORTCODE = re.compile(r"instagram\.com/(?:p|reel|reels?|tv)/([A-Za-z0-9_-]+)")
RE_OGDATE = re.compile(
    r'([\d.,KMB]+) likes, ([\d,]+) comments - (\S+) on ([A-Z][a-z]+ \d{1,2}, \d{4})')

TIPE = {"GraphVideo": "reel/video", "GraphImage": "photo", "GraphSidecar": "carousel"}


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": CRAWLER_UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def normalize_url(url):
    """Rapikan URL IG jadi bentuk '/reel/<code>/' atau '/p/<code>/'.

    '/reels/<code>/' (tab profil, jamak) dialihkan IG ke halaman login —
    bentuk itu tidak bisa dibaca. Shortcode selalu bentuk '/reel/<code>'.
    """
    u = (url or "").strip()
    m = RE_SHORTCODE.search(u)
    if not m:
        return u
    kind = "reel" if "/reel" in u.lower() else "p"
    return f"https://www.instagram.com/{kind}/{m.group(1)}/"


def shortcode_from_url(url):
    m = RE_SHORTCODE.search(url)
    if not m:
        raise ValueError(f"shortcode tidak ketemu di URL: {url}")
    kind = "reel" if "/reel" in url.lower() else "p"
    return m.group(1), kind


def _one(pat, text):
    m = re.search(pat, text)
    return m.group(1) if m else None


def parse_embed(html_src):
    un = html_src.replace('\\"', '"').replace("\\n", " ")
    typename = _one(r'"__typename":"(Graph\w+)"', un)
    return {
        "like": int(v) if (v := _one(r'"edge_liked_by":\{"count":(\d+)', un)) else None,
        "komen": int(v) if (v := _one(r'"edge_media_to_comment":\{"count":(\d+)', un)) else None,
        "views": int(v) if (v := _one(r'"video_view_count":(\d+)', un)) else None,
        "tipe": TIPE.get(typename, typename),
        "owner": _one(r'"owner":\{"id":"\d+","username":"([A-Za-z0-9_.]+)"', un),
        "caption": _parse_caption(un),
    }


def _parse_caption(un):
    """Teks caption dari edge_media_to_caption.

    Perhatikan: penutupnya "}}]}" (node punya children), bukan "}]}" seperti
    pola lama — itu sebabnya caption selalu kosong.
    Teks berisi escape \" dan \\ -> dibersihkan.
    """
    m = re.search(
        r'"edge_media_to_caption":\{"edges":\[\{"node":\{"text":"((?:[^"\\]|\\.)*)"',
        un)
    if not m:
        return ""
    txt = m.group(1)
    txt = re.sub(r'\\(["\\/])', r"\1", txt)   # \" -> " , \\ -> \
    txt = txt.replace("\\n", " ").replace("\\u0025", "%").replace("\\u0026", "&")
    # Instagram mengirim emoji sebagai pasangan \uD83C\uDFEE; tanpa
    # penggabungan, caption jadi surrogate liar yang TIDAK bisa di-encode
    # UTF-8 dan menggagalkan respons API (lihat textsafe._fix_surrogates).
    txt = textsafe._fix_surrogates(re.sub(
        r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), txt))
    return re.sub(r"\s+", " ", txt).strip()[:200]


def parse_post_date(html_src):
    m = RE_OGDATE.search(html_src)
    if not m:
        return None
    # IG hanya memberi TANGGAL ("October 1, 2026"), tanpa jam. Kita simpan
    # sebagai midnight WIB — bukan midnight UTC (terbukti: cross-post IG vs
    # Threads menunjukkan tanggal IG 1 hari lebih awal dari UTC). Lihat wibtime.py.
    return wib.midnight_wib(m.group(4))


def parse_og_metrics(html_src):
    """Cadangan: metrik dari og:description halaman utama.

    Format: "1,234 likes, 56 comments - username on September 18, 2025: ..."
   dipakai saat /embed/captioned/ TIDAK punya field metrik (terverifikasi
    2026-10-11: beberapa posting BALIKAN embed kosong tapi og:description
    halaman utama tetap lengkap). Views tidak ada di sini -> None (jujur).
    """
    m = RE_OGDATE.search(html_src)
    if not m:
        return None
    return {"like": _parse_count(m.group(1)),
            "komen": _parse_count(m.group(2)),
            "views": None}


def _parse_count(s):
    s = (s or "").strip().replace(",", "")
    m = re.match(r"([\d.]+)([KMB]?)", s)
    if not m:
        return None
    return int(float(m.group(1)) * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2)])


def _parse_og_owner(html_src):
    """'&#064;dragon.21758122 on Instagram: ...' -> 'dragon.21758122'."""
    m = re.search(r'<meta property="og:title" content="(?:&#0?64;|@)([^"]{1,60}?)\s+on\s+Instagram', html_src)
    return m.group(1) if m else None


def _parse_og_caption(html_src):
    """Caption dari og:description: '0 likes, 0 comments - user on Date: "..."'."""
    m = re.search(r'<meta property="og:description" content="([^"]*)"', html_src)
    if not m:
        return ""
    import html as _html
    txt = _html.unescape(m.group(1))
    q = re.search(r'-\s*[^:]*:\s*"(.*)', txt)
    return re.sub(r"\s+", " ", q.group(1)).strip()[:200] if q else ""


def fetch_post(url):
    """Ambil metrik satu postingan IG. Raises on failure."""
    url = normalize_url(url)
    shortcode, kind = shortcode_from_url(url)
    main_url = f"https://www.instagram.com/{kind}/{shortcode}/"
    emb_html = fetch(f"{main_url}embed/captioned/")
    main_html = fetch(main_url)
    has_embed = '"edge_liked_by"' in emb_html.replace('\\"', '"')
    if has_embed:
        emb = parse_embed(emb_html)
    else:
        # Embed kosong -> ambil dari og:description (JANGAN gagalkan, datanya
        # sering tetap ada di halaman utama).
        og = parse_og_metrics(main_html)
        if og is None:
            raise ValueError(
                f"postingan tidak bisa dibaca (Instagram tidak mengirim data "
                f"untuk {kind}/{shortcode}). Bisa jadi privat atau dihapus.")
        emb = {"like": og["like"], "komen": og["komen"], "views": og["views"],
               "tipe": "reel/video" if kind == "reel" else "photo",
               "owner": _parse_og_owner(main_html), "caption": _parse_og_caption(main_html)}
    epoch = parse_post_date(main_html)
    emb.update({
        "post_id": shortcode,
        "permalink": f"https://www.instagram.com/{kind}/{shortcode}/",
        "epoch": epoch or 0,
        "posted_at_utc": wib.to_wib_str(epoch),
        "share": None,   # tidak diekspos publik
        "repost": None,  # tidak diekspos publik
        "is_reply": False,
    })
    return emb


def profile_info(username):
    """Info agregat profil (followers/following/jumlah post; >10K disingkat)."""
    html_src = fetch(f"https://www.instagram.com/{username}/")
    m = re.search(r'<meta property="og:description" content="([^"]+)"', html_src)
    return {"og_description": m.group(1) if m else None}
