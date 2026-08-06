"""Akses ke alta-database untuk membaca dan menyetel desired state agent.

Boot script menulis langsung ke tabel, tidak lewat MCP Server — MCP melayani
agent, ini perkakas founder. Karena itu konteks aktor disetel eksplisit sebagai
`human`/`founder` dengan alasan yang wajib: perubahan konfigurasi agent harus
bisa dibedakan dari perubahan yang dilakukan agent sendiri, dan jejak audit yang
mengecualikan pemiliknya bukan jejak audit.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from .models import AGENT_CODES, Agent, DesiredState, Directive, Schedule


@contextmanager
def connect(database_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        conn.execute("SET search_path TO alta, public")
        yield conn


def _set_actor(conn: psycopg.Connection, reason: str) -> None:
    """Konteks aktor untuk satu transaksi. set_config() dipakai karena SET tidak
    menerima parameter — dan alasan tidak boleh dirangkai ke dalam SQL."""
    conn.execute("SELECT set_config('alta.actor_type', 'human', true)")
    conn.execute("SELECT set_config('alta.actor_id', 'founder', true)")
    conn.execute("SELECT set_config('alta.reason', %s, true)", (reason,))


def load_from_db(conn: psycopg.Connection, *, profile_prefix: str = "alta-") -> DesiredState:
    agents: dict[str, Agent] = {}
    rows = conn.execute(
        """
        SELECT code::text, name, profile_name, provider, model, subagent_model
          FROM agents
         WHERE is_active
        """
    ).fetchall()
    for row in rows:
        code = row["code"]
        if code not in AGENT_CODES:
            continue
        agents[code] = Agent(
            code=code,
            name=row["name"],
            profile_name=row["profile_name"] or f"{profile_prefix}{code}",
            provider=row["provider"],
            model=row["model"],
            subagent_model=row["subagent_model"],
        )

    directives = [
        Directive(
            agent_code=row["agent_code"],
            section=row["section"],
            title=row["title"],
            content=row["content"],
            position=row["position"],
        )
        for row in conn.execute(
            """
            SELECT agent_code::text, section::text, title, content, position
              FROM agent_directives
             WHERE is_active AND deleted_at IS NULL
             ORDER BY agent_code, section, position
            """
        ).fetchall()
    ]

    schedules = [
        Schedule(
            agent_code=row["agent_code"],
            name=row["name"],
            schedule=row["schedule"],
            prompt=row["prompt"],
            job_kind=row["job_kind"],
            skills=tuple(row["skills"] or ()),
            provider=row["provider"],
            model=row["model"],
            deliver_to=row["deliver_to"],
            is_active=row["is_active"],
        )
        for row in conn.execute(
            """
            SELECT agent_code::text, name, job_kind::text, schedule, prompt, skills,
                   provider, model, deliver_to, is_active
              FROM agent_schedules
             WHERE is_active AND deleted_at IS NULL
             ORDER BY agent_code, name
            """
        ).fetchall()
    ]

    return DesiredState(
        agents=agents, directives=directives, schedules=schedules, source="database"
    )


def sync(conn: psycopg.Connection, state: DesiredState, *, reason: str) -> list[str]:
    """Dorong desired state dari repo ke database. Kembalikan daftar perubahan.

    Yang hilang dari repo dinonaktifkan (`is_active = false`), tidak dihapus —
    sama seperti aturan seluruh basis data ini: baris tidak pernah lenyap,
    supaya jejak audit tetap utuh dan rollback mungkin dilakukan.
    """
    changes: list[str] = []
    with conn.transaction():
        _set_actor(conn, reason)
        changes += _sync_agents(conn, state)
        changes += _sync_directives(conn, state)
        changes += _sync_schedules(conn, state)
    return changes


def _sync_agents(conn: psycopg.Connection, state: DesiredState) -> list[str]:
    changes: list[str] = []
    current = {
        row["code"]: row
        for row in conn.execute(
            "SELECT code::text, profile_name, provider, model, subagent_model FROM agents"
        ).fetchall()
    }
    for code, agent in state.agents.items():
        row = current.get(code)
        if row is None:
            changes.append(f"! agents: '{code}' belum ada di DB — jalankan seed 001 lebih dulu")
            continue
        wanted = (agent.profile_name, agent.provider, agent.model, agent.subagent_model)
        have = (row["profile_name"], row["provider"], row["model"], row["subagent_model"])
        if wanted == have:
            continue
        conn.execute(
            """
            UPDATE agents
               SET profile_name = %s, provider = %s, model = %s, subagent_model = %s
             WHERE code = %s::agent_code
            """,
            (*wanted, code),
        )
        changes.append(f"~ agents[{code}]: model/profile diperbarui")
    return changes


def _sync_directives(conn: psycopg.Connection, state: DesiredState) -> list[str]:
    changes: list[str] = []
    current = {
        (row["agent_code"], row["section"], row["title"] or ""): row
        for row in conn.execute(
            """
            SELECT id, agent_code::text, section::text, title, content, position, version
              FROM agent_directives
             WHERE is_active AND deleted_at IS NULL
            """
        ).fetchall()
    }

    seen: set[tuple[str, str, str]] = set()
    for directive in state.directives:
        seen.add(directive.key)
        row = current.get(directive.key)
        label = f"{directive.agent_code}/{directive.section}" + (
            f": {directive.title}" if directive.title else ""
        )
        if row is None:
            conn.execute(
                """
                INSERT INTO agent_directives
                       (agent_code, section, title, content, position)
                VALUES (%s::agent_code, %s::directive_section, %s, %s, %s)
                """,
                (
                    directive.agent_code,
                    directive.section,
                    directive.title,
                    directive.content,
                    directive.position,
                ),
            )
            changes.append(f"+ directive {label}")
        elif row["content"] != directive.content or row["position"] != directive.position:
            conn.execute(
                """
                UPDATE agent_directives
                   SET content = %s, position = %s, version = version + 1
                 WHERE id = %s
                """,
                (directive.content, directive.position, row["id"]),
            )
            changes.append(f"~ directive {label} (versi {row['version'] + 1})")

    for key, row in current.items():
        if key in seen:
            continue
        conn.execute("UPDATE agent_directives SET is_active = false WHERE id = %s", (row["id"],))
        changes.append(f"- directive {key[0]}/{key[1]}: {key[2] or '(tanpa judul)'} dinonaktifkan")
    return changes


def _sync_schedules(conn: psycopg.Connection, state: DesiredState) -> list[str]:
    changes: list[str] = []
    current = {
        (row["agent_code"], row["name"]): row
        for row in conn.execute(
            """
            SELECT id, agent_code::text, name, job_kind::text, schedule, prompt, skills,
                   provider, model, deliver_to, is_active
              FROM agent_schedules
             WHERE deleted_at IS NULL
            """
        ).fetchall()
    }

    seen: set[tuple[str, str]] = set()
    for job in state.schedules:
        seen.add(job.key)
        row = current.get(job.key)
        label = f"{job.agent_code}/{job.name}"
        payload = (
            job.job_kind,
            job.schedule,
            job.prompt,
            list(job.skills),
            job.provider,
            job.model,
            job.deliver_to,
            job.is_active,
        )
        if row is None:
            conn.execute(
                """
                INSERT INTO agent_schedules
                       (agent_code, name, job_kind, schedule, prompt, skills,
                        provider, model, deliver_to, is_active)
                VALUES (%s::agent_code, %s, %s::schedule_job_kind, %s, %s, %s, %s, %s, %s, %s)
                """,
                (job.agent_code, job.name, *payload),
            )
            changes.append(f"+ schedule {label}")
            continue

        have = (
            row["job_kind"],
            row["schedule"],
            row["prompt"],
            list(row["skills"] or ()),
            row["provider"],
            row["model"],
            row["deliver_to"],
            row["is_active"],
        )
        if have != payload:
            conn.execute(
                """
                UPDATE agent_schedules
                   SET job_kind = %s::schedule_job_kind, schedule = %s, prompt = %s,
                       skills = %s, provider = %s, model = %s, deliver_to = %s, is_active = %s
                 WHERE id = %s
                """,
                (*payload, row["id"]),
            )
            changes.append(f"~ schedule {label}")

    for key, row in current.items():
        if key in seen or not row["is_active"]:
            continue
        conn.execute("UPDATE agent_schedules SET is_active = false WHERE id = %s", (row["id"],))
        changes.append(f"- schedule {key[0]}/{key[1]} dinonaktifkan")
    return changes
