#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_REPOSITORY:?source repository is required}"
data_repository="${FINPRED_DATA_REPOSITORY:-$GITHUB_REPOSITORY}"
if [[ ! "$data_repository" =~ ^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$ ]]; then
  echo '::error::Invalid private data repository identifier.'
  exit 1
fi
if [[ "${data_repository,,}" != "${GITHUB_REPOSITORY,,}" && -z "${FINPRED_DATA_TOKEN:-}" ]]; then
  echo '::error::A scoped FINPRED_DATA_TOKEN is required for a separate private data repository.'
  exit 1
fi
if ! private="$(gh api "repos/$data_repository" --jq '.private')"; then
  echo '::error::Cannot verify the private data repository or token access.'
  exit 1
fi
if [[ "$private" != 'true' ]]; then
  echo '::error::The data repository is public; private data publication is blocked.'
  exit 1
fi
