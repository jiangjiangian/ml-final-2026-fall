#!/usr/bin/env bash
# One bounded stage; the Python pipeline owns calendars, deadlines and manifests.
set -euo pipefail
: "${FINPRED_PROJECT_ROOT:?Set the absolute business-project directory}"
: "${FINPRED_RUNTIME_ROOT:?Set a persistent private runtime directory outside Git}"
FINPRED_STAGE="${1:?Expected collect, train, predict, submit, or verify}"
case "$FINPRED_STAGE" in collect|train|predict|submit|verify) ;; *) exit 64 ;; esac
cd "$FINPRED_PROJECT_ROOT"
FINPRED_ARGS=(scripts/run_daily_pipeline.py --runtime-dir "$FINPRED_RUNTIME_ROOT" --stage "$FINPRED_STAGE")
if [ -n "${FINPRED_TARGET_DATE:-}" ]; then FINPRED_ARGS+=(--target-date "$FINPRED_TARGET_DATE"); fi
if [ -n "${FINPRED_TRAINING_TABLE:-}" ]; then FINPRED_ARGS+=(--training-table "$FINPRED_TRAINING_TABLE"); fi
if [ -n "${FINPRED_PREDICTION_TABLE:-}" ]; then FINPRED_ARGS+=(--prediction-table "$FINPRED_PREDICTION_TABLE"); fi
if [ -n "${FINPRED_CSV:-}" ]; then FINPRED_ARGS+=(--csv "$FINPRED_CSV"); fi
if [ "$FINPRED_STAGE" = submit ] && [ "${FINPRED_ENABLE_SUBMIT:-0}" = 1 ]; then
  FINPRED_ARGS+=(--submit)
else
  FINPRED_ARGS+=(--dry-run)
fi
exec "$FINPRED_PROJECT_ROOT/.venv/bin/python" "${FINPRED_ARGS[@]}"
