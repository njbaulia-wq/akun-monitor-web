#!/usr/bin/env python3
"""Konversi waktu ke WIB (UTC+7) untuk semua stored posting.

MASALAH YANG DISELESAIKAN (ditemukan 2026-10-11):
    Timestamp dari Threads/TikTok/Facebook disimpan sebagai string UTC
    ("2026-10-04 03:41:10"), TETAPI batas pekan & filter tanggal di UI memakai
    WIB. Dua-duanya tidak konsisten.

    Dampaknya: posting pada jam >= 16:00 UTC (= >= 23:00 WIB) akan bergeser
    ke tanggal berikutnya, dan posting Minggu >= 16:00 UTC masuk ke pekan
    BERBEDA -> rekap mingguan meleset.

    Instagram tidak punya epoch sama sekali (og:date hanya "October 1, 2026"),
    jadi timestamplahir di midnight WIB dan TIDAK dikonversi (sudah WIB).

SETELAH perubahan ini: `posted_at` SELALU string WIB. Semua filter tanggal
dan batas pekan konsisten.
"""
import datetime

WIB = datetime.timezone(datetime.timedelta(hours=7), "WIB")
UTC = datetime.timezone.utc


def to_wib_str(epoch, fmt="%Y-%m-%d %H:%M:%S"):
    """Epoch (detik) -> string WIB. None/0 -> None."""
    if not epoch:
        return None
    try:
        return datetime.datetime.fromtimestamp(
            int(epoch), UTC).astimezone(WIB).strftime(fmt)
    except (ValueError, TypeError, OSError):
        return None


def date_str(epoch):
    """Epoch -> tanggal WIB saja ('YYYY-MM-DD')."""
    return to_wib_str(epoch, "%Y-%m-%d")


def midnight_wib(date_text):
    """'October 1, 2026' / '2026-10-01' -> epoch midnight WIB."""
    d = parse_date(date_text)
    if d is None:
        return None
    return int(datetime.datetime(d.year, d.month, d.day,
                                 tzinfo=WIB).timestamp())


def parse_date(text):
    """'October 1, 2026' atau '2026-10-01' -> datetime.date."""
    if not text:
        return None
    for f in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y"):
        try:
            return datetime.datetime.strptime(text.strip(), f).date()
        except ValueError:
            continue
    return None


def now_wib():
    return datetime.datetime.now(WIB)


def today_wib():
    return now_wib().date()


def shift_wib(stamp_text, hours=7):
    """Naikkan/ turunkan string timestamp (untuk migrasi data lama).

    PERINGATAN: jangan pernah menjalankan migrasi ini dua kali.
    db.run() membuka koneksi baru tiap panggilan, jadi BEGIN/COMMIT lintas
    pemanggilan TIDAK berlaku — Update yang sudah dieksekusi tetap tersimpan
    walau COMMIT-nya gagal. Selalu cek dry-run + backup sebelum jalan.
    """
    try:
        dt = datetime.datetime.strptime(stamp_text, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return stamp_text
    return (dt + datetime.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")