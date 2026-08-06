"""Bentuk data desired state — sengaja sama persis dengan kolom di alta-database.

Kalau bentuk di sini menyimpang dari skema DB, `sync` akan gagal di tengah dan
menyisakan setengah perubahan. Jadi ketika migration menambah kolom, tambahkan
di sini juga sebelum menulis kodenya di tempat lain.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Urutan render di SOUL.md. Identitas lebih dulu, baru aturan, baru prosedur —
# model membaca dari atas, dan yang paling menentukan perilaku harus terbaca
# lebih awal.
SECTIONS: tuple[str, ...] = ("persona", "policy", "sop")

# Kesembilan departemen, urut sesuai daur hidup pekerjaan ALTA.
AGENT_CODES: tuple[str, ...] = (
    "orchestrator",
    "recruitment",
    "verifying_readiness",
    "customer_service",
    "sales",
    "legal",
    "finance",
    "marketing",
    "it",
)


@dataclass(frozen=True)
class Directive:
    """Satu baris `agent_directives`."""

    agent_code: str
    section: str
    content: str
    title: str | None = None
    position: int = 0

    @property
    def key(self) -> tuple[str, str, str]:
        """Identitas untuk pencocokan saat sync. Persona selalu tanpa judul."""
        return (self.agent_code, self.section, self.title or "")


@dataclass(frozen=True)
class Agent:
    """Kolom `agents` yang dipegang lapisan konfigurasi ini."""

    code: str
    profile_name: str
    provider: str | None = None
    model: str | None = None
    subagent_model: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class Schedule:
    """Satu baris `agent_schedules`. Kolom last_* sengaja tidak ada di sini —
    itu diisi eksekutor, dan menariknya ke repo hanya melahirkan data basi."""

    agent_code: str
    name: str
    schedule: str
    prompt: str
    job_kind: str = "agent"
    skills: tuple[str, ...] = ()
    provider: str | None = None
    model: str | None = None
    deliver_to: str | None = None
    is_active: bool = True

    @property
    def key(self) -> tuple[str, str]:
        return (self.agent_code, self.name)


@dataclass(frozen=True)
class DesiredState:
    """Seluruh konfigurasi agent pada satu titik waktu, dari satu sumber."""

    agents: dict[str, Agent]
    directives: list[Directive] = field(default_factory=list)
    schedules: list[Schedule] = field(default_factory=list)
    source: str = "files"

    def directives_for(self, code: str) -> list[Directive]:
        rows = [d for d in self.directives if d.agent_code == code]
        return sorted(rows, key=lambda d: (SECTIONS.index(d.section), d.position, d.title or ""))

    def schedules_for(self, code: str) -> list[Schedule]:
        rows = [s for s in self.schedules if s.agent_code == code and s.is_active]
        return sorted(rows, key=lambda s: s.name)
