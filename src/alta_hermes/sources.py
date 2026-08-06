"""Membaca desired state dari berkas repo.

Repo adalah tempat teks arahan ditulis, ditelaah, dan di-review lewat git.
Database adalah tempat founder menyetelnya kemudian. `sync` memindahkan yang
pertama ke yang kedua; `render` normalnya membaca dari database, tapi bisa
membaca langsung dari berkas (`--from files`) — itulah yang membuat repo ini
bisa diuji sebelum ada Postgres sama sekali.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .models import AGENT_CODES, SECTIONS, Agent, DesiredState, Directive, Schedule

# "## persona", "## policy: Ambang eskalasi", "## sop: Briefing pagi"
_HEADING = re.compile(r"^##\s+(persona|policy|sop)\s*(?::\s*(.+?))?\s*$", re.IGNORECASE)


class SourceError(RuntimeError):
    """Berkas sumber tidak bisa dibaca sebagaimana mestinya."""


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SourceError(f"berkas tidak ditemukan: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SourceError(f"{path.name} harus berupa pemetaan di tingkat atas")
    return data


def parse_directives(text: str, agent_code: str, *, origin: str = "") -> list[Directive]:
    """Pecah satu berkas directive menjadi baris-baris `agent_directives`.

    Apa pun sebelum heading `##` pertama diabaikan — di situ tempat judul
    dokumen dan catatan untuk pembaca manusia, bukan untuk model.
    """
    rows: list[Directive] = []
    section: str | None = None
    title: str | None = None
    buffer: list[str] = []
    counters = dict.fromkeys(SECTIONS, 0)

    def flush() -> None:
        if section is None:
            return
        content = "\n".join(buffer).strip()
        if not content:
            raise SourceError(
                f"{origin or agent_code}: bagian '{section}"
                f"{': ' + title if title else ''}' kosong — DB menolak konten kosong"
            )
        counters[section] += 10
        rows.append(
            Directive(
                agent_code=agent_code,
                section=section,
                title=title,
                content=content,
                position=counters[section],
            )
        )

    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            flush()
            section = match.group(1).lower()
            title = (match.group(2) or "").strip() or None
            buffer = []
            if section == "persona" and title:
                raise SourceError(
                    f"{origin or agent_code}: persona tidak boleh berjudul — "
                    "database hanya mengizinkan satu persona aktif per departemen"
                )
            continue
        if section is not None:
            buffer.append(line)
    flush()

    personas = [r for r in rows if r.section == "persona"]
    if len(personas) > 1:
        raise SourceError(f"{origin or agent_code}: ada {len(personas)} persona, harus tepat satu")
    return rows


def load_from_files(repo_root: Path, *, profile_prefix: str = "alta-") -> DesiredState:
    agents_raw = load_yaml(repo_root / "agents.yaml")
    schedules_raw = load_yaml(repo_root / "schedules.yaml")
    directives_dir = repo_root / "directives"

    agents: dict[str, Agent] = {}
    directives: list[Directive] = []
    schedules: list[Schedule] = []

    unknown = set(agents_raw) - set(AGENT_CODES)
    if unknown:
        raise SourceError(
            f"agents.yaml memuat kode departemen yang tidak dikenal: {sorted(unknown)}"
        )

    for code in AGENT_CODES:
        entry = agents_raw.get(code)
        if entry is None:
            raise SourceError(f"agents.yaml belum memuat departemen '{code}'")
        agents[code] = Agent(
            code=code,
            profile_name=entry.get("profile_name") or f"{profile_prefix}{code}",
            provider=entry.get("provider"),
            model=entry.get("model"),
            subagent_model=entry.get("subagent_model"),
        )

        path = directives_dir / f"{code}.md"
        if not path.is_file():
            raise SourceError(f"directive belum ada untuk departemen '{code}': {path}")
        directives.extend(
            parse_directives(path.read_text(encoding="utf-8"), code, origin=path.name)
        )

    for code, jobs in schedules_raw.items():
        if code not in AGENT_CODES:
            raise SourceError(f"schedules.yaml memuat departemen tak dikenal: {code}")
        for job in jobs or []:
            missing = {"name", "schedule", "prompt"} - set(job)
            if missing:
                raise SourceError(
                    f"schedules.yaml [{code}]: jadwal kehilangan kunci {sorted(missing)}"
                )
            schedules.append(
                Schedule(
                    agent_code=code,
                    name=job["name"],
                    schedule=str(job["schedule"]),
                    prompt=" ".join(str(job["prompt"]).split()),
                    job_kind=job.get("job_kind", "agent"),
                    skills=tuple(job.get("skills") or ()),
                    provider=job.get("provider"),
                    model=job.get("model"),
                    deliver_to=job.get("deliver_to"),
                    is_active=bool(job.get("is_active", True)),
                )
            )

    return DesiredState(agents=agents, directives=directives, schedules=schedules, source="files")


def load_policy(path: Path) -> dict[str, Any]:
    """Baca guardrails/profiles.yaml dan sebarkan default ke tiap departemen."""
    raw = load_yaml(path)
    defaults = raw.get("defaults") or {}
    agents_raw = raw.get("agents") or {}

    resolved: dict[str, dict[str, Any]] = {}
    for code in AGENT_CODES:
        entry = dict(agents_raw.get(code) or {})
        merged = {
            "toolsets": list(entry.get("toolsets") or defaults.get("toolsets") or []),
            "platforms": list(entry.get("platforms") or defaults.get("platforms") or []),
            "disabled_toolsets": list(
                entry.get("disabled_toolsets") or defaults.get("disabled_toolsets") or []
            ),
            "read_only": bool(entry.get("read_only", defaults.get("read_only", False))),
        }
        if not merged["toolsets"]:
            raise SourceError(f"profiles.yaml: departemen '{code}' tidak punya toolset sama sekali")
        resolved[code] = merged
    return resolved
