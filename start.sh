#!/usr/bin/env bash
set -euo pipefail
source /workspace/services/osf_viewer/env.sh

mkdir -p "$OSFV_CACHE_DIR" "$(dirname "$OSFV_LOG")"

if [[ -f "$OSFV_PID" ]]; then
  PID="$(cat "$OSFV_PID" || true)"
  if [[ -n "${PID:-}" ]] && kill -0 "$PID" 2>/dev/null; then
    echo "osf_viewer already running (PID $PID)."
    exit 0
  fi
fi

pkill -f "osf_viewer/app.py" 2>/dev/null || true

nohup "$OSFV_VENV/bin/python" /workspace/services/osf_viewer/app.py \
  > "$OSFV_LOG" 2>&1 &

echo $! > "$OSFV_PID"

sleep 2.5
if ss -ltnp 2>/dev/null | grep -q ":$OSFV_PORT"; then
  echo "OK: osf_viewer listening on ${OSFV_HOST}:${OSFV_PORT}"
else
  echo "ERROR: osf_viewer not listening on ${OSFV_HOST}:${OSFV_PORT}" >&2
  echo "Check log: $OSFV_LOG" >&2
  exit 1
fi
