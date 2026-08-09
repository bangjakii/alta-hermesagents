"""Menyebarkan kredensial dari satu berkas ke `.env` tiap profile Hermes.

Hermes membaca rahasianya dari `.env` milik masing-masing profile. Dengan
sembilan departemen, itu berarti sembilan berkas yang harus diisi tangan —
pekerjaan yang membosankan, gampang salah, dan gampang bocor karena orang lalu
menyalin-tempel kunci ke tempat yang salah.

Modul ini menjadikannya satu berkas: `.env` di akar repo (yang sudah masuk
`.gitignore`). Dari situ tiap profile hanya menerima **apa yang memang
dibutuhkannya**:

- kunci provider **milik departemen itu saja** — profile MiniMax tidak pernah
  menerima kunci Anthropic, dan sebaliknya. Pembagian provider ALTA dibuat atas
  dasar PII, jadi kunci yang tersebar ke mana-mana melunturkan pembagian itu;
- token Telegram **hanya untuk orchestrator**, karena hanya dia yang punya kanal
  ke founder.

Untuk produksi, sumbernya tetap Infisical: isi `.env` repo dari
`infisical export`, jalankan perintah ini, lalu hapus. Nilai rahasianya tidak
pernah ditulis ke berkas yang di-commit dan tidak pernah dicetak ke layar.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .models import Agent, DesiredState

HEADER = (
    "# Dihasilkan `alta-hermes secrets` dari .env repo alta-hermesagents.\n"
    "# JANGAN di-commit dan jangan disalin ke profile lain: tiap profile hanya\n"
    "# menerima kunci yang memang jadi haknya.\n"
)

# Variabel lingkungan yang membawa kunci tiap provider.
PROVIDER_KEYS: dict[str, tuple[str, ...]] = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "minimax": ("MINIMAX_API_KEY", "MINIMAX_GROUP_ID"),
    "openai": ("OPENAI_API_KEY",),
}

# Hanya orchestrator. Departemen lain tidak punya kanal ke manusia, jadi token
# ini di profile mereka bukan sekadar mubazir — ia melubangi aturan satu pintu.
TELEGRAM_KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS", "TELEGRAM_HOME_CHANNEL")


@dataclass
class SecretPlan:
    """Apa yang akan ditulis ke satu profile — nama kunci saja, bukan nilainya."""

    profile_name: str
    path: Path
    keys: tuple[str, ...]
    missing: tuple[str, ...]
    content: str


def keys_for(agent: Agent) -> tuple[str, ...]:
    provider = (agent.provider or "").strip().lower()
    keys = PROVIDER_KEYS.get(provider, (f"{provider.upper()}_API_KEY",) if provider else ())
    if agent.code == "orchestrator":
        keys = keys + TELEGRAM_KEYS
    return ("ALTA_DATABASE_URL",) + keys


def plan_for(agent: Agent, settings: Settings, source: dict[str, str]) -> SecretPlan:
    wanted = keys_for(agent)
    path = settings.profile_dir(agent.profile_name) / ".env"

    existing = _read_env(path)
    # Kunci yang sudah ada di profile tapi bukan urusan kita dibiarkan utuh —
    # operator boleh menaruh setelan lain di sana.
    merged = dict(existing)
    missing = []
    for key in wanted:
        value = source.get(key, "").strip()
        if not value:
            missing.append(key)
            merged.setdefault(key, "")
            continue
        merged[key] = value

    lines = [HEADER]
    for key in wanted:
        lines.append(f"{key}={merged[key]}")
    extra = [k for k in merged if k not in wanted]
    if extra:
        lines.append("\n# Disetel operator, dipertahankan apa adanya:")
        lines += [f"{k}={merged[k]}" for k in sorted(extra)]

    return SecretPlan(
        profile_name=agent.profile_name,
        path=path,
        keys=wanted,
        missing=tuple(missing),
        content="\n".join(lines).rstrip() + "\n",
    )


def distribute(
    state: DesiredState, settings: Settings, source: dict[str, str], *, dry_run: bool
) -> list[SecretPlan]:
    plans = [plan_for(agent, settings, source) for agent in state.agents.values()]
    if dry_run:
        return plans
    for plan in plans:
        plan.path.parent.mkdir(parents=True, exist_ok=True)
        plan.path.write_text(plan.content, encoding="utf-8", newline="\n")
        try:
            plan.path.chmod(0o600)  # tidak berarti di Windows, wajib di VPS
        except OSError:
            pass
    return plans


def _read_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values
