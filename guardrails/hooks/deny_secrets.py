#!/usr/bin/env python3
"""Hook pre_tool_call: tolak panggilan tool yang membawa rahasia sungguhan.

Dipasang di SEMUA departemen. Kesalahan yang ditangkapnya bukan serangan
canggih, melainkan yang paling mungkin benar-benar terjadi: agent menempelkan
token ke kolom yang salah, atau menaruh API key ke dalam catatan/tiket yang
kelak dibaca orang lain.

Database sudah punya CHECK serupa di `service_registry` dan `repositories`.
Hook ini menutup permukaan yang tidak dijaga CHECK itu: SETIAP tool, termasuk
tiket, pesan, dan konten marketing.

Protokol: payload JSON di stdin, jawaban JSON di stdout.
  {"decision": "block", "reason": "..."}  -> panggilan dibatalkan
  {}                                      -> diteruskan
"""

from __future__ import annotations

import json
import re
import sys

# Pola yang menandai rahasia sungguhan, bukan sekadar kata "password".
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("kunci API Anthropic/OpenAI", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")),
    ("token GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("access key AWS", re.compile(r"\bAKIA[0-9A-Z]{12,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("token bot Telegram", re.compile(r"\b\d{8,}:[A-Za-z0-9_-]{30,}")),
    ("service token Infisical", re.compile(r"\bst\.[A-Za-z0-9._-]{30,}")),
    ("URL Postgres berpassword", re.compile(r"postgres(?:ql)?://[^\s:]+:[^\s@]{6,}@")),
]


def scan(value: object) -> str | None:
    """Kembalikan nama pola pertama yang cocok di mana pun dalam struktur."""
    if isinstance(value, str):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(value):
                return label
        return None
    if isinstance(value, dict):
        for item in value.values():
            hit = scan(item)
            if hit:
                return hit
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            hit = scan(item)
            if hit:
                return hit
    return None


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
        tool_name = payload.get("tool_name") or "tool"
        hit = scan(payload.get("tool_input"))
    except Exception:
        # Payload rusak tidak boleh berarti "lolos". Sebuah penyaring yang
        # membuka pintu setiap kali ia bingung tidak menyaring apa pun —
        # jadi teks mentahnya tetap diperiksa.
        tool_name = "tool"
        hit = scan(raw)

    if hit:
        reason = (
            f"DIBLOKIR guardrail ALTA: argumen `{tool_name}` memuat {hit}. "
            "Kredensial tidak pernah masuk database, tiket, pesan, atau konten - "
            "simpan di Infisical dan rujuk jalurnya (infisical_path) saja. "
            "Kalau ini kebocoran nyata, laporkan lewat raise_escalation."
        )
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
        return

    print("{}")


if __name__ == "__main__":
    main()
