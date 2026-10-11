#!/usr/bin/env bash
# Start the app and share it publicly with a Cloudflare quick tunnel.
# The public URL (https://<random>.trycloudflare.com) is printed below.
# Press Ctrl+C to stop both the app and the tunnel.
set -euo pipefail
cd "$(dirname "$0")"

export PORT="${PORT:-8000}"

if ! command -v cloudflared >/dev/null; then
  echo "cloudflared is not installed. Install it with: brew install cloudflared" >&2
  exit 1
fi

uv run python main.py &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null' EXIT

for _ in $(seq 1 40); do
  curl -sf "http://127.0.0.1:$PORT/api/questions" >/dev/null && break
  sleep 0.5
done

TUNNEL=(cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT")
if command -v caffeinate >/dev/null; then
  caffeinate -i "${TUNNEL[@]}"  # macOS: keep the computer awake while sharing
else
  "${TUNNEL[@]}"
fi
