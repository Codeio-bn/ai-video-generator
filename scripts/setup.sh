#!/usr/bin/env bash
# SCP Video Studio — one-time setup (Linux/macOS)
# Creates the Python venv, installs backend deps, vendors FFmpeg, installs the
# frontend, and builds it. Run from anywhere:  ./scripts/setup.sh
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

echo "==> Creating Python virtual environment (.venv)"
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r backend/requirements.txt

echo "==> Vendoring FFmpeg into tools/ffmpeg/bin"
ffdir="tools/ffmpeg/bin"
if [ ! -x "$ffdir/ffmpeg" ]; then
    arch="$(uname -m)"
    case "$arch" in
        x86_64 | amd64) url="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" ;;
        aarch64 | arm64) url="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz" ;;
        *)
            echo "    Unsupported arch '$arch'. Install ffmpeg with your package" >&2
            echo "    manager (e.g. 'sudo apt install ffmpeg') and re-run." >&2
            exit 1
            ;;
    esac
    mkdir -p "$ffdir"
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    echo "    downloading $url"
    curl -fL "$url" -o "$tmp/ffmpeg.tar.xz"
    tar -xf "$tmp/ffmpeg.tar.xz" -C "$tmp"
    bin="$(dirname "$(find "$tmp" -type f -name ffmpeg | head -n1)")"
    cp "$bin/ffmpeg" "$bin/ffprobe" "$ffdir/"
    chmod +x "$ffdir/ffmpeg" "$ffdir/ffprobe"
    rm -rf "$tmp"
    trap - EXIT
else
    echo "    FFmpeg already present, skipping."
fi
"$ffdir/ffmpeg" -version | head -n1

echo "==> Installing + building the frontend"
cd "$root/frontend"
npm install
npm run build
cd "$root"

echo
echo "Setup complete. Start the app with:  ./scripts/dev.sh"
echo "Then add your OpenAI + Gemini API keys under Settings."
