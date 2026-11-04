#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${FINPRED_DATA_ROOT:?live-data checkout is required}"
data_repository="${FINPRED_DATA_REPOSITORY:-${GITHUB_REPOSITORY:-}}"
: "${data_repository:?data owner/repository is required}"
course_mode="${FINPRED_COURSE_MODE:-rehearsal}"
if [[ "${FINPRED_EVENT_NAME:-}" == "schedule" ]]; then
  # Preserve the requested stage if GitHub delays its runner. Each stage still
  # enforces its real execution window; the wrapper never catches up by POSTing.
  case "${FINPRED_SCHEDULE:-}" in
    '20 23 * * *'|'35 23 * * *') course_mode=train ;;
    '10 0 * * *'|'14 0 * * *') course_mode=predict ;;
    '20 0 * * *'|'27 0 * * *') course_mode=submit ;;
    '35 0 * * *'|'42 0 * * *') course_mode=verify ;;
    *) echo 'Unknown course schedule; execution blocked.' >&2; exit 1 ;;
  esac
fi
arguments=(--data-dir "$FINPRED_DATA_ROOT" --repository "$data_repository" --mode "$course_mode")
if [[ "${FINPRED_ALLOW_PUBLIC_DATA:-}" == "true" ]]; then
  arguments+=(--allow-public-data)
fi
if [[ -n "${FINPRED_TARGET_DATE:-}" ]]; then
  arguments+=(--target-date "$FINPRED_TARGET_DATE")
fi
if [[ "$course_mode" == "submit" && "${FINPRED_SUBMISSION_RELEASED:-false}" == "true" ]]; then
  arguments+=(--submit)
fi
python scripts/run_hosted_course.py "${arguments[@]}"
