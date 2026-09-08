#!/usr/bin/env bash
set -euo pipefail

export OSFV_ROOT="/workspace"
export OSFV_HOST="127.0.0.1"
export OSFV_PORT="3930"
export OSFV_CACHE_DIR="/workspace/.osf_view_cache"
export OSFV_LOG="/workspace/services/osf_viewer/osf_viewer.log"
export OSFV_PID="/workspace/services/osf_viewer/osf_viewer.pid"
export OSFV_VENV="/workspace/services/osf_viewer/.venv"
export OSFV_DENYLIST_FILE="/workspace/services/osf_viewer/denylist.txt"
