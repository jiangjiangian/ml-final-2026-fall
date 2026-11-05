#!/usr/bin/env bash
# Reproduce the Python project environment without changing the current branch.
set -euo pipefail
PROJECT_REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_REPO_ROOT/ml_financial_prediction"
FINPRED_SETUP_EXTRAS=(--extra models --extra data)
if [ "${FINPRED_WITH_NEURAL:-0}" = "1" ]; then
  FINPRED_SETUP_EXTRAS+=(--extra neural)
fi
UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}" uv sync --locked --group dev "${FINPRED_SETUP_EXTRAS[@]}"
UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}" uv run --locked --no-sync ruff check src scripts tests
UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}" uv run --locked --no-sync python -m unittest discover -s tests -q
