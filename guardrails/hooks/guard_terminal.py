#!/usr/bin/env python3
"""Hook pre_tool_call untuk `terminal` / `process` — dipasang di profile IT.

IT adalah satu-satunya departemen yang boleh menjalankan perintah shell, dan
ia berjalan di VPS yang sama dengan database berisi PII TKI. Yang ditolak di
sini adalah tiga kelas perintah yang tidak punya alasan sah untuk dijalankan
seorang agent:

  1. Perusakan massal    — rm -rf pada akar/direktori data, mkfs, dd ke disk.
  2. Pembacaan rahasia   — cat .env, isi ~/.hermes/*/.env, dump Infisical.
  3. Pengeluaran data    — pipe ke curl/nc/scp yang mengirim keluar mesin,
                           dan pg_dump yang tidak menulis ke berkas lokal.

Bukan daftar yang sempurna, dan tidak dimaksudkan begitu: ia menutup jalan
yang mudah, sementara batas sesungguhnya tetap izin sistem di VPS.
"""

from __future__ import annotations

import json
import re
import sys

RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+(/|/\*|~|\$HOME|/var/lib/postgresql)"),
        "penghapusan rekursif pada akar sistem atau direktori data",
    ),
    (re.compile(r"\bmkfs\b|\bdd\s+[^|]*of=/dev/"), "penulisan langsung ke perangkat blok"),
    (re.compile(r">\s*/dev/(sd|nvme|vd)"), "penimpaan perangkat disk"),
    (
        re.compile(r"\b(cat|less|more|head|tail|strings|xxd)\b[^|;&]*\.env\b"),
        "pembacaan berkas .env (kredensial ada di Infisical, bukan untuk dibaca agent)",
    ),
    (
        re.compile(r"\binfisical\b[^|;&]*\b(export|secrets\s+get)\b"),
        "pengambilan nilai rahasia dari Infisical",
    ),
    (
        re.compile(r"\bpsql\b[^|;&]*\b(candidates|candidate_documents|sensitive_access_log)\b"),
        "akses SQL langsung ke tabel ber-PII (pakai tool MCP supaya tercatat)",
    ),
    (
        re.compile(r"\|\s*(curl|wget|nc|ncat|socat)\b"),
        "pengiriman keluaran perintah ke jaringan",
    ),
    (
        re.compile(r"\bcurl\b[^|;&]*(-d|--data|-T|--upload-file|-F)\b[^|;&]*\$\(?[A-Z_]{3,}"),
        "pengiriman isi variabel lingkungan ke layanan luar",
    ),
    (
        re.compile(r"\bpg_dump\b(?![^|;&]*\s(-f|--file)\b)"),
        "pg_dump tanpa tujuan berkas lokal (backup dijalankan cron terenkripsi, bukan agent)",
    ),
    (
        re.compile(r"\b(scp|rsync)\b[^|;&]*\s\S+@\S+:"),
        "penyalinan berkas ke mesin lain",
    ),
    (
        re.compile(r"\bhistory\s+-c\b|\btruncate\b[^|;&]*audit|\bshred\b"),
        "penghapusan jejak",
    ),
]


def main() -> None:
    raw = sys.stdin.read()
    try:
        tool_input = json.loads(raw).get("tool_input") or {}
        command = " ".join(
            str(tool_input.get(key, ""))
            for key in ("command", "cmd", "script", "args")
            if tool_input.get(key)
        )
    except Exception:
        # Payload rusak diperiksa apa adanya, bukan diloloskan.
        command = raw

    if not command.strip():
        print("{}")
        return

    for pattern, label in RULES:
        if pattern.search(command):
            reason = (
                f"DIBLOKIR guardrail ALTA: {label}. VPS ini memegang PII TKI, invoice, "
                "dan jejak audit. Kalau tindakan ini memang perlu, ajukan lewat "
                "raise_escalation supaya founder yang memutuskan."
            )
            print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
            return

    print("{}")


if __name__ == "__main__":
    main()
