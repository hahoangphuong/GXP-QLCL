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
PG_SHARED_BUFFERS_MB="${PG_SHARED_BUFFERS_MB:-256}"
PG_EFFECTIVE_CACHE_SIZE_MB="${PG_EFFECTIVE_CACHE_SIZE_MB:-768}"
PG_WORK_MEM_MB="${PG_WORK_MEM_MB:-4}"
PG_MAINTENANCE_WORK_MEM_MB="${PG_MAINTENANCE_WORK_MEM_MB:-64}"
PG_AUTOVACUUM_WORK_MEM_MB="${PG_AUTOVACUUM_WORK_MEM_MB:-64}"
PG_MAX_CONNECTIONS="${PG_MAX_CONNECTIONS:-30}"

require_root
need_cmd psql
need_cmd createdb
need_cmd pg_isready
need_cmd systemctl
load_runtime_env "${VM_RUNTIME_ENV_FILE:-/etc/gxp/runtime.env}"
DB_NAME="${DB_NAME:-gxp_qlcl}"
DB_USER="${DB_USER:-gxp_app}"
DB_PASSWORD="${DB_PASSWORD:-}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"

[[ -n "${DB_PASSWORD}" ]] || {
  echo "ERROR: DB_PASSWORD is required." >&2
  exit 1
}
[[ "${DB_USER}" != "postgres" ]] || {
  echo "ERROR: DB_USER must not be postgres." >&2
  exit 1
}

POSTGRES_LISTEN_ADDRESS="${DB_HOST}"
if [[ "${POSTGRES_LISTEN_ADDRESS}" == "localhost" ]]; then
  POSTGRES_LISTEN_ADDRESS="127.0.0.1"
fi

runuser -u postgres -- psql \
  --set=db_user="${DB_USER}" \
  --set=db_password="${DB_PASSWORD}" \
  --dbname=postgres <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'db_user') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', :'db_user', :'db_password');
  ELSE
    EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'db_user', :'db_password');
  END IF;
END
$$;
SQL

if ! runuser -u postgres -- psql --set=db_name="${DB_NAME}" --dbname=postgres -Atqc "SELECT 1 FROM pg_database WHERE datname = :'db_name'" | grep -q '^1$'; then
  runuser -u postgres -- createdb --owner "${DB_USER}" "${DB_NAME}"
fi

PG_VERSION_DIR="$(find /etc/postgresql -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
[[ -n "${PG_VERSION_DIR}" ]] || {
  echo "ERROR: Could not locate /etc/postgresql/<version>." >&2
  exit 1
}
PG_CLUSTER_DIR="$(find "${PG_VERSION_DIR}" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
[[ -n "${PG_CLUSTER_DIR}" ]] || {
  echo "ERROR: Could not locate PostgreSQL cluster config directory." >&2
  exit 1
}

install -d -m 0755 "${PG_CLUSTER_DIR}/conf.d"
cat > "${PG_CLUSTER_DIR}/conf.d/90-gxp-vm.conf" <<EOF
listen_addresses = '${POSTGRES_LISTEN_ADDRESS}'
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

systemctl restart postgresql
pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -d "${DB_NAME}" >/dev/null

echo "PostgreSQL configured for ${DB_NAME} / ${DB_USER}."
