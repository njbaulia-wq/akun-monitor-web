#!/usr/bin/env python3
"""Diagnosa koneksi Facebook + cookie sesi — jalankan di MESIN ANDA.

    python3 cek_facebook.py [url_opsional]

Menguji lapis demi lapis dan mencetak APA yang gagal, supaya tidak perlu
menebak. Tidak mengirim cookie ke mana pun selain facebook.com.
"""
import re
import socket
import sys
import urllib.error
import urllib.request

sys.path.insert(0, __file__.rsplit("/", 1)[0] if "/" in __file__ else ".")
import db  # noqa: E402
import session  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.facebook.com/share/r/1MGLJCGNcc/"

socket.setdefaulttimeout(8)
db.init()
cookies = session.get_stored("facebook")
CH = session.cookie_header(cookies)

print("=" * 70)
print("DIAGNOSA FACEBOOK")
print("=" * 70)
print(f"URL  uji : {URL}")
print(f"Cookie    : {len(cookies)} cookie ({', '.join(sorted(cookies)[:8])})")
print(f"DB        : {db.DB_PATH}\n")

print("[1] DNS + konektivitas tiap host")
hosts = ["www.facebook.com", "m.facebook.com", "free.facebook.com",
         "mbasic.facebook.com", "graph.facebook.com"]
alive = []
for h in hosts:
    try:
        socket.gethostbyname(h)
        dns = "DNS OK"
    except Exception as e:
        print(f"  {h:<24} DNS GAGAL ({type(e).__name__})")
        continue
    try:
        req = urllib.request.Request(f"https://{h}/", headers={
            "User-Agent": session.UA_DESKTOP})
        with urllib.request.urlopen(req, timeout=8) as r:
            print(f"  {h:<24} {dns} | HTTP {r.status} ({len(r.read())} byte)")
            alive.append(h)
    except urllib.error.HTTPError as e:
        note = " (API hidup)" if e.code == 400 else ""
        print(f"  {h:<24} {dns} | HTTP {e.code}{note}")
        if e.code in (200, 400):
            alive.append(h)
    except Exception as e:
        print(f"  {h:<24} {dns} | {type(e).__name__}: {str(e)[:40]}")

if "www.facebook.com" not in alive:
    print("\n  >> www.facebook.com TIDAK bisa diakses — ini bukan soal cookie.")
    print("     Favicon/anak: ganti www -> m. atau free., atau cek VPN/firewall.")

print("\n[2] Apakah sesi login valid?")
try:
    r = session.test_session("facebook", cookies)
    print(f"  ok={r['ok']} :: {r['detail'][:100]}")
except Exception as e:
    print(f"  ERR {e}")

print("\n[3] Ambil halaman postingan")
try:
    s, body, final = session.fetch(URL, cookies, timeout=25)
    print(f"  HTTP {s} | {len(body)} byte | final: {final[:70]}")
    if s != 200:
        print("  >> Gagal buka. Cek cookie / host.")
    elif "login" in final.lower() or re.search(r"<title>\s*Log in", body[:4000], re.I):
        print("  >> Login wall — COOKIE KEDALUWARSA. Ambil ulang cookie.")
    else:
        found = {k: (k in body) for k in
                 ("reaction_count", "comment_count", "share_count",
                  "video_view_count", "creation_time", "post_id")}
        ada = [k for k, v in found.items() if v]
        print(f"  field metrik ditemukan: {ada or 'TIDAK ADA'}")
        if not ada:
            m = re.search(r"<title[^>]*>([^<]{0,60})", body)
            print(f"  title: {m.group(1).strip() if m else '-'}")
            print("  >> Konten privat, sudah dihapus, atau markup berubah.")
        else:
            import scrape
            try:
                d = scrape.scrape_facebook_post(URL, cookies)
                print("\n  HASIL:")
                for k in ("author", "posted_at", "views", "like", "komen",
                          "share", "post_key"):
                    print(f"    {k:<11}: {d.get(k)}")
            except Exception as e:
                print(f"  parser: {type(e).__name__}: {str(e)[:110]}")
except Exception as e:
    print(f"  ERR {type(e).__name__}: {str(e)[:90]}")

print("\n" + "=" * 70)
print("Kirim output di atas kalau masih gagal.")