"""Pengaturan boot script — semuanya alamat dan jalur, tidak satu pun rahasia."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    """Konfigurasi tidak memadai untuk tindakan yang diminta."""


def _repo_root() -> Path:
    # src/alta_hermes/config.py -> naik tiga tingkat
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    profiles_root: Path
    database_url: str | None
    backend_dir: Path | None
    mcp_command: str
    mcp_args: tuple[str, ...]
    profile_prefix: str

    @classmethod
    def from_env(cls) -> Settings:
        root = _repo_root()
        _load_dotenv(root / ".env")

        profiles_root = os.getenv("HERMES_PROFILES_ROOT") or str(
            Path.home() / ".hermes" / "profiles"
        )
        backend = os.getenv("ALTA_BACKEND_DIR") or ""
        args = os.getenv("ALTA_MCP_ARGS", "run,alta-mcp")

        return cls(
            repo_root=root,
            profiles_root=Path(profiles_root).expanduser(),
            database_url=os.getenv("ALTA_DATABASE_URL") or None,
            backend_dir=Path(backend).expanduser() if backend else None,
            mcp_command=os.getenv("ALTA_MCP_COMMAND", "uv"),
            mcp_args=tuple(a.strip() for a in args.split(",") if a.strip()),
            profile_prefix=os.getenv("ALTA_PROFILE_PREFIX", "alta-"),
        )

    def require_database(self) -> str:
        if not self.database_url:
            raise ConfigError(
                "ALTA_DATABASE_URL belum diisi. Salin .env.example ke .env dan isi "
                "alamat database (passwordnya dari Infisical, bukan dari repo)."
            )
        return self.database_url

    def profile_dir(self, profile_name: str) -> Path:
        return self.profiles_root / profile_name

    @property
    def guardrails_file(self) -> Path:
        return self.repo_root / "guardrails" / "GUARDRAILS.md"

    @property
    def profiles_policy_file(self) -> Path:
        return self.repo_root / "guardrails" / "profiles.yaml"

    @property
    def hooks_dir(self) -> Path:
        return self.repo_root / "guardrails" / "hooks"


def _load_dotenv(path: Path) -> None:
    """Muat .env sederhana tanpa dependensi tambahan.

    Nilai yang sudah ada di lingkungan tidak ditimpa — supaya `ALTA_DATABASE_URL=...
    alta-hermes render` untuk sekali jalan tetap bekerja seperti yang diharapkan.
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
