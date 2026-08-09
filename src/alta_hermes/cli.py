"""Antarmuka baris perintah: alta-hermes {render, sync, doctor, show}."""

from __future__ import annotations

import argparse
import sys

from .config import ConfigError, Settings
from .models import AGENT_CODES, DesiredState
from .render import apply, render_profile, render_soul
from .sources import SourceError, load_from_files, load_policy

# Batas aman SOUL.md. Hermes memotong context file di 20.000 karakter; kalau
# terpotong, yang hilang justru bagian bawah — SOP. Diberi jarak supaya tidak
# ada departemen yang diam-diam kehilangan prosedurnya.
SOUL_WARN_CHARS = 18_000


def _load_state(settings: Settings, source: str) -> DesiredState:
    if source == "files":
        return load_from_files(settings.repo_root, profile_prefix=settings.profile_prefix)

    from . import db  # impor tertunda: `--from files` tidak butuh psycopg

    with db.connect(settings.require_database()) as conn:
        return db.load_from_db(conn, profile_prefix=settings.profile_prefix)


def cmd_render(args: argparse.Namespace, settings: Settings) -> int:
    state = _load_state(settings, args.source)
    policies = load_policy(settings.profiles_policy_file)
    guardrails = settings.guardrails_file.read_text(encoding="utf-8")

    codes = [args.agent] if args.agent else list(AGENT_CODES)
    report: list[str] = []
    for code in codes:
        agent = state.agents.get(code)
        if agent is None:
            print(f"! departemen '{code}' tidak ada di sumber {state.source}", file=sys.stderr)
            return 1
        files = render_profile(state, agent, policies[code], settings, guardrails)
        report += apply(files, dry_run=args.dry_run)

    print(f"sumber: {state.source}   akar profile: {settings.profiles_root}")
    print("\n".join(report))
    changed = sum(1 for line in report if not line.startswith("="))
    if args.dry_run:
        print(f"\n[uji coba] {changed} berkas akan berubah — tidak ada yang ditulis")
    else:
        print(f"\n{changed} berkas ditulis")
        print("Berikutnya: jalankan cron.sh tiap profile, lalu restart gateway orchestrator.")
    return 0


def cmd_sync(args: argparse.Namespace, settings: Settings) -> int:
    from . import db

    state = load_from_files(settings.repo_root, profile_prefix=settings.profile_prefix)
    with db.connect(settings.require_database()) as conn:
        if args.dry_run:
            current = db.load_from_db(conn, profile_prefix=settings.profile_prefix)
            diff = _diff(state, current)
            print("\n".join(diff) if diff else "database sudah sesuai repo")
            return 0
        changes = db.sync(conn, state, reason=args.reason)

    print("\n".join(changes) if changes else "database sudah sesuai repo")
    if changes:
        print(f"\n{len(changes)} perubahan tercatat di audit_log sebagai human/founder.")
        print("Jalankan `alta-hermes render` supaya profile Hermes ikut menyusul.")
    return 0


def cmd_secrets(args: argparse.Namespace, settings: Settings) -> int:
    import os

    from .secrets import distribute

    state = _load_state(settings, args.source)
    plans = distribute(state, settings, dict(os.environ), dry_run=args.dry_run)

    kurang = 0
    for plan in plans:
        tanda = "?" if args.dry_run else "+"
        # Nama kunci, tidak pernah nilainya.
        print(f"{tanda} {plan.profile_name:20} {', '.join(plan.keys)}")
        if plan.missing:
            kurang += len(plan.missing)
            print(f"  ! belum terisi di .env repo: {', '.join(plan.missing)}")

    print()
    if args.dry_run:
        print(f"[uji coba] {len(plans)} berkas .env akan ditulis — tidak ada yang disentuh")
    else:
        print(f"{len(plans)} berkas .env ditulis (mode 600).")
    if kurang:
        print(
            f"{kurang} nilai masih kosong. Isi di {settings.repo_root / '.env'} lalu "
            "jalankan lagi — profile yang kuncinya kosong tidak akan bisa memanggil model."
        )
    return 0


def cmd_doctor(args: argparse.Namespace, settings: Settings) -> int:
    problems: list[str] = []
    notes: list[str] = []

    try:
        state = load_from_files(settings.repo_root, profile_prefix=settings.profile_prefix)
    except SourceError as exc:
        print(f"GAGAL membaca sumber repo: {exc}", file=sys.stderr)
        return 1

    policies = load_policy(settings.profiles_policy_file)
    guardrails = settings.guardrails_file.read_text(encoding="utf-8")

    for name in ("deny_secrets.py", "guard_terminal.py"):
        if not (settings.hooks_dir / name).is_file():
            problems.append(f"hook hilang: guardrails/hooks/{name}")

    for code in AGENT_CODES:
        agent = state.agents[code]
        soul = render_soul(state, agent, guardrails)
        if len(soul) > SOUL_WARN_CHARS:
            problems.append(
                f"{code}: SOUL.md {len(soul)} karakter, melewati ambang {SOUL_WARN_CHARS} — "
                "SOP di bagian bawah berisiko terpotong"
            )
        if not any(d.section == "sop" for d in state.directives_for(code)):
            notes.append(f"{code}: belum punya SOP sama sekali")
        if not agent.model or not agent.provider:
            problems.append(f"{code}: provider/model belum ditetapkan di agents.yaml")
        if "terminal" in policies[code]["toolsets"] and code != "it":
            problems.append(f"{code}: punya toolset terminal — hanya IT yang boleh")

    if any(s.deliver_to == "telegram:founder" for s in state.schedules if s.agent_code != "orchestrator"):
        problems.append(
            "ada departemen non-orchestrator yang mengirim ke telegram:founder — "
            "melanggar aturan satu pintu"
        )

    if settings.database_url:
        try:
            from . import db

            with db.connect(settings.database_url) as conn:
                current = db.load_from_db(conn, profile_prefix=settings.profile_prefix)
            drift = _diff(state, current)
            notes += drift or ["database sesuai repo"]
        except Exception as exc:  # noqa: BLE001 — doctor melaporkan, bukan menggagalkan
            notes.append(f"database tidak bisa dihubungi: {exc}")
    else:
        notes.append("ALTA_DATABASE_URL kosong — pemeriksaan hanya dilakukan atas berkas repo")

    notes.append(
        "nama model di agents.yaml belum diverifikasi terhadap katalog provider; "
        "cek dengan `hermes -p <profile> model` sebelum boot pertama"
    )

    for note in notes:
        print(f"catatan: {note}")
    for problem in problems:
        print(f"MASALAH: {problem}", file=sys.stderr)
    print(f"\n{len(problems)} masalah, {len(notes)} catatan")
    return 1 if problems else 0


def cmd_show(args: argparse.Namespace, settings: Settings) -> int:
    state = _load_state(settings, args.source)
    guardrails = settings.guardrails_file.read_text(encoding="utf-8")
    agent = state.agents[args.agent]
    sys.stdout.write(render_soul(state, agent, guardrails))
    return 0


def _diff(repo: DesiredState, database: DesiredState) -> list[str]:
    """Perbedaan repo vs database, dari sudut pandang repo."""
    lines: list[str] = []

    for code, agent in repo.agents.items():
        other = database.agents.get(code)
        if other is None:
            lines.append(f"! agents[{code}] belum ada di database")
        elif (agent.provider, agent.model, agent.subagent_model, agent.profile_name) != (
            other.provider,
            other.model,
            other.subagent_model,
            other.profile_name,
        ):
            lines.append(f"~ agents[{code}] berbeda (model/provider/profile)")

    repo_dir = {d.key: d.content for d in repo.directives}
    db_dir = {d.key: d.content for d in database.directives}
    for key, content in repo_dir.items():
        if key not in db_dir:
            lines.append(f"+ directive {key[0]}/{key[1]}: {key[2] or '(tanpa judul)'}")
        elif db_dir[key] != content:
            lines.append(f"~ directive {key[0]}/{key[1]}: {key[2] or '(tanpa judul)'}")
    for key in db_dir.keys() - repo_dir.keys():
        lines.append(f"- directive {key[0]}/{key[1]}: {key[2] or '(tanpa judul)'} (hanya di DB)")

    repo_sched = {s.key for s in repo.schedules}
    db_sched = {s.key for s in database.schedules}
    for key in sorted(repo_sched - db_sched):
        lines.append(f"+ schedule {key[0]}/{key[1]}")
    for key in sorted(db_sched - repo_sched):
        lines.append(f"- schedule {key[0]}/{key[1]} (hanya di DB)")

    return lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alta-hermes",
        description="Boot script ALTA: desired state di alta-database -> profile Hermes.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    render = sub.add_parser("render", help="tulis SOUL.md, config.yaml, cron.sh tiap profile")
    render.add_argument(
        "--from", dest="source", choices=("database", "files"), default="database",
        help="sumber desired state (default: database)",
    )
    render.add_argument("--agent", choices=AGENT_CODES, help="hanya satu departemen")
    render.add_argument("--dry-run", action="store_true", help="tampilkan tanpa menulis")
    render.set_defaults(func=cmd_render)

    sync = sub.add_parser("sync", help="dorong directive/jadwal/model dari repo ke database")
    sync.add_argument("--dry-run", action="store_true", help="tampilkan selisih saja")
    sync.add_argument(
        "--reason",
        default="sync konfigurasi agent dari repo alta-hermesagents",
        help="alasan yang tersimpan di audit_log",
    )
    sync.set_defaults(func=cmd_sync)

    rahasia = sub.add_parser(
        "secrets",
        help="sebarkan kredensial dari .env repo ke .env tiap profile Hermes",
    )
    rahasia.add_argument(
        "--from", dest="source", choices=("database", "files"), default="files",
        help="sumber daftar departemen & providernya (default: files)",
    )
    rahasia.add_argument("--dry-run", action="store_true", help="tampilkan tanpa menulis")
    rahasia.set_defaults(func=cmd_secrets)

    doctor = sub.add_parser("doctor", help="periksa kesehatan konfigurasi sebelum deploy")
    doctor.set_defaults(func=cmd_doctor)

    show = sub.add_parser("show", help="cetak SOUL.md sebuah departemen ke stdout")
    show.add_argument("agent", choices=AGENT_CODES)
    show.add_argument("--from", dest="source", choices=("database", "files"), default="files")
    show.set_defaults(func=cmd_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    try:
        return int(args.func(args, settings))
    except (ConfigError, SourceError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
