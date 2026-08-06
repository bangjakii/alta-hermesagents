# MEMORY — yang harus diketahui sesi baru

Catatan yang **tidak bisa disimpulkan** dari kode, git log, atau README. Kalau
sebuah fakta sudah terbaca dari berkas repo, tempatnya bukan di sini.

Perbarui berkas ini ketika sebuah keputusan berubah — memori yang basi lebih
berbahaya daripada tidak ada memori, karena ia tetap dipercaya.

---

## Perusahaan & ruang lingkup

- **PT Alta Teknologi Indonesia (ALTA)** — penyedia tenaga kerja Indonesia untuk
  Eropa, Asia Timur, Amerika Utara. Satu founder; operasional dijalankan agent.
- **Bekerja hanya untuk ALTA.** Krakatau Shipyard (KS) adalah perusahaan lain di
  grup yang sama. Repo, database, dan Hermes-nya terpisah.
- ALTA **belum punya lisensi P3MI.** Penempatan lewat mitra pemegang lisensi,
  kemungkinan lewat joint venture. Training, medical, dan visa dikerjakan mitra;
  ALTA melacak hasilnya. Kalau ALTA kelak punya izin sendiri, skema database
  sudah provider-agnostic — yang berubah hanya `enforce_partner_license`.
- **Dua model layanan:** recruitment (jual putus, *placement fee* sekali) dan
  staffing (ALTA menggaji, *management fee* berulang).

## Keputusan yang sudah diambil dan jangan dibuka lagi tanpa alasan baru

- **Sembilan profile Hermes**, bukan satu agent dengan sembilan skill. Alasannya
  di README; yang menentukan adalah subagent Hermes mewarisi seluruh toolset
  induknya, sehingga satu profile berarti batas antar departemen hilang pada
  delegasi pertama.
- **Pekerjaan mengalir lewat tabel `tasks`**, bukan lewat orchestrator memanggil
  `hermes -p <dept>`. Konsekuensinya orchestrator tidak butuh akses shell.
- **Satu VPS** (Hostinger KVM 4, Indonesia). MCP memakai transport stdio,
  sehingga 9 proses MCP wajib satu mesin dengan Hermes.
- **Pembagian LLM mengikuti PII, bukan harga.** Claude untuk departemen yang
  membaca data kandidat (orchestrator, recruitment, V&R, CS, finance; Legal
  memakai Opus termasuk subagent-nya). MiniMax untuk Sales, Marketing, IT —
  lewat OpenRouter, bukan `api.minimax.io` langsung, supaya trafiknya tidak
  dihosting di RRT.
- **Mekari Jurnal adalah buku besar.** Database hanya memegang lapisan
  operasional finance. Payroll karyawan internal di Mekari Talenta, bukan di DB.
- **Berkas di MinIO** pada VPS yang sama, bukan Google Drive — pindaian
  KTP/paspor tidak boleh keluar wilayah.
- **Founder memegang relasi klien.** Sales hanya top-of-funnel sampai
  `hand_client_to_founder`.

## Keadaan mesin pengembangan (Windows, diperiksa 6 Agustus 2026)

**Hermes terpasang** di `%LOCALAPPDATA%\hermes` dan sudah menaungi tujuh profile
KS (`ks-finance`, `ks-hr`, `ks-it`, `ks-legal`, `ks-marketing`, `ks-ops`,
`ks-sales`). Profile ALTA menumpang instalasi yang sama — satu instalasi Hermes
memang dirancang menaungi banyak profile, dan tiap profile punya `.env`,
memori, sesi, serta kredensial sendiri.

**PostgreSQL 17.4 juga ada**, sebagai biner portabel di direktori sementara
sesi lama (`%TEMP%\claude\…-alta-database\d17b66a9-…\scratchpad\pg`), berjalan
di **port 55432** dengan basis data `alta_test` berisi skema ALTA lengkap.
Karena letaknya di `%TEMP%`, anggap ia **fana**: kalau hilang, bangun ulang
dengan menjalankan migration dari awal. Isinya data uji, bukan PII.

**Docker dan WSL tidak ada.**

- `HERMES_PROFILES_ROOT` untuk percobaan lokal adalah
  `%LOCALAPPDATA%\hermes\profiles`, bukan `~/.hermes/profiles`.
- Windows tidak bisa mengeksekusi `mcp-launch.sh`, jadi untuk uji lokal setel
  `ALTA_MCP_COMMAND` ke `backend/.venv/Scripts/alta-mcp.exe`.
- `pgvector` tetap belum terverifikasi (tidak ada binary Windows resmi); salinan
  uji memakai `real[]` sebagai ganti `vector(1024)`.
- **Jangan menjalankan `uv run` di `alta-database/backend`** — ia menyelaraskan
  ulang venv dan menaikkan `mcp` ke versi mayor yang mematikan server MCP.

## Yang belum ada, dan menahan jalur kritis

1. **WhatsApp Cloud API** — verifikasi Meta Business 2–4 minggu, menuntut domain
   `alta.co.id` aktif lebih dulu, dan nomornya harus yang **belum pernah**
   dipakai WhatsApp biasa. Identitas kandidat berlabuh pada nomor WA, jadi tanpa
   ini deduplikasi tidak bisa jalan sama sekali.
2. **Registrasi `.co.id`** — menuntut akta pendirian PT, NPWP perusahaan, dan
   KTP direktur. Ia mendahului nomor 1.
3. **`max_connections` Postgres** — bawaannya 100; 9 MCP × `ALTA_POOL_MAX` + API
   bisa melebihinya. Setel 200 dan turunkan `ALTA_POOL_MAX` ke 4 sebelum
   produksi.

## Kebiasaan kerja yang diminta founder

- **Bahasa Indonesia baku** untuk semua dokumentasi dan komunikasi.
- **Satu pertanyaan pada satu waktu** ketika perlu klarifikasi, bukan daftar.
- **Jaga ruang kerja bersih** — berkas simulasi, sementara, dan scratch dihapus
  setelah dipakai.
- **Skalakan perkakas ke volume nyata.** Volume Sales ALTA rendah; jangan
  merekomendasikan alat kelas enterprise untuk antrean belasan baris.
