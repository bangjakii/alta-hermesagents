"""Merender desired state menjadi berkas runtime Hermes.

Tiga berkas per departemen:

    SOUL.md      guardrail (dari repo) + persona/policy/sop (dari DB)
    config.yaml  model, provider, MCP server departemen, toolset, hook
    cron.sh      pendaftaran ulang jadwal ke cron Hermes

SOUL.md dan cron.sh ditulis penuh — keduanya memang milik lapisan ini.
config.yaml TIDAK: Hermes sendiri menulis banyak hal ke sana (kredensial hasil
`hermes setup`, preferensi tampilan, hasil `hermes tools`). Jadi ia digabung,
bukan ditimpa: hanya kunci yang memang dikelola boot script yang disentuh.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import Settings
from .models import Agent, DesiredState, Schedule

GENERATED_MARK = "alta-hermes render"


@dataclass
class RenderedFile:
    path: Path
    content: str
    executable: bool = False


# --------------------------------------------------------------------- SOUL.md


def render_soul(state: DesiredState, agent: Agent, guardrails: str) -> str:
    rows = state.directives_for(agent.code)
    persona = [r for r in rows if r.section == "persona"]
    policies = [r for r in rows if r.section == "policy"]
    sops = [r for r in rows if r.section == "sop"]

    body: list[str] = [guardrails.strip(), "", "---", ""]

    if persona:
        body += [persona[0].content.strip(), ""]

    if policies:
        body += ["## Kebijakan Departemen", ""]
        for row in policies:
            if row.title:
                body.append(f"### {row.title}")
            body += [row.content.strip(), ""]

    if sops:
        body += ["## Prosedur Baku", ""]
        for row in sops:
            if row.title:
                body.append(f"### {row.title}")
            body += [row.content.strip(), ""]

    content = "\n".join(body).rstrip() + "\n"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
    header = (
        f"<!-- Dihasilkan {GENERATED_MARK} dari {state.source}. hash:{digest}\n"
        "     JANGAN disunting di sini — suntingan hilang saat render berikutnya.\n"
        "     Persona/kebijakan/SOP diubah lewat Admin Panel (agent_directives)\n"
        "     atau repo alta-hermesagents. Blok guardrail di bawah hanya bisa\n"
        "     diubah lewat repo, dan itu memang disengaja. -->\n\n"
    )
    return header + content


# ------------------------------------------------------------------ config.yaml


def render_config(
    existing: dict[str, Any],
    agent: Agent,
    policy: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    config = dict(existing)
    toolset_name = f"alta-{agent.code.replace('_', '-')}"

    if agent.provider or agent.model:
        model_cfg = dict(config.get("model") or {}) if isinstance(config.get("model"), dict) else {}
        if agent.provider:
            model_cfg["provider"] = agent.provider
        if agent.model:
            model_cfg["default"] = agent.model
        config["model"] = model_cfg

    if agent.subagent_model:
        delegation = dict(config.get("delegation") or {})
        delegation["model"] = agent.subagent_model
        delegation["provider"] = agent.provider
        # Departemen tidak boleh menumbuhkan pohon subagent sendiri: satu
        # tingkat, dan anaknya tidak boleh mendelegasikan lagi.
        delegation["max_spawn_depth"] = 1
        delegation["orchestrator_enabled"] = False
        config["delegation"] = delegation

    servers = dict(config.get("mcp_servers") or {})
    servers["alta"] = _mcp_entry(agent, policy, settings)
    config["mcp_servers"] = servers

    config["toolsets"] = [toolset_name]
    custom = dict(config.get("custom_toolsets") or {})
    custom[toolset_name] = list(policy["toolsets"])
    config["custom_toolsets"] = custom

    agent_cfg = dict(config.get("agent") or {})
    agent_cfg["disabled_toolsets"] = list(policy["disabled_toolsets"])
    config["agent"] = agent_cfg

    config["hooks"] = _hooks(policy, settings)
    # Gateway dan cron berjalan tanpa TTY; tanpa ini hook baru diam-diam tidak
    # terpasang dan guardrail-nya hilang tanpa ada yang tahu.
    config["hooks_auto_accept"] = True

    return config


def render_mcp_launcher(agent: Agent, policy: dict[str, Any], settings: Settings) -> str:
    """Skrip yang menyalakan proses MCP departemen ini.

    Ada karena `${ALTA_DATABASE_URL}` di `config.yaml` tidak bisa diandalkan:
    pada uji 6 Agustus 2026, Hermes tidak mengekspor `.env` profile ke
    substitusi itu, sehingga server MCP menerima placeholder mentah lalu mati.
    Menuliskan URL-nya langsung ke `config.yaml` bukan pilihan — di dalamnya ada
    password database.

    Peluncur ini membaca `.env` milik profile-nya sendiri, jadi rahasianya tetap
    di satu tempat (`.env`, chmod 600) dan tidak pernah masuk berkas yang
    di-render atau di-commit.
    """
    target = settings.mcp_command
    if settings.backend_dir and Path(target).name.startswith("uv"):
        target = f'{target} --directory "{settings.backend_dir.as_posix()}" ' + " ".join(
            settings.mcp_args
        )
    elif settings.mcp_args:
        target = target + " " + " ".join(settings.mcp_args)
    else:
        target = f'"{target}"'

    read_only = 'export ALTA_READ_ONLY=true\n' if policy["read_only"] else ""
    return f"""#!/usr/bin/env bash
# Dihasilkan {GENERATED_MARK} — jangan disunting; jalankan ulang render.
#
# Menyalakan proses MCP departemen {agent.code}. Rahasianya dibaca dari .env
# milik profile ini, bukan dari config.yaml — di config.yaml ia akan ikut
# ter-commit atau terbaca siapa pun yang membuka berkasnya.
set -euo pipefail

PROFILE_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
if [ -f "$PROFILE_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROFILE_DIR/.env"
  set +a
fi

export ALTA_AGENT={agent.code}
{read_only}
# Sembilan proses MCP berbagi satu Postgres. Bawaan ALTA_POOL_MAX=8 dikalikan
# sembilan sudah melewati max_connections bawaan (100) sebelum REST API dihitung.
export ALTA_POOL_MAX="${{ALTA_POOL_MAX:-4}}"

exec {target}
"""


def _mcp_entry(agent: Agent, policy: dict[str, Any], settings: Settings) -> dict[str, Any]:
    if settings.mcp_command_explicit:
        # Operator memaksa perintahnya sendiri (mis. .exe untuk uji di Windows,
        # di mana peluncur .sh tidak bisa dijalankan). Di jalur ini `env` di
        # bawah adalah SATU-SATUNYA lingkungan yang diterima subproses —
        # terbukti 6 Agustus 2026: Hermes tidak mewariskan lingkungan induknya,
        # sehingga tanpa baris ALTA_DATABASE_URL server MCP mati saat start.
        # Nilainya tetap placeholder; Hermes menggantinya dari lingkungannya
        # sendiri, jadi password tidak pernah tertulis di config.yaml.
        command, args = settings.mcp_command, list(settings.mcp_args)
        env = {"ALTA_AGENT": agent.code, "ALTA_DATABASE_URL": "${ALTA_DATABASE_URL}"}
        if policy["read_only"]:
            env["ALTA_READ_ONLY"] = "true"
    else:
        command = (settings.profile_dir(agent.profile_name) / "mcp-launch.sh").as_posix()
        args = []
        env = {}

    return {
        "command": command,
        "args": args,
        "env": env,
        "timeout": 120,
        "tools": {"resources": False, "prompts": False},
    }


def _hooks(policy: dict[str, Any], settings: Settings) -> dict[str, Any]:
    # Hermes memecah perintah hook dengan shlex.split (tanpa shell), jadi jalur
    # yang memuat spasi harus dikutip — dan jalur repo memang bisa memuat spasi.
    def command(script: str) -> str:
        return f'python3 "{(settings.hooks_dir / script).as_posix()}"'

    entries: list[dict[str, Any]] = [{"command": command("deny_secrets.py"), "timeout": 10}]
    if "terminal" in policy["toolsets"]:
        entries.append(
            {
                "matcher": "terminal|process",
                "command": command("guard_terminal.py"),
                "timeout": 10,
            }
        )
    return {"pre_tool_call": entries}


def dump_config(config: dict[str, Any]) -> str:
    header = (
        f"# Sebagian kunci di berkas ini dikelola {GENERATED_MARK}: model, delegation,\n"
        "# mcp_servers.alta, toolsets, custom_toolsets, agent.disabled_toolsets, hooks.\n"
        "# Kunci lain milik Hermes dan dipertahankan apa adanya saat render.\n"
    )
    return header + yaml.safe_dump(config, sort_keys=False, allow_unicode=True, width=100)


# ---------------------------------------------------------------------- cron.sh


def _sh(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def deliver_target(deliver_to: str | None) -> str | None:
    """Terjemahkan kosakata ALTA menjadi target pengiriman yang dikenal Hermes.

    `telegram:founder` adalah cara ALTA menyebutnya di database — terbaca founder,
    dan tidak menaruh chat id siapa pun di sana. Hermes tidak mengenalnya: ia
    hanya menerima `telegram` (memakai TELEGRAM_HOME_CHANNEL) atau
    `telegram:<chat_id>`. Jadi chat id founder tinggal di `.env` profile
    orchestrator sebagai TELEGRAM_HOME_CHANNEL, bukan di database.

    `none` menjadi `local`: hasilnya tersimpan sebagai berkas di
    `<profile>/cron/output/`. Tanpa ini Hermes memakai default `origin`, dan job
    departemen tidak punya percakapan asal — kegagalan yang tidak kelihatan.
    """
    if not deliver_to or deliver_to == "none":
        return "local"
    if deliver_to == "telegram:founder":
        return "telegram"
    return deliver_to


def render_cron(agent: Agent, schedules: list[Schedule]) -> str:
    lines = [
        "#!/usr/bin/env bash",
        f"# Dihasilkan {GENERATED_MARK} — jangan disunting; jalankan ulang render.",
        "#",
        "# Idempoten: tiap job dihapus lebih dulu lalu dibuat lagi, jadi menjalankan",
        "# skrip ini dua kali tidak melahirkan jadwal ganda.",
        "set -euo pipefail",
        "",
        f"PROFILE={_sh(agent.profile_name)}",
        'HERMES=${HERMES_BIN:-hermes}',
        "",
        '# Pinning provider/model hanya dipakai bila CLI mendukungnya. Job cron yang',
        '# tidak dipin akan fail-closed kalau default global berubah — itu perilaku',
        '# Hermes, bukan bug; pin lewat `cronjob action=update` bila flagnya tidak ada.',
        'CRON_HELP="$("$HERMES" -p "$PROFILE" cron create --help 2>&1 || true)"',
        'PIN_SUPPORTED=0',
        'if grep -q -- "--model" <<<"$CRON_HELP"; then PIN_SUPPORTED=1; fi',
        "",
    ]

    if not schedules:
        lines += ['echo "tidak ada jadwal aktif untuk $PROFILE"', ""]
        return "\n".join(lines)

    for job in schedules:
        flags = [f"--name {_sh(job.name)}"]
        for skill in job.skills:
            flags.append(f"--skill {_sh(skill)}")
        flags.append(f"--deliver {_sh(deliver_target(job.deliver_to))}")
        if job.job_kind == "script":
            flags.append("--no-agent")
            flags.append(f"--script {_sh(job.prompt)}")

        positional = _sh(job.schedule) if job.job_kind == "script" else (
            f"{_sh(job.schedule)} {_sh(job.prompt)}"
        )
        pin = ""
        if job.model:
            pin = f" --model {_sh(job.model)}"
            if job.provider:
                pin += f" --provider {_sh(job.provider)}"

        lines += [
            f'echo "-> {job.name}"',
            f'"$HERMES" -p "$PROFILE" cron remove {_sh(job.name)} >/dev/null 2>&1 || true',
        ]
        if pin:
            lines += [
                'if [ "$PIN_SUPPORTED" = "1" ]; then',
                f'  "$HERMES" -p "$PROFILE" cron create {positional} {" ".join(flags)}{pin}',
                "else",
                f'  "$HERMES" -p "$PROFILE" cron create {positional} {" ".join(flags)}',
                f'  echo "   ! model {job.model} belum dipin — pin lewat cronjob action=update" >&2',
                "fi",
            ]
        else:
            lines.append(f'"$HERMES" -p "$PROFILE" cron create {positional} {" ".join(flags)}')
        lines.append("")

    lines.append('echo "selesai: $PROFILE"')
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------- perakitan


def render_profile(
    state: DesiredState,
    agent: Agent,
    policy: dict[str, Any],
    settings: Settings,
    guardrails: str,
) -> list[RenderedFile]:
    profile_dir = settings.profile_dir(agent.profile_name)
    existing_path = profile_dir / "config.yaml"
    existing: dict[str, Any] = {}
    if existing_path.is_file():
        loaded = yaml.safe_load(existing_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            existing = loaded

    files = [
        RenderedFile(profile_dir / "SOUL.md", render_soul(state, agent, guardrails)),
        RenderedFile(
            existing_path, dump_config(render_config(existing, agent, policy, settings))
        ),
        RenderedFile(
            profile_dir / "cron.sh",
            render_cron(agent, state.schedules_for(agent.code)),
            executable=True,
        ),
    ]
    if not settings.mcp_command_explicit:
        files.append(
            RenderedFile(
                profile_dir / "mcp-launch.sh",
                render_mcp_launcher(agent, policy, settings),
                executable=True,
            )
        )
    return files


def apply(files: list[RenderedFile], *, dry_run: bool) -> list[str]:
    report: list[str] = []
    for item in files:
        before = item.path.read_text(encoding="utf-8") if item.path.is_file() else None
        if before == item.content:
            report.append(f"= {item.path}")
            continue
        verb = "+" if before is None else "~"
        report.append(f"{verb} {item.path}")
        if dry_run:
            continue
        item.path.parent.mkdir(parents=True, exist_ok=True)
        item.path.write_text(item.content, encoding="utf-8")
        if item.executable:
            item.path.chmod(0o755)
    return report
