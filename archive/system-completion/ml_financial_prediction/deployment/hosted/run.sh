#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${FINPRED_DATA_ROOT:?live-data checkout is required}"
data_repository="${FINPRED_DATA_REPOSITORY:-${GITHUB_REPOSITORY:-}}"
: "${data_repository:?private data owner/repository is required}"

arguments=(--data-dir "$FINPRED_DATA_ROOT" --repository "$data_repository")
if [[ "${FINPRED_ALLOW_PUBLIC_DATA:-}" == "true" ]]; then
  arguments+=(--allow-public-data)
fi
if [[ "${FINPRED_MODE:-rehearsal}" == "financial" ]]; then
  selected_stage="${FINPRED_STAGE:-auto}"
  if [[ "${FINPRED_EVENT_NAME:-}" == "schedule" ]]; then
    # Preserve the scheduled operation when a hosted runner starts late. The
    # selected stage still enforces its own real-clock window and hard deadline.
    case "${FINPRED_SCHEDULE:-}" in
      '20 23 * * *') selected_stage=train ;;
      '10 0 * * *') selected_stage=predict ;;
      '20 0 * * *') selected_stage=submit ;;
      '35 0 * * *') selected_stage=verify ;;
      *) printf '%s\n' 'Unknown financial schedule; stage execution blocked' >&2; exit 1 ;;
    esac
  elif [[ "$selected_stage" == "auto" ]]; then
    selected_stage="$(python - <<'PY'
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
module_path = Path('scripts/run_hosted_pipeline.py').resolve()
spec = importlib.util.spec_from_file_location('hosted_stage', module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.select_stage(datetime.now(timezone.utc)))
PY
)"
  fi
  arguments+=(--mode stage --stage "$selected_stage")
  if [[ -n "${FINPRED_TARGET_DATE:-}" ]]; then
    arguments+=(--target-date "$FINPRED_TARGET_DATE")
  fi
  if [[ "$selected_stage" == "submit" && "${FINPRED_SUBMISSION_RELEASED:-false}" == "true" ]]; then
    arguments+=(--submit)
  fi
else
  arguments+=(--mode "${FINPRED_MODE:-rehearsal}")
fi
python scripts/run_hosted_pipeline.py "${arguments[@]}"
