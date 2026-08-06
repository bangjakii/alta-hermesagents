#!/usr/bin/env bash
# Menerapkan perubahan konfigurasi agent: repo -> database -> profile Hermes.
#
# Ini urutan yang benar dan bukan sekadar kebiasaan. Database adalah sumber
# kebenaran; kalau render dijalankan sebelum sync, profile akan memakai versi
# lama dan perubahan repo tampak "tidak berpengaruh".
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES="${HERMES_BIN:-hermes}"
cd "$REPO_DIR"

REASON="${1:-penerapan konfigurasi agent dari repo alta-hermesagents}"

echo "== selisih repo vs database"
alta-hermes sync --dry-run

read -r -p "Terapkan ke database? [y/N] " answer
[ "$answer" = "y" ] || { echo "dibatalkan"; exit 0; }

alta-hermes sync --reason "$REASON"
alta-hermes render --from database

PROFILES_ROOT="$(python3 -c 'from alta_hermes.config import Settings; print(Settings.from_env().profiles_root)')"
for script in "$PROFILES_ROOT"/*/cron.sh; do
  [ -x "$script" ] && HERMES_BIN="$HERMES" "$script"
done

echo
echo "SOUL.md baru berlaku pada SESI BARU. Restart gateway orchestrator bila"
echo "perubahannya menyentuh persona atau kebijakannya:"
echo "  $HERMES -p alta-orchestrator gateway restart"
