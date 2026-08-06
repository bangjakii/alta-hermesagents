#!/usr/bin/env bash
# Kendali gateway armada ALTA.
#
# Catatan penting: hanya orchestrator yang MEMILIKI gateway. Delapan
# departemen lain sengaja tidak punya kanal masuk — mereka dibangunkan cron
# dan berbicara lewat tabel `tasks`. Kalau suatu hari ada departemen yang
# punya gateway, aturan satu pintu sudah bocor; perbaiki itu, jangan
# menambahkan namanya ke sini.
set -euo pipefail

HERMES="${HERMES_BIN:-hermes}"
ORCHESTRATOR="${ALTA_ORCHESTRATOR_PROFILE:-alta-orchestrator}"

usage() {
  cat <<EOF
Pemakaian: $(basename "$0") {start|stop|restart|status|logs|cron}

  start|stop|restart  gateway orchestrator
  status              status gateway + ringkasan cron tiap profile
  logs                ikuti log gateway orchestrator
  cron                daftar job cron seluruh profile
EOF
}

profiles() {
  "$HERMES" profile list 2>/dev/null | awk '/alta-/ {print $1}'
}

case "${1:-}" in
  start|stop|restart)
    "$HERMES" -p "$ORCHESTRATOR" gateway "$1"
    ;;
  status)
    "$HERMES" -p "$ORCHESTRATOR" gateway status || true
    echo
    for p in $(profiles); do
      printf '%-24s ' "$p"
      "$HERMES" -p "$p" cron list 2>/dev/null | grep -c . || echo 0
    done
    ;;
  logs)
    "$HERMES" -p "$ORCHESTRATOR" logs -f
    ;;
  cron)
    for p in $(profiles); do
      echo "== $p"
      "$HERMES" -p "$p" cron list || true
      echo
    done
    ;;
  *)
    usage
    exit 2
    ;;
esac
