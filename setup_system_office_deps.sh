#!/usr/bin/env bash
# One-command restore for osf_viewer's SYSTEM-level office-document support.
#
# Why this exists: LibreOffice is installed via apt into the container's
# ephemeral overlay (/), not /workspace -- it does NOT survive a pod rebuild,
# unlike everything in requirements.lock.txt (which lives in the /workspace
# venv). If osf_viewer starts fine but every DOCX/XLSX/PPTX/ODT/ODS/ODP/
# legacy-Office/RTF file falls back to the generic binary report instead of
# real extracted text, and /preview.pdf 404s for those formats, this script
# is almost certainly what's missing -- run it before debugging anything else.
#
# Deliberately does NOT install a JVM or Apache Tika: this pod has no Java
# runtime, and pure-Python libraries (python-docx/openpyxl/python-pptx/
# odfpy, all pinned in requirements.lock.txt) already give better structural
# fidelity than a raw Tika text dump for the DOCX/XLSX/PPTX/ODT/ODS/ODP
# formats -- see the "why no Tika" note in DOCS.md and office_extract.py's
# module docstring. LibreOffice headless here is used only for /preview.pdf
# rendering and for converting legacy binary formats (.doc/.xls/.ppt/.rtf)
# to their modern XML equivalent before running them through the same
# structural extractor.
set -euo pipefail

if command -v soffice >/dev/null 2>&1; then
  echo "soffice already present: $(soffice --version)"
  exit 0
fi

echo "Installing LibreOffice (writer/calc/impress only, --no-install-recommends)..."
apt-get update
apt-get install -y --no-install-recommends \
  libreoffice-writer libreoffice-calc libreoffice-impress

echo "Verifying by function (not just presence)..."
TD="$(mktemp -d)"
printf 'setup_system_office_deps.sh functional probe\n' > "$TD/probe.txt"
soffice --headless --invisible --nologo --nofirststartwizard --norestore --nolockcheck \
  -env:"UserInstallation=file://$TD/profile" \
  --convert-to pdf --outdir "$TD" "$TD/probe.txt" >/dev/null 2>&1
if [[ -s "$TD/probe.pdf" ]]; then
  echo "OK: soffice headless conversion produced a real PDF ($(stat -c%s "$TD/probe.pdf") bytes)."
else
  echo "ERROR: soffice installed but headless conversion did not produce a PDF." >&2
  rm -rf "$TD"
  exit 1
fi
rm -rf "$TD"

echo ""
echo "Installed: $(dpkg -l | grep -c '^ii  libreoffice') libreoffice-* packages"
echo "(exact versions this was verified against: libreoffice-{core,common,writer,calc,impress,draw,base-core}"
echo " 1:6.4.7-0ubuntu0.20.04.15 on Ubuntu 20.04/focal -- apt will pick whatever"
echo " is current in this image's configured repos, which is expected to be at"
echo " least this version)."
echo "Done. Restart osf_viewer (bash restart.sh) to pick this up."
