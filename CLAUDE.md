# Konteks Repo — alta-hermesagents

Runtime Hermes untuk sembilan departemen ALTA. Baca `README.md` untuk
arsitekturnya; berkas ini memuat hal yang perlu diketahui **sebelum menyunting**.

## Ruang lingkup

Hanya **ALTA** (PT Alta Teknologi Indonesia). KS / Krakatau Shipyard adalah
perusahaan lain di grup yang sama dengan repo, database, dan armada Hermes
sendiri — jangan menyalin pola dari sana tanpa memeriksa apakah ia masih benar
untuk ALTA.

Keduanya berbagi **satu instalasi Hermes** di mesin ini
(`%LOCALAPPDATA%\hermes`), tetapi profile-nya terpisah: `ks-*` milik KS,
`alta-*` milik ALTA. Satu instalasi memang dirancang menaungi banyak profile,
dan tiap profile punya `.env`, memori, sesi, serta kredensial sendiri. Jangan
menyentuh profile `ks-*` dari sini.

## Tiga repo, tiga tanggung jawab

| Repo | Isi |
|---|---|
| `alta-database` | Skema, migration, MCP Server (tool), REST API, Admin Panel |
| `alta-hermesagents` (di sini) | Boot script, teks arahan, guardrail runtime |
| `alta-landingpage` | Situs publik; memakai router `/public` — jangan ubah endpointnya |

Kalau sebuah perubahan menyentuh **tool** atau **skema**, tempatnya di
`alta-database`, bukan di sini. Repo ini tidak pernah menulis SQL selain lewat
`src/alta_hermes/db.py`.

## Aturan yang tidak boleh dilanggar saat menyunting

1. **Tidak ada rahasia.** Tidak di `.env` yang di-commit, tidak di
   `agents.yaml`, tidak di directive, tidak di contoh. Kredensial hidup di
   Infisical; yang boleh disimpan hanya jalurnya.
2. **Guardrail tetap di repo.** `guardrails/` sengaja tidak ada di database.
   Memindahkan salah satunya ke `agent_directives` berarti ia bisa berubah
   lewat CRUD Admin Panel — itu justru yang dihindari.
3. **Satu pintu.** Hanya profile orchestrator yang punya platform/gateway, dan
   hanya jadwal orchestrator yang boleh `deliver_to: telegram:founder`. Ada uji
   yang menegakkan keduanya; kalau uji itu gagal, jangan dilonggarkan.
4. **Hanya IT yang punya `terminal`.** Juga diuji.
5. **Database adalah sumber kebenaran runtime.** `render` default membaca dari
   database. Jangan mengubah defaultnya menjadi `files` demi kenyamanan —
   setelan founder akan tertimpa.
6. **`config.yaml` digabung, bukan ditimpa.** Kunci milik Hermes harus lolos
   utuh; ada uji untuk itu.

## Cara bekerja di sini

```bash
python -m pip install -e ".[dev]"     # atau: pip install pyyaml pytest
PYTHONPATH=src python -m pytest -q    # 44 uji, cepat, jalankan tiap perubahan
PYTHONPATH=src python -m alta_hermes.cli doctor
PYTHONPATH=src python -m alta_hermes.cli render --from files --dry-run
```

Keadaan mesin pengembangan Windows ini (diperiksa 6 Agustus 2026):

| | |
|---|---|
| Hermes | **ada** — `%LOCALAPPDATA%\hermes`, 7 profile `ks-*` + profile uji `alta-it` |
| `uv` | **ada** — `%LOCALAPPDATA%\hermes\bin\uv.exe` |
| PostgreSQL | **ada, portabel** — 17.4 di port **55432**, basis data `alta_test` |
| Docker / WSL | **tidak ada** |

Postgres-nya biner portabel yang dipasang sesi sebelumnya di bawah
`%TEMP%\claude\…-alta-database\d17b66a9-…\scratchpad\pg`, dengan data di
`…\scratchpad\pgdata`. **Ia ada di direktori sementara** — kalau suatu saat
hilang, itu bukan kerusakan, dan basis datanya dibangun ulang dengan
menjalankan migration `alta-database` dari awal. Isinya data uji, bukan PII.

Perintah uji lingkaran penuh dari repo ini:

```bash
export ALTA_DATABASE_URL="postgresql://postgres@localhost:55432/alta_test"
export HERMES_PROFILES_ROOT="/c/Users/user/AppData/Local/hermes/profiles"
export ALTA_BACKEND_DIR="…/ALTA/alta-database/backend"
# Windows tidak bisa mengeksekusi mcp-launch.sh, jadi tunjuk .exe-nya langsung:
export ALTA_MCP_COMMAND="…/backend/.venv/Scripts/alta-mcp.exe"
```

Hal lain yang perlu diketahui:

- Jalur berkas dirender dengan `as_posix()`: render boleh berjalan di Windows,
  tetapi yang membaca hasilnya selalu Linux di VPS.
- **Jangan menjalankan `uv run` di `alta-database/backend`.** Ia menyelaraskan
  ulang venv dan menaikkan `mcp` ke versi mayor yang mematikan server MCP.
  Pemulihannya: `uv pip install --python .venv/Scripts/python.exe "mcp<2" -e ".[dev]"`.
- Hermes **tidak** mewariskan lingkungan induk ke subproses MCP — hanya `env` di
  `config.yaml` yang sampai. Itulah alasan `mcp-launch.sh` ada.

## Menambah atau mengubah arahan departemen

1. Sunting `directives/<dept>.md`. Heading `##` menjadi baris `agent_directives`:
   `## persona` (tepat satu, tanpa judul), `## policy: Judul`, `## sop: Judul`.
2. `alta-hermes doctor` — ia menolak persona ganda, bagian kosong, dan SOUL
   yang melewati ambang panjang (Hermes memotong context file di 20.000
   karakter, dan yang hilang justru SOP di bagian bawah).
3. `alta-hermes sync --dry-run`, lalu `sync --reason "..."`. Alasan itu masuk
   `audit_log` sebagai `human`/`founder` — tulis yang sebenarnya.
4. `alta-hermes render`, jalankan `cron.sh` bila jadwalnya berubah.

Nama tool yang disebut di directive harus **benar-benar ada**. Daftarnya di
`alta-database/backend/src/alta_core/mcp/tools/`; departemen mana yang
mendapat modul apa ditentukan konstanta `WRITERS` / `MODULE_AGENTS` di tiap
modul. Menyebut tool yang tidak ada membuat agent membuang giliran mencari
sesuatu yang tidak pernah muncul di daftar perkakasnya.

## Bahasa

Seluruh dokumentasi, komentar, dan teks arahan memakai **bahasa Indonesia
baku** — bukan slang, bukan campur-campur. Kode (nama fungsi, variabel) tetap
Inggris. Directive ditulis untuk dibaca model **dan** founder, jadi kalimatnya
harus benar-benar bisa dieksekusi: sebut tool, sebut ambang, sebut apa yang
dianggap selesai.
