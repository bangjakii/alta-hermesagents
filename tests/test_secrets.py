"""Uji penyebaran kredensial.

Yang dijaga di sini bukan kenyamanan, melainkan pembatasan: satu berkas di repo
boleh menjadi sumbernya, tetapi tiap profile hanya menerima kunci yang jadi
haknya. Pembagian provider ALTA dibuat atas dasar PII — kunci Anthropic yang
ikut mendarat di profile MiniMax membuat pembagian itu tidak berarti apa-apa.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from alta_hermes.config import Settings
from alta_hermes.secrets import TELEGRAM_KEYS, distribute, keys_for, plan_for
from alta_hermes.sources import load_from_files

REPO = Path(__file__).resolve().parents[1]

SUMBER = {
    "ALTA_DATABASE_URL": "postgresql://alta:rahasia@127.0.0.1:5432/alta",
    "ANTHROPIC_API_KEY": "sk-ant-kunci-uji",
    "OPENROUTER_API_KEY": "sk-or-kunci-uji",
    "TELEGRAM_BOT_TOKEN": "7123456789:token-uji",
    "TELEGRAM_ALLOWED_USERS": "12345",
    "TELEGRAM_HOME_CHANNEL": "12345",
}


@pytest.fixture(scope="module")
def state():
    return load_from_files(REPO)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        repo_root=REPO,
        profiles_root=tmp_path,
        database_url=None,
        backend_dir=Path("/opt/alta/alta-database/backend"),
        mcp_command="/opt/alta/alta-database/backend/.venv/bin/alta-mcp",
        mcp_args=(),
        profile_prefix="alta-",
    )


def test_departemen_pii_hanya_menerima_kunci_anthropic(state, settings):
    isi = plan_for(state.agents["recruitment"], settings, SUMBER).content
    assert "ANTHROPIC_API_KEY=sk-ant-kunci-uji" in isi
    assert "OPENROUTER_API_KEY" not in isi


def test_departemen_non_pii_tidak_pernah_menerima_kunci_anthropic(state, settings):
    for code in ("sales", "marketing", "it"):
        isi = plan_for(state.agents[code], settings, SUMBER).content
        assert "OPENROUTER_API_KEY=sk-or-kunci-uji" in isi
        assert "ANTHROPIC_API_KEY" not in isi, f"{code} menerima kunci ber-PII"


def test_token_telegram_hanya_sampai_ke_orchestrator(state, settings):
    assert all(k in keys_for(state.agents["orchestrator"]) for k in TELEGRAM_KEYS)
    for code, agent in state.agents.items():
        if code == "orchestrator":
            continue
        isi = plan_for(agent, settings, SUMBER).content
        assert "TELEGRAM_BOT_TOKEN" not in isi, f"{code} punya kanal ke founder"


def test_semua_profile_menerima_alamat_database(state, settings):
    for agent in state.agents.values():
        assert "ALTA_DATABASE_URL=postgresql://" in plan_for(agent, settings, SUMBER).content


def test_nilai_kosong_dilaporkan_bukan_ditulis_diam_diam(state, settings):
    plan = plan_for(state.agents["legal"], settings, {"ALTA_DATABASE_URL": "postgresql://x"})
    assert "ANTHROPIC_API_KEY" in plan.missing
    assert "ANTHROPIC_API_KEY=\n" in plan.content


def test_setelan_operator_di_profile_dipertahankan(state, settings):
    path = settings.profile_dir("alta-legal")
    path.mkdir(parents=True, exist_ok=True)
    (path / ".env").write_text("HERMES_LOG_LEVEL=debug\n", encoding="utf-8")

    isi = plan_for(state.agents["legal"], settings, SUMBER).content
    assert "HERMES_LOG_LEVEL=debug" in isi


def test_uji_coba_tidak_menyentuh_berkas(state, settings):
    distribute(state, settings, SUMBER, dry_run=True)
    assert not list(settings.profiles_root.glob("*/.env"))


def test_penulisan_nyata_menghasilkan_satu_berkas_per_profile(state, settings):
    plans = distribute(state, settings, SUMBER, dry_run=False)
    assert len(plans) == 9
    for plan in plans:
        assert plan.path.is_file()
        assert plan.path.read_text(encoding="utf-8").startswith("# Dihasilkan")
