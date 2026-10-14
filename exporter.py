#!/usr/bin/env python3
"""Export Excel format PEMANTAUAN AKUN MINGGUAN dari database.

Dihasilkan dari nol (tidak bergantung file template), strukturnya meniru
template asli: sheet per platform + kolom Jumlah Interaksi berupa rumus SUM.
"""
import datetime
import io

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

import db

HEADER = ["No", "Username", "Link Profile", "Views", "Komen", "Share",
          "Like", "Repost", "Jumlah Interaksi", "Catatan"]
SHEETS = [("INSTAGRAM", "instagram"), ("TIKTOK", "tiktok"),
          ("TRHEADS", "threads"), ("FACEBOOK", "facebook")]

HDR_FILL = PatternFill("solid", fgColor="1F4E5F")
HDR_FONT = Font(bold=True, color="FFFFFF", size=11)
TITLE_FONT = Font(bold=True, size=13)
NOTE_FONT = Font(italic=True, size=10, color="555555")
THIN = Side(style="thin", color="B0B0B0")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WIDTHS = [8, 22, 42, 10, 10, 10, 10, 10, 15, 34]


def build_workbook(sejak, sampai, platform=None):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    label = f"{sejak} s.d. {sampai}"

    sheets = [(s, p) for s, p in SHEETS if not platform or p == platform]
    for sheet_name, plat in sheets:
        ws = wb.create_sheet(sheet_name)
        ws["A1"] = f"PEMANTAUAN {label}"
        ws["A1"].font = TITLE_FONT
        for ci, h in enumerate(HEADER, 1):
            c = ws.cell(2, ci, h)
            c.font = HDR_FONT
            c.fill = HDR_FILL
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.border = BORDER
        for ci, w in enumerate(WIDTHS, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(ci)].width = w

        rows = db.dashboard(sejak, sampai, plat)
        for i, a in enumerate(rows, 3):
            vals = [a["kode"], a["username"],
                    _link_profile(a["platform"], a["username"]),
                    a["views"], a["komen"], a["share"], a["like"],
                    a["repost"], f"=SUM(D{i}:H{i})",
                    f"{a['n_post']} postingan" if a["n_post"] else ""]
            for ci, v in enumerate(vals, 1):
                c = ws.cell(i, ci, v)
                c.border = BORDER
                if ci in (4, 5, 6, 7, 8, 9):
                    c.alignment = Alignment(horizontal="center")

    # Ringkasan
    ws = wb.create_sheet("Ringkasan")
    ws["A1"] = f"Rekap {label}"
    ws["A1"].font = TITLE_FONT
    for ci, h in enumerate(["Platform", "Total Interaksi", "Akun aktif"], 1):
        c = ws.cell(2, ci, h)
        c.font = HDR_FONT
        c.fill = HDR_FILL
        c.border = BORDER
    r = 3
    for sheet_name, plat in sheets:
        rows = db.dashboard(sejak, sampai, plat)
        tot = sum(x["interaksi"] for x in rows)
        aktif = sum(1 for x in rows if x["n_post"])
        for ci, v in enumerate([sheet_name.title(), tot, aktif], 1):
            c = ws.cell(r, ci, v)
            c.border = BORDER
        r += 1
    for ci, w in enumerate([18, 16, 12], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(ci)].width = w
    # Keterbatasan data (jujur & terverifikasi — sel kosong = tidak diekspos publik)
    r += 1
    ws.cell(r, 1, "Keterbatasan data per platform (tanpa login)").font = TITLE_FONT
    r += 1
    notes = [
        ("TikTok", "Views, Komen, Share, Like ✓ | Repost tidak diekspos publik."),
        ("Instagram", "Views (reels), Komen, Like ✓ | Share & Repost tidak diekspos publik."),
        ("Threads", "Komen, Like, Repost ✓ | Views & Share tidak diekspos publik."),
        ("Facebook", "Butuh login — isi manual."),
    ]
    for plat, note in notes:
        c = ws.cell(r, 1, f"{plat}: {note}")
        c.font = NOTE_FONT
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        r += 1
    return wb


def _link_profile(platform, username):
    base = {"tiktok": "https://www.tiktok.com/@",
            "instagram": "https://www.instagram.com/",
            "threads": "https://www.threads.com/@",
            "facebook": "https://www.facebook.com/"}.get(platform, "")
    return f"{base}{username}"


def to_csv_bytes(sejak, sampai, platform=None):
    """CSV (dengan BOM UTF-8) — mudah dibuka di Excel & Google Sheets.

    Format: satu blok CSV (bukan multi-sheet). Semua akun dalam rentang
    tanggal, dengan kolom metrik yang sama seperti Excel. Nilai "tidak
    diekspos publik" ditulis sebagai string kosong, BUKAN 0.
    """
    import csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"Rekap {sejak} s.d. {sampai}"])
    w.writerow([])
    header = ["Kode", "Platform", "Username", "Link Profile", "Views",
              "Komen", "Share", "Like", "Repost", "Jumlah Interaksi",
              "Jumlah Postingan"]
    w.writerow(header)
    sheets = [(s, p) for s, p in SHEETS if not platform or p == platform]
    for _sheet_name, plat in sheets:
        rows = db.dashboard(sejak, sampai, plat)
        if not rows:
            continue
        w.writerow([f"--- {plat.upper()} ---"])
        for a in rows:
            w.writerow([a["kode"], plat, a["username"],
                        _link_profile(a["platform"], a["username"]),
                        a["views"] if a["views"] is not None else "",
                        a["komen"] if a["komen"] is not None else "",
                        a["share"] if a["share"] is not None else "",
                        a["like"] if a["like"] is not None else "",
                        a["repost"] if a["repost"] is not None else "",
                        a["interaksi"], a["n_post"]])
        w.writerow([])
    # BOM supaya Excel di Windows membaca UTF-8 dengan benar (Indonesia
    # banyak huruf beraksen).
    return ("﻿" + buf.getvalue()).encode("utf-8")


def csv_filename(sejak, sampai):
    return f"pemantauan_{sejak}_{sampai}.csv"


def to_bytes(sejak, sampai, platform=None):
    wb = build_workbook(sejak, sampai, platform)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def filename(sejak, sampai):
    return f"pemantauan_{sejak}_{sampai}.xlsx"
