# ALTA Hermes Agents — Runtime

Lapisan yang menjalankan sembilan departemen ALTA di atas [Hermes
Agent](https://hermes-agent.nousresearch.com/docs). Isinya tiga hal:

1. **Boot script** — merender desired state dari `alta-database` menjadi berkas
   runtime Hermes (`SOUL.md`, `config.yaml`, cron).
2. **Teks arahan** tiap departemen (`directives/`) — sumber yang di-version
   control untuk tabel `agent_directives`.
3. **Guardrail** (`guardrails/`) — aturan yang sengaja **tidak** disimpan di
   database, supaya tidak bisa berubah tak sengaja lewat CRUD Admin Panel.

Repo ini tidak memuat tool. Seluruh akses ke data ALTA lewat MCP Server di
`alta-database/backend`, satu proses per departemen.

---

## Arah Aliran

```
directives/  agents.yaml  schedules.yaml        <- ditulis & ditelaah lewat git
        |
        |   alta-hermes sync          (actor: human/founder, teraudit)
        v
alta-database: agent_directives, agents, agent_schedules   <- SUMBER KEBENARAN
        |                                                     (founder menyetel
        |   alta-hermes render                                  dari Admin Panel)
        v
~/.hermes/profiles/<dept>/
        SOUL.md      guardrail repo + persona/policy/sop dari DB
        config.yaml  model, provider, MCP departemen, toolset, hook
        cron.sh      pendaftaran ulang jadwal ke cron Hermes
```

Repo adalah tempat teksnya **ditulis**; database tempat founder
**menyetelnya** tanpa deploy; berkas profile adalah **runtime**. Karena itu
`render` normalnya membaca dari database, bukan dari repo — kalau tidak,
setelan founder akan tertimpa setiap kali seseorang menjalankan render.

`--from files` ada untuk satu keperluan: bekerja dan menguji sebelum ada
Postgres sama sekali.

---

## Kenapa Sembilan Profile, Bukan Satu Agent dengan Sembilan Skill

Ini keputusan terpenting di repo ini, dan ia dipaksa oleh tiga hal yang
kebetulan menunjuk arah yang sama:

**Subagent mewarisi seluruh toolset induknya.** Hermes tidak mengizinkan
pemanggil mempersempit tool per delegasi (`delegate_task` sengaja tidak
menerima parameter `toolsets`). Kalau satu profile menyambungkan sembilan MCP
server, setiap subagent — apa pun perannya — memegang seluruh 125 tool. Batas
wewenang antar departemen akan hilang pada delegasi pertama.

**Model berbeda per departemen.** Pembagian Claude/MiniMax mengikuti PII, dan
provider ditentukan per profile. Satu profile berarti satu provider untuk
semua, dan itu berarti teks CV berakhir di tempat yang tidak dikehendaki.

**MCP Server ALTA memang sudah satu proses per departemen** (`ALTA_AGENT`).
Wewenangnya ditegakkan pada **pendaftaran**: tool di luar remit sebuah
departemen tidak pernah didaftarkan. Arsitektur profile mengikuti bentuk yang
sudah ada, bukan melawannya.

Konsekuensinya: sembilan `HERMES_HOME` terpisah, masing-masing dengan `.env`,
memori, sesi, dan skill sendiri.

### Berbagi instalasi Hermes dengan armada KS

Satu instalasi Hermes menaungi banyak profile, jadi profile `alta-*` bisa hidup
berdampingan dengan `ks-*` di mesin yang sama. Yang **terpisah** per profile:
`config.yaml`, `.env` dan seluruh kredensial, memori, sesi, skill, cron, dan
state gateway. Hermes bahkan menolak start bila dua profile memakai token bot
yang sama.

Yang **tidak** terpisah: kode Hermes itu sendiri, dan — ini yang menentukan —
akun sistem operasi. Profile bukan sandbox: agent yang punya toolset `terminal`
memakai hak akses pengguna OS yang sama, sehingga ia bisa membaca berkas milik
profile lain. Di ALTA hanya IT yang punya `terminal`, dan perintahnya disaring
hook, tetapi pemisahan sesungguhnya antara data ALTA dan armada KS tetap
**pemisahan mesin**: produksi ALTA jalan di VPS-nya sendiri, dengan Postgres
dan MinIO yang tidak pernah menyentuh mesin lain.

Instalasi lokal karena itu berguna untuk mengembangkan dan memeriksa hasil
render, bukan untuk menjalankan operasional.

---

## Bagaimana Pekerjaan Mengalir Antar Departemen

**Tidak ada satu pun departemen yang memanggil departemen lain.** Orchestrator
menaruh pekerjaan di tabel `tasks` lewat `assign_task`; tiap departemen
dibangunkan cron setiap 15–120 menit, membaca antreannya sendiri lewat
`list_my_tasks`, mengerjakannya, lalu tidur lagi.

Alternatifnya adalah orchestrator memanggil `hermes -p <dept> chat -q ...`
lewat terminal. Itu ditolak karena tiga alasan: orchestrator jadi butuh akses
shell (dan dengan itu, akses ke segalanya di VPS), kegagalan satu departemen
menular ke pemanggilnya, dan pekerjaannya tidak meninggalkan baris yang bisa
dilihat founder. Antrean di database memberi ketiganya secara gratis — dan
tabel `tasks` memang sudah dirancang untuk itu, lengkap dengan penugasan ke
mitra dan founder, bukan hanya ke agent.

**Satu pintu ke founder** juga jatuh dari sini: hanya profile orchestrator yang
punya gateway (Telegram). Delapan lainnya tidak punya kanal masuk sama sekali.
Aturan itu ditegakkan tiga lapis — constraint database
(`chk_founder_via_orchestrator`), `guardrails/profiles.yaml` yang tidak memberi
platform kepada siapa pun kecuali orchestrator, dan `alta-hermes doctor` yang
menolak jadwal departemen lain yang mengirim ke `telegram:founder`.

---

## Apa yang Ada di Database dan Apa yang Tidak

| Di database (bisa disetel founder) | Di repo (hanya lewat commit) |
|---|---|
| Persona, kebijakan, SOP tiap dept | Guardrail keselamatan & PII |
| Model, provider, subagent_model | Toolset tiap profile (shell, berkas, web) |
| Jadwal cron tiap dept | Hook penyaring perintah & rahasia |
| Izin tool (hanya bisa MENYEMPITKAN) | Mode baca-saja orkestrator |

Pembagiannya satu pertanyaan: *kalau ini berubah karena salah klik di Admin
Panel, apa akibat terburuknya?* Persona yang keliru menghasilkan jawaban yang
canggung. Toolset yang keliru memberi departemen Marketing akses terminal ke
VPS yang memegang PII TKI. Yang pertama boleh di database; yang kedua tidak.

---

## Perkakas

```bash
alta-hermes doctor                    # periksa sebelum menyentuh apa pun
alta-hermes sync --dry-run            # selisih repo vs database
alta-hermes sync --reason "..."       # dorong repo -> database (teraudit)
alta-hermes render                    # database -> profile Hermes
alta-hermes render --from files       # tanpa database (pengembangan)
alta-hermes render --dry-run          # tampilkan tanpa menulis
alta-hermes show legal                # cetak SOUL.md sebuah dept ke stdout
```

Skrip:

```bash
scripts/bootstrap_vps.sh              # sekali jalan: pasang, buat profile, render, cron
scripts/apply.sh "alasan perubahan"   # sync -> render -> daftar ulang cron
scripts/gateways.sh status            # gateway orchestrator + ringkasan cron
```

`config.yaml` **digabung, bukan ditimpa**: hanya kunci yang dikelola boot
script yang disentuh (`model`, `delegation`, `mcp_servers.alta`, `toolsets`,
`custom_toolsets`, `agent.disabled_toolsets`, `hooks`). Sisanya milik Hermes —
kredensial hasil `hermes setup`, preferensi tampilan, hasil `hermes tools` —
dan dipertahankan apa adanya.

`SOUL.md` baru berlaku pada **sesi baru**. Sesi yang sedang berjalan masih
memakai prompt lama; restart gateway bila perubahannya menyentuh persona atau
kebijakan.

---

## Menyiapkan VPS

```bash
git clone https://github.com/bangjakii/alta-hermesagents.git /opt/alta/alta-hermesagents
cd /opt/alta/alta-hermesagents
cp .env.example .env && $EDITOR .env
timedatectl set-timezone Asia/Jakarta       # kalau tidak, briefing pagi tiba tengah malam
scripts/bootstrap_vps.sh
```

Sesudah itu tiga hal masih dikerjakan manusia, dan memang harus:

1. **Kredensial** — dari Infisical ke `~/.hermes/profiles/<profile>/.env`.
   Minimal `ALTA_DATABASE_URL` di setiap profile, kunci provider LLM, serta
   `TELEGRAM_BOT_TOKEN` + `TELEGRAM_FOUNDER_CHAT_ID` **hanya** di orchestrator.
   Tidak ada satu pun rahasia yang boleh masuk repo ini atau database.
2. **Verifikasi nama model** — nilai di `agents.yaml` belum diperiksa terhadap
   katalog provider yang aktif. Jalankan `hermes -p <profile> model`.
3. **`max_connections`** — bawaan Postgres 100, sementara 9 MCP × `ALTA_POOL_MAX`
   ditambah API bisa melebihinya. Setel `max_connections = 200` dan turunkan
   `ALTA_POOL_MAX` ke 4 sebelum produksi; kalau tidak, proses MCP terakhir gagal
   start dengan sebab yang sulit ditebak.

---

## Struktur

```
directives/<dept>.md      teks arahan; heading ## menjadi baris agent_directives
agents.yaml               model & provider tiap dept  -> tabel agents
schedules.yaml            jadwal tiap dept            -> tabel agent_schedules
guardrails/
  GUARDRAILS.md           di-render ke puncak SETIAP SOUL.md
  profiles.yaml           toolset, platform, mode baca-saja per dept
  hooks/                  penyaring pre_tool_call (rahasia & perintah shell)
src/alta_hermes/          boot script (sync, render, doctor)
scripts/                  bootstrap, apply, kendali gateway
tests/                    uji invarian: satu pintu, batas toolset, guardrail
```

Format `directives/<dept>.md`:

```markdown
## persona            -> section persona (tepat satu, tanpa judul)
## policy: Judul      -> section policy
## sop: Judul         -> section sop
```

Teks sebelum heading `##` pertama tidak pernah masuk prompt — di situ tempat
catatan untuk pembaca manusia.

---

## Status

Diuji: 44 uji lolos — parsing directive, perakitan SOUL, penggabungan
`config.yaml`, pengutipan `cron.sh`, dan kedua hook guardrail (yang berbahaya
diblokir, yang wajar tidak).

Belum diuji terhadap sistem nyata: **`sync` ke Postgres** dan **`render` yang
dijalankan Hermes sungguhan**. Mesin pengembangan tidak punya keduanya, jadi
seluruh lapisan database baru terbukti saat dijalankan di VPS. Jalankan
`alta-hermes sync --dry-run` lebih dulu di sana sebelum menulis apa pun.

Belum dibangun:

- **Kanal WhatsApp** untuk Recruitment dan Customer Service. Keduanya butuh
  WhatsApp Cloud API, dan verifikasi Meta Business memakan 2–4 minggu.
- **Pemantauan armada** — belum ada yang memberi tahu founder kalau sebuah
  profile berhenti mengerjakan antreannya. Sementara ini terlihat lewat
  penumpukan di `operational_dashboard`, yaitu setelah terlambat.
- **Rotasi kredensial otomatis** dari Infisical ke `.env` tiap profile;
  sekarang masih disalin manusia.
