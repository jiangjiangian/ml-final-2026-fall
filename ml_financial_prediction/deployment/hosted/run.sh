#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${FINPRED_DATA_ROOT:?live-data checkout is required}"
: "${GITHUB_REPOSITORY:?private owner/repository is required}"

arguments=(--data-dir "$FINPRED_DATA_ROOT" --repository "$GITHUB_REPOSITORY")
if [[ "${FINPRED_MODE:-rehearsal}" == "financial" ]]; then
  selected_stage="${FINPRED_STAGE:-auto}"
  if [[ "$selected_stage" == "auto" ]]; then
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
