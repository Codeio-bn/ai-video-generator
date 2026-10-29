# SCP Video Studio — one-time setup (Windows PowerShell)
# Creates the Python venv, installs backend deps, vendors FFmpeg, installs the
# frontend, and builds it. Run from the repo root:  powershell -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> Creating Python virtual environment (.venv)" -ForegroundColor Cyan
if (-not (Test-Path ".venv")) { python -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt

Write-Host "==> Vendoring FFmpeg into tools\ffmpeg\bin" -ForegroundColor Cyan
$ffdir = "tools\ffmpeg\bin"
if (-not (Test-Path "$ffdir\ffmpeg.exe")) {
    New-Item -ItemType Directory -Force -Path $ffdir | Out-Null
    $zip = "$env:TEMP\ffmpeg-scp.zip"
    Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $zip
    $tmp = "$env:TEMP\ffmpeg-scp-extract"
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $bin = Get-ChildItem -Path $tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1
    Copy-Item "$($bin.Directory.FullName)\ffmpeg.exe", "$($bin.Directory.FullName)\ffprobe.exe" $ffdir -Force
    Remove-Item $zip, $tmp -Recurse -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "    FFmpeg already present, skipping." -ForegroundColor DarkGray
}
& "$ffdir\ffmpeg.exe" -version | Select-Object -First 1

Write-Host "==> Installing + building the frontend" -ForegroundColor Cyan
Set-Location "$root\frontend"
npm install
npm run build
Set-Location $root

Write-Host "`nSetup complete. Start the app with:  powershell -File scripts\dev.ps1" -ForegroundColor Green
Write-Host "Then add your OpenAI + Gemini API keys under Settings." -ForegroundColor Green
