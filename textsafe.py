"""Utilitas teks bersama (netral — tidak import modul lain).

`_fix_surrogates` lived in scrape.py, tapi fetchers/instagram.py juga
membutuhkannya sementara scrape.py meng-import fetchers -> circular import.
Modul netral ini dipakai kedua sisi.
"""


def _fix_surrogates(s):
    """Gabungkan pasangan surrogate menjadi satu karakter (emoji).

    PENTING (bug terverifikasi 2026-10-11): `chr(int(h, 16))` untuk setiap
    escape \\uXXXX menghasilkan surrogate LARI (U+D800..U+DFFF) untuk emoji,
    karena emoji ditulis sebagai PASANGAN: \\uD83C\\uDFEE. Python tidak
    menggabungkannya otomatis, dan string berisi surrogate liar TIDAK bisa
    di-encode UTF-8 -> `json.dumps(...).encode('utf-8')` melempar
    "surrogates not allowed" -> server balas HTTP 500 untuk SELURUH isi job.

    Terukur: 9 dari 24 caption Threads (37%) punya emoji, jadi hampir semua
    job akan 500. Di sini pasangan digabung jadi karakter asli, dan surrogate
    yang benar-benar sendirian diganti U+FFFD.
    """
    if not isinstance(s, str) or not s:
        return s
    if not any(0xD800 <= ord(c) <= 0xDFFF for c in s):
        return s
    out = []
    i, n = 0, len(s)
    while i < n:
        o = ord(s[i])
        if 0xD800 <= o <= 0xDBFF and i + 1 < n:
            o2 = ord(s[i + 1])
            if 0xDC00 <= o2 <= 0xDFFF:
                out.append(chr(0x10000 + ((o - 0xD800) << 10) + (o2 - 0xDC00)))
                i += 2
                continue
        out.append("�" if 0xD800 <= o <= 0xDFFF else s[i])
        i += 1
    return "".join(out)


def json_safe(obj):
    """Pastikan apa pun bisa di-serialize jadi JSON UTF-8 yang valid.

    Dipakai sebagai pengaman terakhir sebelum mengirim respons API, supaya
    satu karakter aneh tidak bisa menggagalkan seluruh respons dengan 500.
    """
    if isinstance(obj, str):
        return _fix_surrogates(obj)
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    return obj