# SCP Shorts Studio — dev launcher (Windows PowerShell)
# Starts BOTH servers in one command: the FastAPI backend (hot reload) and the
# Vite frontend dev server. Styling/UI changes appear instantly, no rebuild.
# One Ctrl+C stops both. Run from the repo root:  powershell -File scripts\dev.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = "$root\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    throw "Python venv not found. Run 'powershell -File scripts\setup.ps1' first."
}
if (-not (Test-Path "$root\frontend\node_modules")) {
    throw "Frontend deps not installed. Run 'powershell -File scripts\setup.ps1' first."
}

$procs = @()
try {
    # --reload-dir app scopes the watcher to backend\app so only source edits
    # trigger a restart (not writes under data\ or projects\). WatchFiles gives
    # near-instant reloads when installed; uvicorn falls back to polling if not.
    $backend = Start-Process -PassThru -NoNewWindow -WorkingDirectory "$root\backend" `
        $py -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--reload-dir", "app", "--port", "8000"
    $procs += $backend

    $frontend = Start-Process -PassThru -NoNewWindow -WorkingDirectory "$root\frontend" `
        "cmd.exe" -ArgumentList "/c", "npm run dev"
    $procs += $frontend

    Write-Host ""
    Write-Host "  Backend   http://127.0.0.1:8000  (API, hot reload)" -ForegroundColor Green
    Write-Host "  Frontend  http://127.0.0.1:5173  <- open this one" -ForegroundColor Green
    Write-Host "  Press Ctrl+C to stop both." -ForegroundColor Yellow
    Write-Host ""

    while (-not $backend.HasExited -and -not $frontend.HasExited) {
        Start-Sleep -Milliseconds 400
    }
} finally {
    foreach ($p in $procs) {
        if ($p -and -not $p.HasExited) {
            # /T kills the whole process tree (uvicorn's reloader, npm's node child).
            taskkill /PID $p.Id /T /F 2>$null | Out-Null
        }
    }
    Write-Host "`nStopped both servers." -ForegroundColor Yellow
}
