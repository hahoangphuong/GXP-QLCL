#!/usr/bin/env bash

POLICY_CHECK_ERROR_MESSAGE=""

policy_member_has_role() {
  local context="$1"
  local member="$2"
  local role="$3"
  shift 3

  POLICY_CHECK_ERROR_MESSAGE=""

  local policy_json
  local policy_err
  local parser_err
  local rc
  policy_json="$(mktemp)"
  policy_err="$(mktemp)"
  parser_err="$(mktemp)"

  if ! "$@" >"${policy_json}" 2>"${policy_err}"; then
    POLICY_CHECK_ERROR_MESSAGE="Failed to query IAM policy for ${context}."
    [[ -s "${policy_err}" ]] && cat "${policy_err}" >&2
    rm -f "${policy_json}" "${policy_err}" "${parser_err}"
    return 2
  fi

  rc=0
  python3 - "${policy_json}" "${member}" "${role}" 2>"${parser_err}" <<'PY' || rc=$?
import json
import sys

policy_path, member, role = sys.argv[1:4]
try:
    with open(policy_path, encoding="utf-8") as fh:
        policy = json.load(fh)
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
    raise SystemExit(3)

for binding in policy.get("bindings", []):
    if binding.get("role") == role and member in binding.get("members", []):
        raise SystemExit(0)
raise SystemExit(1)
PY
  if [[ "${rc}" -eq 0 ]]; then
    rm -f "${policy_json}" "${policy_err}" "${parser_err}"
    return 0
  fi

  if [[ "${rc}" -eq 1 ]]; then
    rm -f "${policy_json}" "${policy_err}" "${parser_err}"
    return 1
  fi

  POLICY_CHECK_ERROR_MESSAGE="Failed to parse IAM policy JSON for ${context}."
  [[ -s "${parser_err}" ]] && cat "${parser_err}" >&2
  rm -f "${policy_json}" "${policy_err}" "${parser_err}"
  return 3
}
