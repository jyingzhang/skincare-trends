#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export DBT_PROFILES_DIR="$(pwd)"

# Personal codebase: personal Gmail on skincare-trends-dev (not Wayfair).
# shellcheck source=/dev/null
source "$(cd ../.. && pwd)/scripts/use_personal_gcp.sh"

if command -v dbt >/dev/null 2>&1; then
  exec dbt "$@"
fi

PYTHON_BIN="${PYTHON:-$(command -v python3 || true)}"
if [[ -n "${PYTHON_BIN}" ]]; then
  DBT_NEXT="$(dirname "${PYTHON_BIN}")/dbt"
  if [[ -x "${DBT_NEXT}" ]]; then
    exec "${DBT_NEXT}" "$@"
  fi
fi

echo "dbt not found on PATH or next to python (${PYTHON_BIN:-none})." >&2
echo "Activate your project venv, then: pip install -r ../requirements.txt" >&2
exit 127
