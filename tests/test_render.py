"""Uji lapisan render — yang diperiksa di sini adalah janji yang dipegang repo ini.

Bukan uji "kodenya jalan", melainkan uji bahwa aturan yang kita klaim ditegakkan
memang ditegakkan: guardrail selalu di atas, config.yaml milik Hermes tidak
dirusak, orkestrator berjalan baca-saja, dan satu pintu tidak bocor.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from alta_hermes.config import Settings
from alta_hermes.models import Agent
from alta_hermes.render import (
    deliver_target,
    dump_config,
    render_config,
    render_cron,
    render_mcp_launcher,
    render_soul,
)
from alta_hermes.sources import SourceError, load_from_files, load_policy, parse_directives

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def state():
    return load_from_files(REPO)


@pytest.fixture(scope="module")
def policies():
    return load_policy(REPO / "guardrails" / "profiles.yaml")


@pytest.fixture(scope="module")
def settings(tmp_path_factory):
    root = tmp_path_factory.mktemp("profiles")
    backend = Path("/opt/alta/alta-database/backend")
    return Settings(
        repo_root=REPO,
        profiles_root=root,
        database_url=None,
        backend_dir=backend,
        mcp_command=(backend / ".venv" / "bin" / "alta-mcp").as_posix(),
        mcp_args=(),
        profile_prefix="alta-",
    )


# ------------------------------------------------------------------ parsing


def test_parse_memecah_heading_menjadi_baris():
    rows = parse_directives(
        "# judul dokumen\nabaikan ini\n\n"
        "## persona\nsaya agen\n\n"
        "## policy: Ambang\naturannya begini\n\n"
        "## sop: Langkah\nsatu dua tiga\n",
        "finance",
    )
    assert [(r.section, r.title) for r in rows] == [
        ("persona", None),
        ("policy", "Ambang"),
        ("sop", "Langkah"),
    ]
    assert "abaikan ini" not in "".join(r.content for r in rows)
    assert rows[0].position == 10


def test_persona_ganda_ditolak():
    with pytest.raises(SourceError):
        parse_directives("## persona\na\n\n## persona\nb\n", "it")


def test_persona_berjudul_ditolak():
    # Database hanya mengizinkan satu persona aktif tanpa judul per departemen.
    with pytest.raises(SourceError):
        parse_directives("## persona: Nama\nisi\n", "it")


def test_bagian_kosong_ditolak():
    with pytest.raises(SourceError):
        parse_directives("## policy: Kosong\n\n", "it")


def test_seluruh_departemen_punya_persona_dan_sop(state):
    for code in state.agents:
        sections = {d.section for d in state.directives_for(code)}
        assert "persona" in sections, f"{code} tanpa persona"
        assert "sop" in sections, f"{code} tanpa SOP"


# --------------------------------------------------------------------- SOUL


def test_guardrail_selalu_mendahului_persona(state):
    guardrails = (REPO / "guardrails" / "GUARDRAILS.md").read_text(encoding="utf-8")
    soul = render_soul(state, state.agents["sales"], guardrails)
    assert soul.index("Guardrail ALTA") < soul.index("## Kebijakan Departemen")
    assert "Satu pintu ke founder" in soul


def test_soul_muat_dalam_batas_context_file(state):
    guardrails = (REPO / "guardrails" / "GUARDRAILS.md").read_text(encoding="utf-8")
    for code, agent in state.agents.items():
        soul = render_soul(state, agent, guardrails)
        # Hermes memotong context file di 20.000 karakter, dan yang hilang
        # justru bagian bawah — tempat SOP berada.
        assert len(soul) < 20_000, f"{code}: SOUL.md {len(soul)} karakter"


# --------------------------------------------------------------- config.yaml


def test_kunci_milik_hermes_dipertahankan(state, policies, settings):
    existing = {
        "display": {"theme": "dark"},
        "model": {"provider": "lama", "default": "lama", "api_mode": "chat_completions"},
        "gateway": {"multiplex_profiles": False},
    }
    config = render_config(existing, state.agents["legal"], policies["legal"], settings)

    assert config["display"] == {"theme": "dark"}
    assert config["gateway"] == {"multiplex_profiles": False}
    # kunci terkelola diperbarui, kunci tetangga di dalamnya tidak dibuang
    assert config["model"]["provider"] == state.agents["legal"].provider
    assert config["model"]["api_mode"] == "chat_completions"


def test_perintah_paksa_membawa_departemen_lewat_env(state, policies, settings):
    # Mode ini dipakai saat uji di Windows: peluncur .sh dilewati, jadi
    # identitas departemen harus ikut lewat env agar batas wewenang tetap ada.
    dipaksa = replace(settings, mcp_command="C:/x/alta-mcp.exe", mcp_command_explicit=True)

    orch = render_config({}, state.agents["orchestrator"], policies["orchestrator"], dipaksa)
    rec = render_config({}, state.agents["recruitment"], policies["recruitment"], dipaksa)

    assert orch["mcp_servers"]["alta"]["env"] == {
        "ALTA_AGENT": "orchestrator",
        "ALTA_DATABASE_URL": "${ALTA_DATABASE_URL}",
        "ALTA_READ_ONLY": "true",
    }
    assert rec["mcp_servers"]["alta"]["env"] == {
        "ALTA_AGENT": "recruitment",
        "ALTA_DATABASE_URL": "${ALTA_DATABASE_URL}",
    }
    assert rec["mcp_servers"]["alta"]["command"] == "C:/x/alta-mcp.exe"
    # Placeholder, bukan nilainya: password tetap tidak masuk config.yaml.
    assert "postgres" not in dump_config(rec)


def test_password_database_tidak_pernah_masuk_config(state, policies, settings):
    config = render_config({}, state.agents["finance"], policies["finance"], settings)
    dumped = dump_config(config)
    assert "ALTA_DATABASE_URL" not in dumped
    assert "postgres" not in dumped
    # Peluncurlah yang membaca .env profile, bukan config.yaml.
    assert config["mcp_servers"]["alta"]["command"].endswith("mcp-launch.sh")


def test_peluncur_membaca_env_profile_dan_menyetel_departemen(state, policies, settings):
    script = render_mcp_launcher(state.agents["finance"], policies["finance"], settings)
    assert 'ALTA_AGENT=finance' in script
    assert '. "$PROFILE_DIR/.env"' in script
    assert "ALTA_READ_ONLY" not in script
    # Sembilan proses MCP berbagi satu Postgres; bawaan 8 melewati max_connections.
    assert "ALTA_POOL_MAX" in script


def test_peluncur_orchestrator_baca_saja(state, policies, settings):
    script = render_mcp_launcher(
        state.agents["orchestrator"], policies["orchestrator"], settings
    )
    assert "export ALTA_READ_ONLY=true" in script


def test_perintah_mcp_bawaan_bukan_uv_run(settings):
    # `uv run` menyelaraskan ulang venv tiap start dan pernah menaikkan `mcp`
    # ke versi mayor yang mematikan server. Lihat _default_mcp_command().
    assert "uv" not in Path(settings.mcp_command).name
    assert settings.mcp_command.endswith(".venv/bin/alta-mcp")


def test_toolset_dipersempit_ke_daftar_departemen(state, policies, settings):
    config = render_config({}, state.agents["marketing"], policies["marketing"], settings)
    assert config["toolsets"] == ["alta-marketing"]
    assert "terminal" not in config["custom_toolsets"]["alta-marketing"]


def test_hanya_it_yang_mendapat_penyaring_terminal(state, policies, settings):
    it_config = render_config({}, state.agents["it"], policies["it"], settings)
    cs_config = render_config(
        {}, state.agents["customer_service"], policies["customer_service"], settings
    )
    it_hooks = " ".join(h["command"] for h in it_config["hooks"]["pre_tool_call"])
    cs_hooks = " ".join(h["command"] for h in cs_config["hooks"]["pre_tool_call"])

    assert "guard_terminal.py" in it_hooks
    assert "guard_terminal.py" not in cs_hooks
    # penyaring rahasia berlaku di mana pun
    assert "deny_secrets.py" in it_hooks and "deny_secrets.py" in cs_hooks


def test_jalur_selalu_bergaya_posix_dan_dikutip(state, policies, settings):
    # Render boleh dijalankan dari Windows; yang membacanya selalu Linux.
    config = render_config({}, state.agents["it"], policies["it"], settings)
    assert "\\" not in " ".join(config["mcp_servers"]["alta"]["args"])
    for hook in config["hooks"]["pre_tool_call"]:
        assert "\\" not in hook["command"]
        # shlex.split tanpa shell: jalur bisa memuat spasi, jadi harus dikutip
        assert hook["command"].startswith('python3 "') and hook["command"].endswith('"')


def test_config_yang_dirender_tetap_yaml_sah(state, policies, settings):
    text = dump_config(render_config({}, state.agents["it"], policies["it"], settings))
    assert yaml.safe_load(text)["toolsets"] == ["alta-it"]


# ------------------------------------------------------------------ cron.sh


def test_cron_idempoten_dan_aman_dikutip(state):
    jobs = state.schedules_for("customer_service")
    script = render_cron(state.agents["customer_service"], jobs)
    assert script.startswith("#!/usr/bin/env bash")
    for job in jobs:
        assert f"cron remove '{job.name}'" in script
        assert f"--name '{job.name}'" in script


def test_target_pengiriman_diterjemahkan_ke_kosakata_hermes(state):
    # Hermes tidak mengenal "telegram:founder" — chat id founder ada di
    # TELEGRAM_HOME_CHANNEL pada .env, bukan di database.
    assert deliver_target("telegram:founder") == "telegram"
    # "none" harus jadi "local"; default Hermes adalah "origin", dan job
    # departemen tidak punya percakapan asal.
    assert deliver_target("none") == "local"
    assert deliver_target(None) == "local"
    assert deliver_target("telegram:-1001234") == "telegram:-1001234"

    briefing = next(s for s in state.schedules_for("orchestrator") if s.name == "briefing-pagi")
    script = render_cron(state.agents["orchestrator"], [briefing])
    assert "--deliver 'telegram'" in script
    assert "telegram:founder" not in script


def test_kutipan_tunggal_dalam_prompt_tidak_memecah_skrip():
    from alta_hermes.models import Schedule

    job = Schedule(
        agent_code="it",
        name="uji",
        schedule="*/5 * * * *",
        prompt="jangan jalankan 'rm -rf' apa pun",
    )
    script = render_cron(Agent(code="it", profile_name="alta-it"), [job])
    assert "'jangan jalankan '\\''rm -rf'\\'' apa pun'" in script


# ------------------------------------------------------------------ invarian


def test_hanya_orchestrator_yang_mengirim_ke_founder(state):
    pelanggar = [
        s.key for s in state.schedules
        if s.deliver_to == "telegram:founder" and s.agent_code != "orchestrator"
    ]
    assert not pelanggar, f"satu pintu bocor: {pelanggar}"


def test_hanya_it_yang_punya_terminal(policies):
    for code, policy in policies.items():
        if code == "it":
            continue
        assert "terminal" not in policy["toolsets"], f"{code} punya terminal"


def test_setiap_departemen_punya_jadwal_pengambil_task(state):
    for code in state.agents:
        if code == "orchestrator":
            continue
        names = {s.name for s in state.schedules_for(code)}
        assert "ambil-task" in names, f"{code} tidak pernah membaca antreannya"
