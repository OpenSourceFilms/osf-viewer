#!/usr/bin/env bash
set -uo pipefail
source /workspace/services/osf_viewer/env.sh

if [[ -f "$OSFV_PID" ]]; then
  PID="$(cat "$OSFV_PID" || true)"
  if [[ -n "${PID:-}" ]] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    sleep 1
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
  fi
  rm -f "$OSFV_PID"
fi
pkill -f "osf_viewer/app.py" 2>/dev/null || true
echo "osf_viewer stopped."
