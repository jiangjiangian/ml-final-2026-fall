#!/usr/bin/env bash
# Install the isolated, pinned PDF-to-Markdown tool without changing project deps.
set -euo pipefail
MARKITDOWN_REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MARKITDOWN_ENV_PATH="${MARKITDOWN_ENV_PATH:-/workspace/.tools/markitdown}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}"
if [ ! -x "$MARKITDOWN_ENV_PATH/bin/python" ]; then
  uv venv --python 3.12 "$MARKITDOWN_ENV_PATH"
fi
uv pip sync --python "$MARKITDOWN_ENV_PATH/bin/python" \
  "$MARKITDOWN_REPO_ROOT/tools/markitdown-requirements.txt"
"$MARKITDOWN_ENV_PATH/bin/python" -c \
  'from importlib.metadata import version; from markitdown import MarkItDown; assert version("markitdown") == "0.1.9"; MarkItDown(enable_plugins=False); print("MarkItDown 0.1.9 ready (PDF dependencies; plugins disabled)")'
