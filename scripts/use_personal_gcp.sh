#!/usr/bin/env bash
# Use personal Gmail + skincare-trends-dev for this repo (not Wayfair ADC/gcloud).
# Source from shells or scripts:  source scripts/use_personal_gcp.sh

PERSONAL_GCP_CONFIG="${PERSONAL_GCP_CONFIG:-personal-codebase}"
PERSONAL_GCP_ACCOUNT="${PERSONAL_GCP_ACCOUNT:-yingjzhang02@gmail.com}"
PERSONAL_GCP_PROJECT="${PERSONAL_GCP_PROJECT:-skincare-trends-dev}"

export CLOUDSDK_ACTIVE_CONFIG_NAME="${PERSONAL_GCP_CONFIG}"
export DBT_GCP_PROJECT="${PERSONAL_GCP_PROJECT}"
export GOOGLE_CLOUD_QUOTA_PROJECT="${PERSONAL_GCP_PROJECT}"

if ! gcloud config configurations describe "${PERSONAL_GCP_CONFIG}" >/dev/null 2>&1; then
  echo "Creating gcloud config '${PERSONAL_GCP_CONFIG}' for personal codebase..." >&2
  gcloud config configurations create "${PERSONAL_GCP_CONFIG}"
  gcloud config configurations activate "${PERSONAL_GCP_CONFIG}"
  gcloud config set account "${PERSONAL_GCP_ACCOUNT}"
  gcloud config set project "${PERSONAL_GCP_PROJECT}"
  gcloud config configurations activate default
fi

_active_account="$(gcloud config get-value account 2>/dev/null || true)"
_active_project="$(gcloud config get-value project 2>/dev/null || true)"

if [[ "${_active_account}" != "${PERSONAL_GCP_ACCOUNT}" ]]; then
  echo "WARNING: gcloud account is '${_active_account}', expected '${PERSONAL_GCP_ACCOUNT}'." >&2
fi

if [[ "${_active_project}" != "${PERSONAL_GCP_PROJECT}" ]]; then
  echo "WARNING: gcloud project is '${_active_project}', expected '${PERSONAL_GCP_PROJECT}'." >&2
fi

_adc_file="${HOME}/.config/gcloud/application_default_credentials.json"
if [[ ! -f "${_adc_file}" ]]; then
  echo "WARNING: ADC not configured. dbt will fail until you run:" >&2
  echo "  gcloud auth application-default login --account=${PERSONAL_GCP_ACCOUNT} \\" >&2
  echo "    --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/bigquery" >&2
  echo "  gcloud auth application-default set-quota-project ${PERSONAL_GCP_PROJECT}" >&2
else
  _adc_quota="$(python3 - <<'PY' 2>/dev/null || true
import json, os
path = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
with open(path) as f:
    print(json.load(f).get("quota_project_id") or "")
PY
)"
  if [[ "${_adc_quota}" != "${PERSONAL_GCP_PROJECT}" ]]; then
    echo "WARNING: ADC quota project is '${_adc_quota:-unset}', expected '${PERSONAL_GCP_PROJECT}'." >&2
    echo "If dbt fails with Access Denied, ADC is likely still on Wayfair. Re-login with:" >&2
    echo "  gcloud auth application-default login --account=${PERSONAL_GCP_ACCOUNT} \\" >&2
    echo "    --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/bigquery" >&2
    echo "  gcloud auth application-default set-quota-project ${PERSONAL_GCP_PROJECT}" >&2
  fi
fi

echo "Personal GCP: account=${_active_account} project=${_active_project} config=${PERSONAL_GCP_CONFIG}"
