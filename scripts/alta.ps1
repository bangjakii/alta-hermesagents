# =====================================================================
# Menjalankan Hermes untuk satu departemen ALTA - uji lokal di Windows.
# =====================================================================
# Kunci cukup ada di SATU tempat: .env di akar repo ini. Skrip ini memuatnya
# ke lingkungan proses, lalu memanggil hermes. Tidak ada salinan kunci yang
# berserak di .env tiap profile.
#
#   .\scripts\alta.ps1 orchestrator chat        # buka CLI
#   .\scripts\alta.ps1 orchestrator doctor
#   .\scripts\alta.ps1 it mcp test alta
#
# Di VPS pola ini TIDAK dipakai: gateway berjalan sebagai layanan tanpa
# shell, jadi di sana kredensial memang harus ada di .env tiap profile
# (lihat `alta-hermes secrets`).
#
# Berkas ini sengaja ASCII saja: PowerShell 5.1 membaca .ps1 sebagai ANSI,
# dan karakter non-ASCII tanpa BOM membuatnya gagal di-parse.
# =====================================================================

param(
    [Parameter(Mandatory = $true)][string]$Dept,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$HermesArgs
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repo '.env'

if (-not (Test-Path $envFile)) {
    throw "Belum ada .env di $repo. Salin .env.example lalu isi kuncinya."
}

# Muat .env repo ke lingkungan proses ini saja; tidak menyentuh sistem.
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $k, $v = $line -split '=', 2
        $v = $v.Trim().Trim('"').Trim("'")
        if ($v) { Set-Item -Path "Env:$($k.Trim())" -Value $v }
    }
}

# Nama profile mengikuti agents.yaml. Nama profile penuh juga boleh dipakai.
$profileName = switch ($Dept) {
    'orchestrator'        { 'alta-orchestrator' }
    'recruitment'         { 'alta-recruitment' }
    'verifying_readiness' { 'alta-vr' }
    'vr'                  { 'alta-vr' }
    'customer_service'    { 'alta-cs' }
    'cs'                  { 'alta-cs' }
    'sales'               { 'alta-sales' }
    'legal'               { 'alta-legal' }
    'finance'             { 'alta-finance' }
    'marketing'           { 'alta-marketing' }
    'it'                  { 'alta-it' }
    default               { $Dept }
}

$hermes = (Get-Command hermes -ErrorAction SilentlyContinue).Source
if (-not $hermes) {
    $hermes = Join-Path $env:LOCALAPPDATA 'hermes\hermes-agent\venv\Scripts\hermes.exe'
}
if (-not (Test-Path $hermes)) {
    throw "hermes tidak ditemukan di PATH maupun di $hermes"
}

if (-not $HermesArgs) { $HermesArgs = @('chat') }

& $hermes -p $profileName @HermesArgs
