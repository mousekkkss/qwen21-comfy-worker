#!/usr/bin/env bash
set -euo pipefail
python -u /bootstrap.py
python -u /comfyui/main.py --disable-auto-launch --listen 127.0.0.1 --port 8188 --preview-method none --cache-none --verbose INFO &
comfy_pid=$!
trap 'kill "$comfy_pid" 2>/dev/null || true' EXIT
python -u /handler.py
