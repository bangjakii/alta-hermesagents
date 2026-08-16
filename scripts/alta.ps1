# =====================================================================
# Menjalankan Hermes untuk satu departemen ALTA - uji lokal di Windows.
# =====================================================================
# Yang Anda sunting cukup SATU berkas: .env di akar repo ini.
#
#   .\scripts\alta.ps1 orchestrator chat        # buka CLI
#   .\scripts\alta.ps1 orchestrator doctor
#   .\scripts\alta.ps1 it mcp test alta
#
# Kenapa skrip ini menyalin kunci ke .env tiap profile, bukan sekadar
# meng-export ke lingkungan proses: hermes_cli/env_loader.py memuat .env
# milik HERMES_HOME dengan override=True, justru supaya menang atas
# variabel shell yang basi. Jadi apa pun yang di-export di sini akan
# ditimpa .env profile. Satu-satunya cara "satu berkas" tetap berlaku
# adalah menjadikan .env repo sumber, lalu menyebarkannya tiap kali.
#
# Di VPS pola ini TIDAK dipakai: gateway berjalan sebagai layanan tanpa
# shell, dan `alta-hermes secrets` dijalankan sekali saat deploy.
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

# Sebarkan kunci dari .env repo ke .env profile. Diam bila berhasil; kalau
# gagal cuma diperingatkan, sebab profile bisa saja sudah punya kunci yang sah.
$secrets = (Get-Command alta-hermes -ErrorAction SilentlyContinue).Source
if ($secrets) {
    $out = & $secrets secrets 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "penyebaran kunci gagal; memakai .env profile yang ada"
        $out | ForEach-Object { Write-Warning $_ }
    }
}

# Jalankan dari workspace profile, bukan dari repo. Hermes menempelkan
# CLAUDE.md/AGENTS.md milik cwd ke system prompt (agent/prompt_builder.py),
# dan CLAUDE.md repo ini ditujukan untuk Claude Code yang MENGGARAP repo --
# terbaca dari dalam, orchestrator menyangka tugasnya mengaudit directive.
$workspace = Join-Path $env:HERMES_PROFILES_ROOT (Join-Path $profileName 'workspace')
if (-not (Test-Path $workspace)) { New-Item -ItemType Directory -Path $workspace -Force | Out-Null }

Push-Location $workspace
try {
    & $hermes -p $profileName @HermesArgs
} finally {
    Pop-Location
}
