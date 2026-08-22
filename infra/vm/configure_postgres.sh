#!/usr/bin/env bash
set -euo pipefail

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

sudo -u postgres psql postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', '${DB_USER}', '${DB_PASSWORD}');
  ELSE
    EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', '${DB_USER}', '${DB_PASSWORD}');
  END IF;
END
\$\$;
SQL

sudo -u postgres psql postgres -tc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | grep -q 1 || \
  sudo -u postgres createdb --owner "${DB_USER}" "${DB_NAME}"

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

sed -i "s/^#\\?listen_addresses.*/listen_addresses = '${DB_HOST}'/" "${PG_CLUSTER_DIR}/postgresql.conf"
grep -q '^host\s\+all\s\+all\s\+127.0.0.1/32\s\+scram-sha-256$' "${PG_CLUSTER_DIR}/pg_hba.conf" || \
  printf '\nhost all all 127.0.0.1/32 scram-sha-256\n' >> "${PG_CLUSTER_DIR}/pg_hba.conf"

systemctl restart postgresql
pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -d "${DB_NAME}" >/dev/null

echo "PostgreSQL configured for ${DB_NAME} / ${DB_USER}."
