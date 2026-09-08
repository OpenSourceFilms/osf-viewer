#!/usr/bin/env bash
set -uo pipefail
source /workspace/services/osf_viewer/env.sh

if [[ -f "$OSFV_PID" ]] && kill -0 "$(cat "$OSFV_PID")" 2>/dev/null; then
  echo "osf_viewer: RUNNING (PID $(cat "$OSFV_PID"))"
else
  echo "osf_viewer: NOT RUNNING"
fi
ss -ltnp 2>/dev/null | grep ":$OSFV_PORT" || echo "port $OSFV_PORT: not listening"
curl -s -o /dev/null -w "health check: %{http_code}\n" "http://${OSFV_HOST}:${OSFV_PORT}/__view_health__" || true
