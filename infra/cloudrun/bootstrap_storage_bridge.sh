#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_PATH="${1:-infra/cloudrun/storage_bridge_bootstrap.example.json}"
VALIDATION_JSON="$(mktemp)"
cleanup() {
  rm -f "${VALIDATION_JSON}"
}
trap cleanup EXIT

cd "${REPO_ROOT}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $1" >&2
    exit 1
  }
}

need_cmd python3
need_cmd gcloud

python3 tools/validate_phase18_storage_bridge_bootstrap.py "${CONFIG_PATH}" >"${VALIDATION_JSON}" || {
  cat "${VALIDATION_JSON}" >&2
  echo "ERROR: storage bridge bootstrap validation failed" >&2
  exit 1
}

python3 - "$VALIDATION_JSON" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
for key in ("warnings",):
    items = payload.get(key) or []
    if items:
        print(f"{key.upper()}:")
        for item in items:
            print(f"- {item}")
if not payload.get("ok"):
    raise SystemExit("validation failed")
print("BUILD:", " ".join(payload["build_command_preview"]))
print("DEPLOY:", " ".join(payload["deploy_command_preview"]))
print("INVOKER:", " ".join(payload["invoker_binding_preview"]))
print("BRIDGE_BASE_URL_HINT:", payload["bridge_base_url_hint"])
PY

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "DRY RUN PASS"
  exit 0
fi

mapfile -t BUILD_CMD < <(python3 - "$VALIDATION_JSON" <<'PY'
import json
import sys
for item in json.loads(open(sys.argv[1], encoding="utf-8").read())["build_command_preview"]:
    print(item)
PY
)
mapfile -t DEPLOY_CMD < <(python3 - "$VALIDATION_JSON" <<'PY'
import json
import sys
for item in json.loads(open(sys.argv[1], encoding="utf-8").read())["deploy_command_preview"]:
    print(item)
PY
)
mapfile -t INVOKER_CMD < <(python3 - "$VALIDATION_JSON" <<'PY'
import json
import sys
for item in json.loads(open(sys.argv[1], encoding="utf-8").read())["invoker_binding_preview"]:
    print(item)
PY
)

"${BUILD_CMD[@]}"
"${DEPLOY_CMD[@]}"
"${INVOKER_CMD[@]}"

python3 - "$VALIDATION_JSON" <<'PY'
import json
import sys
payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
print("")
print("Set these in the main application deploy environment after bridge bootstrap:")
print(f"STORAGE_BRIDGE_BASE_URL={payload['bridge_base_url_hint']}")
print(f"STORAGE_BRIDGE_AUTH_AUDIENCE={payload['bridge_base_url_hint']}")
PY
