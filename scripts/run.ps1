# SCP Shorts Studio — start the app (Windows PowerShell)
# Serves the built frontend + API from one origin at http://127.0.0.1:8000
# Run from the repo root:  powershell -File scripts\run.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\backend"

if (-not (Test-Path "$root\frontend\dist")) {
    Write-Warning "frontend\dist not found — run scripts\setup.ps1 first (or 'npm run build' in frontend\)."
}

Write-Host "Starting SCP Shorts Studio at http://127.0.0.1:8000  (Ctrl+C to stop)" -ForegroundColor Green
& "$root\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
