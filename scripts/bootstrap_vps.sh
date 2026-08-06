#!/usr/bin/env bash
# =====================================================================
# Menyiapkan seluruh armada Hermes ALTA di VPS — sekali jalan.
# =====================================================================
# Idempoten: aman dijalankan ulang. Profile yang sudah ada tidak dibuat
# ulang, dan render menimpa hanya berkas yang memang dikelola boot script.
#
# Yang TIDAK dilakukan skrip ini, dan memang disengaja:
#   - mengisi kredensial. Token Telegram dan API key provider diambil dari
#     Infisical lalu ditulis ke .env tiap profile oleh operator manusia.
#   - menyalakan gateway departemen. Hanya orchestrator yang punya kanal
#     ke manusia; delapan lainnya dijalankan cron.
# =====================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES="${HERMES_BIN:-hermes}"

cd "$REPO_DIR"

if [ ! -f .env ]; then
  echo "!! .env belum ada. Salin .env.example lalu isi ALTA_DATABASE_URL." >&2
  exit 1
fi

echo "== 1/6 memasang alta-hermes"
python3 -m pip install --quiet -e .

echo "== 2/6 memeriksa konfigurasi"
alta-hermes doctor || echo "   (doctor menemukan masalah — lanjut, tapi baca di atas)"

echo "== 3/6 membuat profile Hermes yang belum ada"
mapfile -t PROFILES < <(python3 - <<'PY'
import yaml, pathlib
data = yaml.safe_load(pathlib.Path("agents.yaml").read_text(encoding="utf-8"))
for code, entry in data.items():
    print(f"{code}\t{entry['profile_name']}")
PY
)

EXISTING="$("$HERMES" profile list 2>/dev/null || true)"
for row in "${PROFILES[@]}"; do
  code="${row%%$'\t'*}"
  name="${row##*$'\t'}"
  if grep -qw "$name" <<<"$EXISTING"; then
    echo "   = $name sudah ada"
  else
    echo "   + $name"
    "$HERMES" profile create "$name" --description "ALTA departemen $code"
  fi
done

echo "== 4/6 merender SOUL.md, config.yaml, cron.sh"
# Sebelum database terisi, jalankan dengan --from files.
alta-hermes render --from "${ALTA_RENDER_SOURCE:-database}"

echo "== 5/6 mendaftarkan jadwal ke cron Hermes"
PROFILES_ROOT="$(python3 -c 'from alta_hermes.config import Settings; print(Settings.from_env().profiles_root)')"
for row in "${PROFILES[@]}"; do
  name="${row##*$'\t'}"
  script="$PROFILES_ROOT/$name/cron.sh"
  if [ -x "$script" ]; then
    HERMES_BIN="$HERMES" "$script"
  fi
done

echo "== 6/6 gateway orchestrator"
ORCH="$(printf '%s\n' "${PROFILES[@]}" | awk -F'\t' '$1=="orchestrator"{print $2}')"
cat <<EOF

Selesai. Yang masih harus dikerjakan manusia:

  1. Isi kredensial tiap profile dari Infisical:
       $PROFILES_ROOT/<profile>/.env
     Minimal: ALTA_DATABASE_URL (semua profile), kunci provider LLM,
     dan TELEGRAM_BOT_TOKEN + TELEGRAM_FOUNDER_CHAT_ID (hanya $ORCH).

  2. Pastikan zona waktu server sudah benar, kalau tidak briefing pagi
     tiba tengah malam:
       timedatectl set-timezone Asia/Jakarta

  3. Nyalakan gateway orchestrator — HANYA dia yang punya kanal ke manusia:
       $HERMES -p $ORCH gateway install
       $HERMES -p $ORCH gateway start

  4. Periksa MCP tiap profile benar-benar tersambung dan melihat tool yang
     benar. Ini pemeriksaan terpenting: kalau jumlah tool-nya tidak sesuai
     remit departemen, batas wewenangnya sedang tidak berlaku.
       $HERMES -p <profile> mcp test alta

     Jumlah yang diharapkan (dengan agent_tool_permissions terpasang):
       orchestrator 126 (baca-saja)   verifying_readiness 43   recruitment 43
       legal 40   sales 23   customer_service 21   marketing 19
       finance 18   it 18
EOF
