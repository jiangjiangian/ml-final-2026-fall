#!/usr/bin/env bash
set -euo pipefail
cd /workspace/ml-final-2026-fall
if [ ! -x /workspace/.tools/graphify/bin/python ]; then
  UV_CACHE_DIR=/workspace/.cache/uv uv venv /workspace/.tools/graphify
fi
UV_CACHE_DIR=/workspace/.cache/uv uv pip sync \
  --python /workspace/.tools/graphify/bin/python tools/graphify-requirements.txt
/workspace/.tools/graphify/bin/python -c 'import graphify; from importlib.metadata import version; assert version("graphifyy") == "0.9.95"'
