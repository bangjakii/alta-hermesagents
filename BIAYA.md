# Ongkos armada agent

Ditulis 16 Agustus 2026 setelah tagihan $20 dalam beberapa jam uji.

## Di mana uangnya habis

Bukan pada pekerjaan agent. Pada konteks yang dikirim ulang **sebelum** ia
mengerjakan apa pun. Sekali denyut cron membayar seluruh blok ini:

| Blok | Ukuran | Catatan |
| --- | --- | --- |
| System prompt Hermes | 17–21 KB | setelah skill bawaan dilepas |
| Skema tool Hermes | ~10 KB | memory, todo, session_search (+delegation di orkestrator) |
| Skema tool ALTA | 13–36 KB | lihat tabel di bawah |

Skema tool ALTA per departemen, diukur langsung dari registri MCP:

| Departemen | Tool | Skema | ~Token |
| --- | ---: | ---: | ---: |
| verifying_readiness | 40 | 36,4 KB | 9.313 |
| recruitment | 36 | 30,7 KB | 7.858 |
| orchestrator | 47 | 29,6 KB | 7.565 |
| sales | 23 | 23,5 KB | 6.006 |
| legal | 27 | 21,3 KB | 5.451 |
| it | 18 | 13,9 KB | 3.556 |
| finance | 18 | 13,7 KB | 3.500 |
| marketing | 19 | 13,6 KB | 3.486 |
| customer_service | 15 | 12,7 KB | 3.251 |

Kira-kira **15.000–20.000 token input sekali denyut**. Dengan Sonnet
($3/1M) itu $0,05–0,06 — dan mayoritas denyut hanya menemukan antrean
kosong lalu berhenti. Membayar penuh untuk tidak melakukan apa-apa.

## Tuas, urut dari yang paling berpengaruh

### 1. Cadence — linear, penentu utama

Sembilan job tiap menit ≈ 540 panggilan/jam ≈ $32/jam. Jadwal semula
(15/30 menit, 2 jam) ≈ 36 panggilan/jam ≈ $2/jam. Enam belas kali lipat,
hanya dari angka di kolom cron.

`schedules.yaml` menyimpan nilai produksi di kepala berkasnya. Setelan
tiap menit hanya untuk melihat putaran kerja saat mengembangkan.

### 2. Jam kerja — 3x, tanpa kehilangan apa pun

Departemen tidak perlu bangun pukul tiga pagi. `*/15 8-18 * * 1-5`
memangkas dua pertiga denyut dibanding `*/15 * * * *`, dan tidak ada
pekerjaan perekrutan yang benar-benar tertunda karenanya. Job yang memang
harus jalan di luar jam kerja (mis. sapuan kesejahteraan pekerja di zona
waktu lain) dikecualikan satu per satu.

### 3. Cache prompt — sudah dipasang

`prompt_caching.cache_ttl: 1h` dirender ke tiap profile. Bawaan Hermes 5
menit, yang SELALU meleset untuk jadwal lebih jarang dari itu — tiap denyut
lalu membayar penuh. Tulis 1 jam berongkos 2x sekali, bacanya 0,1x. Untuk
pekerja cron dengan konteks yang sama persis tiap kali, ini memangkas blok
stabil di atas menjadi sepersepuluh.

### 4. Skill bawaan — sudah dilepas

Tiap profile Hermes datang dengan 73 skill bawaan (apple, spotify, github,
smart-home, yuanbao) yang tidak satu pun dipakai departemen ALTA. Indeksnya
ikut di tiap panggilan: 6,8 KB. Dilepas dengan
`hermes -p <profile> skills opt-out --remove --yes` — system prompt turun
dari ~25 KB ke ~19 KB. Ulangi untuk profile baru.

### 5. Model per job

`hermes cron create --model` menerima pin per job. Job polling yang
biasanya menemukan antrean kosong tidak butuh Sonnet ($3/$15); Haiku 4.5
($1/$5) tiga kali lebih murah untuk pekerjaan membaca antrean dan
memutuskan tidak ada yang perlu dikerjakan.

### 6. Skema tool — pekerjaan yang belum dilakukan

Blok terbesar untuk V&R dan Recruitment. Deskripsi tool ditulis panjang
supaya agent tidak salah pakai, dan itu memang berguna — tapi 36 KB dikirim
tiap denyut selamanya. Mempersempit toolset per departemen (bukan
memendekkan deskripsinya) menurunkan ini tanpa membuat tool jadi
membingungkan.

## Yang TIDAK menurunkan biaya

- Mematikan MCP server: ia tidak memanggil model sama sekali.
- Admin panel dan REST API: keduanya tidak menyentuh LLM.
- Postgres: gratis.

Biaya armada ini hampir seluruhnya token input cron. Kalau tagihan naik,
lihat kolom cron lebih dulu.
