#!/usr/bin/env bash
# One-command restore for osf_viewer's venv.
#
# Why this exists: the venv's own bin/python symlink chain resolves through
# /usr/bin/python3 -> a base-image interpreter, which is NOT pinned and can
# change under a pod rebuild (this happened once already: pyvenv.cfg recorded
# 3.12.3 but the live symlink had drifted to resolve to python3.8, silently
# breaking every import). Rebuilding from this script + requirements.lock.txt
# is the only way to get back to a known-good state -- never trust the venv
# without re-running this after a base-image change.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PYBIN="/usr/bin/python3.12"
if [[ ! -x "$PYBIN" ]]; then
  echo "ERROR: $PYBIN not found. Pick another 3.x interpreter present on this" >&2
  echo "image (ls /usr/bin/python3.*), recreate the venv with it, then verify" >&2
  echo "the whole stack still imports before trusting it." >&2
  exit 1
fi

echo "Removing existing venv (if any)..."
rm -rf .venv

echo "Creating venv with $PYBIN ($("$PYBIN" --version))..."
"$PYBIN" -m venv .venv

echo "Installing pinned dependencies from requirements.lock.txt..."
.venv/bin/pip install --disable-pip-version-check -q -r requirements.lock.txt

echo "Verifying by function (not just import)..."
.venv/bin/python -c "
import magic, pypdf, py7zr, mutagen, safetensors, pyarrow
from PIL import Image
assert magic.from_file('/bin/ls'), 'libmagic probe returned nothing'
print('OK: all core deps import and libmagic functions')
"

REAL_PY="$(readlink -f .venv/bin/python)"
echo "venv python resolves to: $REAL_PY"
case "$REAL_PY" in
  /usr/bin/*)
    echo "NOTE: this venv's interpreter is a symlink into $REAL_PY on the base" >&2
    echo "image. That's expected right after a fresh install, but it means a" >&2
    echo "future base-image change can silently break this venv again -- if" >&2
    echo "osf_viewer ever fails to start after a pod rebuild, re-run this script" >&2
    echo "before debugging anything else." >&2
    ;;
esac

echo "Done."
