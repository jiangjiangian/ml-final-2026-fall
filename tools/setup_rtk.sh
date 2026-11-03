#!/usr/bin/env bash
set -euo pipefail

# Reviewed official installer, pinned independently from the release version.
rtk_project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
rtk_installer_path="$(mktemp)"
trap 'rm -f -- "$rtk_installer_path"' EXIT
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  --connect-timeout 10 --max-time 60 \
  'https://raw.githubusercontent.com/rtk-ai/rtk/753a3b0e939f2e4490fc24e3a1984010f40a103c/install.sh' \
  --output "$rtk_installer_path"
python3 - "$rtk_installer_path" <<'PY'
import hashlib
from pathlib import Path
import sys

expected = '7ca3997314f631b8ad267e5add9af4b7a2f0351bdab0b1c5a9b7ed4008d0434a'
if hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest() != expected:
    raise SystemExit('Official RTK installer checksum mismatch')
PY
rtk_install_dir="${RTK_INSTALL_DIR:-$HOME/.local/bin}"
RTK_VERSION=v1.1.0 RTK_INSTALL_DIR="$rtk_install_dir" sh "$rtk_installer_path"
cd -- "$rtk_project_root"
"$rtk_install_dir/rtk" init --codex
