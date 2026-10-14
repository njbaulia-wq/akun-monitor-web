#!/usr/bin/env python3
"""Migrasi posted_at dari UTC -> WIB untuk data yang SUDAH tersimpan.

    python3 migrasi_wib.py          # cek dulu (dry-run)
    python3 migrasi_wib.py --jalankan

Aman: karena tidak ada posting pada jam >= 16:00 UTC, menggeser +7 jam
TIDAK mengubah satu pun tanggal — hanya jamnya. Backup otomatis dibuat.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402
import wibtime as wib  # noqa: E402

JALANKAN = "--jalankan" in sys.argv
KOREKSI = "--koreksi" in sys.argv     # untuk mengembalikan +14 -> +7
db.init()

rows = db.q("SELECT id, platform, posted_at FROM posts "
            "WHERE posted_at IS NOT NULL AND length(posted_at) >= 19 "
            "AND platform != 'instagram'")
print(f"posting bertanggal (IG dikecualikan): {len(rows)}\n")
print("Catatan: Instagram tidak punya jam sama sekali (og:date hanya tanggal),")
print("jadi dibiarkan 00:00 — menggesernya tidak menambah informasi.\n")

geser_tanggal = []
per_platform = {}
for r in rows:
    try:
        lama = __import__("datetime").datetime.strptime(
            r["posted_at"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        continue
    baru = wib.shift_wib(r["posted_at"])
    per_platform.setdefault(r["platform"], [0, 0])
    per_platform[r["platform"]][0] += 1
    if baru[:10] != r["posted_at"][:10]:
        per_platform[r["platform"]][1] += 1
        geser_tanggal.append((r, lama, baru))

print(f"{'platform':<12} {'total':>6} {'tanggal geser':>14}")
print("-" * 36)
for plat, (n, geser) in sorted(per_platform.items()):
    print(f"{plat:<12} {n:>6} {geser:>14}")
print("-" * 36)
print(f"{'TOTAL':<12} {len(rows):>6} {len(geser_tanggal):>14}")

if geser_tanggal:
    print("\nposting yang TANGGALNYA akan bergeser:")
    for r, lama, baru in geser_tanggal[:20]:
        print(f"  {r['platform']:<10} {r['posted_at']} -> {baru}")
else:
    print("\n-> TIDAK ADA tanggal yang bergeser. Migrasi hanya mengubah JAM,")
    print("   rekap mingguan & harian TIDAK berubah sama sekali.")

# IG: jam 00:00 hasil konversi og:date -> jangan digeser lagi
n_ig = per_platform.get("instagram", [0])[0]

if not JALANKAN:
    print("\nDRY-RUN. Jalankan dengan: python3 migrasi_wib.py --jalankan")
    sys.exit(0)

bak = db.backup_db("-sebelum-migrasi-wib")
print(f"\nbackup: {os.path.basename(bak)}")

# Transaksi harus jalan di SATU koneksi (db.run() membuka koneksi baru
# tiap panggilan, jadi BEGIN/COMMIT lintas pemanggilan tidak berlaku).
conn = db.connect()
try:
    conn.execute("BEGIN")
    n = 0
    for r in rows:
        baru = wib.shift_wib(r["posted_at"], -7 if KOREKSI else 7)
        conn.execute("UPDATE posts SET posted_at=? WHERE id=?", (baru, r["id"]))
        n += 1
    conn.commit()
except Exception:
    conn.rollback()
    print("GAGAL, sudah rollback.")
    raise
finally:
    conn.close()
print(f"{n} posting dikonversi ke WIB")
contoh = db.q("SELECT platform, posted_at FROM posts ORDER BY id DESC LIMIT 5")
print("\ncontoh setelah migrasi:")
for c in contoh:
    print(f"  {c['platform']:<10} {c['posted_at']}")
print("\nSELESAI. Data lama & baru kini sama-sama WIB.")