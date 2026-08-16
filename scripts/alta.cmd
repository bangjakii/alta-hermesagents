@echo off
REM =====================================================================
REM Padanan alta.ps1 untuk Command Prompt.
REM =====================================================================
REM Perlu ada karena `hermes` polos membuka profile BAWAAN, dan profile
REM bawaan di mesin dev ini milik Krakatau Shipyard. ALTA selalu lewat -p.
REM
REM   scripts\alta.cmd orchestrator chat
REM   scripts\alta.cmd it mcp test alta
REM =====================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0alta.ps1" %*
