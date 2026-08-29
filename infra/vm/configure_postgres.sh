#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/vm/common.sh
source "${SCRIPT_DIR}/common.sh"

DB_NAME="${DB_NAME:-gxp_qlcl}"
DB_USER="${DB_USER:-gxp_app}"
DB_PASSWORD="${DB_PASSWORD:-}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
PG_LISTEN_ADDRESSES="${PG_LISTEN_ADDRESSES:-127.0.0.1}"
PG_SHARED_BUFFERS_MB="${PG_SHARED_BUFFERS_MB:-256}"
PG_EFFECTIVE_CACHE_SIZE_MB="${PG_EFFECTIVE_CACHE_SIZE_MB:-768}"
PG_WORK_MEM_MB="${PG_WORK_MEM_MB:-4}"
PG_MAINTENANCE_WORK_MEM_MB="${PG_MAINTENANCE_WORK_MEM_MB:-64}"
PG_AUTOVACUUM_WORK_MEM_MB="${PG_AUTOVACUUM_WORK_MEM_MB:-64}"
PG_MAX_CONNECTIONS="${PG_MAX_CONNECTIONS:-30}"
SUPPORTED_POSTGRES_MAJORS="${VM_SUPPORTED_POSTGRES_MAJORS:-17,18}"
POSTGRES_MAJOR="${VM_POSTGRES_MAJOR:-18}"
POSTGRES_CLUSTER_NAME="${VM_POSTGRES_CLUSTER_NAME:-main}"
PG_CLUSTER_DIR="${VM_POSTGRES_CLUSTER_DIR:-/etc/postgresql/${POSTGRES_MAJOR}/${POSTGRES_CLUSTER_NAME}}"

if [[ "${CONFIGURE_POSTGRES_UNSAFE_SKIP_ROOT_CHECK:-0}" != "1" ]]; then
  require_root
fi
need_cmd psql
need_cmd createdb
need_cmd pg_isready
need_cmd pg_lsclusters
need_cmd pg_ctlcluster
need_cmd runuser
load_runtime_env "${VM_RUNTIME_ENV_FILE:-/etc/gxp/runtime.env}"
DB_NAME="${DB_NAME:-gxp_qlcl}"
DB_USER="${DB_USER:-gxp_app}"
DB_PASSWORD="${DB_PASSWORD:-}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
SUPPORTED_POSTGRES_MAJORS="${VM_SUPPORTED_POSTGRES_MAJORS:-${SUPPORTED_POSTGRES_MAJORS}}"
POSTGRES_MAJOR="${VM_POSTGRES_MAJOR:-${POSTGRES_MAJOR}}"
POSTGRES_CLUSTER_NAME="${VM_POSTGRES_CLUSTER_NAME:-${POSTGRES_CLUSTER_NAME}}"

[[ -n "${DB_PASSWORD}" ]] || {
  echo "ERROR: DB_PASSWORD is required." >&2
  exit 1
}
[[ "${DB_USER}" != "postgres" ]] || {
  echo "ERROR: DB_USER must not be postgres." >&2
  exit 1
}
case ",${SUPPORTED_POSTGRES_MAJORS}," in
  *",${POSTGRES_MAJOR},"*) ;;
  *) fail "VM_POSTGRES_MAJOR=${POSTGRES_MAJOR} is unsupported. Supported majors: ${SUPPORTED_POSTGRES_MAJORS}." ;;
esac

POSTGRES_CONFIG_JSON="$(
  python3 "${REPO_ROOT}/tools/vm_postgres_config.py" render-json "${VM_RUNTIME_ENV_FILE:-/etc/gxp/runtime.env}"
)" || fail "Invalid PostgreSQL VM configuration."
POSTGRES_LISTEN_ADDRESSES="$(
  python3 -c 'import json, sys; print(json.loads(sys.argv[1])["listen_addresses_csv"])' "${POSTGRES_CONFIG_JSON}"
)" || fail "Could not resolve PG_LISTEN_ADDRESSES."
PRIVATE_HBA_RULES="$(
  python3 -c 'import json, sys; print("\n".join(json.loads(sys.argv[1])["private_hba_rules"]))' "${POSTGRES_CONFIG_JSON}"
)" || fail "Could not resolve private PostgreSQL HBA rules."

mapfile -t PG_CLUSTERS < <(pg_lsclusters --no-header 2>/dev/null || true)
MATCHING_CLUSTER_COUNT=0
UNEXPECTED_CLUSTERS=()
for cluster_line in "${PG_CLUSTERS[@]}"; do
  [[ -n "${cluster_line}" ]] || continue
  read -r cluster_version cluster_name _ <<<"${cluster_line}"
  if [[ "${cluster_version}" == "${POSTGRES_MAJOR}" && "${cluster_name}" == "${POSTGRES_CLUSTER_NAME}" ]]; then
    MATCHING_CLUSTER_COUNT=$(( MATCHING_CLUSTER_COUNT + 1 ))
  else
    UNEXPECTED_CLUSTERS+=("${cluster_version}/${cluster_name}")
  fi
done
(( ${#UNEXPECTED_CLUSTERS[@]} == 0 )) || fail "Unexpected PostgreSQL clusters detected: ${UNEXPECTED_CLUSTERS[*]}. Refusing to reconfigure the wrong cluster."
[[ "${MATCHING_CLUSTER_COUNT}" == "1" ]] || fail "Expected exactly one PostgreSQL cluster ${POSTGRES_MAJOR}/${POSTGRES_CLUSTER_NAME}, found ${MATCHING_CLUSTER_COUNT}."
[[ -d "${PG_CLUSTER_DIR}" ]] || fail "PostgreSQL cluster config directory not found: ${PG_CLUSTER_DIR}"

runuser -u postgres -- psql \
  -v ON_ERROR_STOP=1 \
  --set=db_user="${DB_USER}" \
  --set=db_password="${DB_PASSWORD}" \
  --dbname=postgres <<'SQL'
SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L',
  :'db_user',
  :'db_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = :'db_user'
)\gexec
SELECT format(
  'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L',
  :'db_user',
  :'db_password'
)\gexec
SQL

DB_EXISTS="$(
  runuser -u postgres -- psql \
    -v ON_ERROR_STOP=1 \
    --set=db_name="${DB_NAME}" \
    --dbname=postgres \
    -At <<'SQL'
SELECT 1 FROM pg_database WHERE datname = :'db_name';
SQL
)"
if [[ "${DB_EXISTS}" != "1" ]]; then
  runuser -u postgres -- createdb --owner "${DB_USER}" "${DB_NAME}"
fi

install -d -m 0755 "${PG_CLUSTER_DIR}/conf.d"
cat > "${PG_CLUSTER_DIR}/conf.d/90-gxp-vm.conf" <<EOF
listen_addresses = '${POSTGRES_LISTEN_ADDRESSES}'
password_encryption = 'scram-sha-256'
shared_buffers = '${PG_SHARED_BUFFERS_MB}MB'
effective_cache_size = '${PG_EFFECTIVE_CACHE_SIZE_MB}MB'
work_mem = '${PG_WORK_MEM_MB}MB'
maintenance_work_mem = '${PG_MAINTENANCE_WORK_MEM_MB}MB'
autovacuum_work_mem = '${PG_AUTOVACUUM_WORK_MEM_MB}MB'
max_connections = ${PG_MAX_CONNECTIONS}
EOF
grep -q '^host\s\+all\s\+all\s\+127.0.0.1/32\s\+scram-sha-256$' "${PG_CLUSTER_DIR}/pg_hba.conf" || printf '\nhost all all 127.0.0.1/32 scram-sha-256\n' >> "${PG_CLUSTER_DIR}/pg_hba.conf"
grep -q '^host\s\+all\s\+all\s\+::1/128\s\+scram-sha-256$' "${PG_CLUSTER_DIR}/pg_hba.conf" || printf 'host all all ::1/128 scram-sha-256\n' >> "${PG_CLUSTER_DIR}/pg_hba.conf"
python3 - "${PG_CLUSTER_DIR}/pg_hba.conf" "${PRIVATE_HBA_RULES}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
private_rules = [line for line in sys.argv[2].splitlines() if line.strip()]
start_marker = "# BEGIN GXP MANAGED PRIVATE POSTGRES ACCESS"
end_marker = "# END GXP MANAGED PRIVATE POSTGRES ACCESS"

content = path.read_text(encoding="utf-8")
lines = content.splitlines()
result: list[str] = []
in_block = False
for line in lines:
    if line == start_marker:
        in_block = True
        continue
    if line == end_marker:
        in_block = False
        continue
    if not in_block:
        result.append(line)
while result and result[-1] == "":
    result.pop()
if private_rules:
    if result:
        result.append("")
    result.append(start_marker)
    result.extend(private_rules)
    result.append(end_marker)
path.write_text("\n".join(result) + "\n", encoding="utf-8", newline="\n")
PY

pg_ctlcluster "${POSTGRES_MAJOR}" "${POSTGRES_CLUSTER_NAME}" restart
pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -d "${DB_NAME}" >/dev/null
AUTH_PROBE_RESULT="$(
  PGPASSWORD="${DB_PASSWORD}" psql \
    -v ON_ERROR_STOP=1 \
    --host "${DB_HOST}" \
    --port "${DB_PORT}" \
    --username "${DB_USER}" \
    --dbname "${DB_NAME}" \
    -Atqc "SELECT current_database() || E'\t' || current_user"
)"
[[ "${AUTH_PROBE_RESULT}" == "${DB_NAME}"$'\t'"${DB_USER}" ]] || fail "Authenticated PostgreSQL probe returned unexpected identity: ${AUTH_PROBE_RESULT}."
PG_VERSION_NUM="$(runuser -u postgres -- psql -v ON_ERROR_STOP=1 --dbname=postgres -Atqc 'SHOW server_version_num')"
PG_MAJOR="${PG_VERSION_NUM:0:${#PG_VERSION_NUM}-4}"
case ",${SUPPORTED_POSTGRES_MAJORS}," in
  *",${PG_MAJOR},"*) ;;
  *) fail "Unsupported PostgreSQL major version ${PG_MAJOR}. Supported majors: ${SUPPORTED_POSTGRES_MAJORS}." ;;
esac

echo "PostgreSQL configured for ${DB_NAME} / ${DB_USER} on cluster ${POSTGRES_MAJOR}/${POSTGRES_CLUSTER_NAME}."
