#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${FINPRED_DATA_ROOT:?live-data checkout is required}"
data_repository="${FINPRED_DATA_REPOSITORY:-${GITHUB_REPOSITORY:-}}"
: "${data_repository:?data owner/repository is required}"
shadow_mode="${FINPRED_SHADOW_MODE:-rehearsal}"
if [[ "${FINPRED_EVENT_NAME:-}" == "schedule" ]]; then
  case "${FINPRED_SCHEDULE:-}" in
    '25 23 * * *') shadow_mode=train ;;
    '13 0 * * *') shadow_mode=predict ;;
    *) echo 'Unknown research shadow schedule; execution blocked.' >&2; exit 1 ;;
  esac
fi
arguments=(--data-dir "$FINPRED_DATA_ROOT" --repository "$data_repository" --mode "$shadow_mode")
if [[ "${FINPRED_ALLOW_PUBLIC_DATA:-}" == "true" ]]; then
  arguments+=(--allow-public-data)
fi
if [[ -n "${FINPRED_TARGET_DATE:-}" ]]; then
  arguments+=(--target-date "$FINPRED_TARGET_DATE")
fi
python scripts/run_hosted_shadow.py "${arguments[@]}"
