#!/usr/bin/env bash
# VM-only B6H read-only PostgreSQL fence. Never targets rehearsal or production.
set -euo pipefail

: "${B6H_DISPOSABLE_DATABASE:?set a new disposable database name}"
case "$B6H_DISPOSABLE_DATABASE" in
  gxp_b6h_test_*) ;;
  *) echo "refusing non-disposable or protected database" >&2; exit 2 ;;
esac

SOCKET_HOST="${B6H_POSTGRES_SOCKET_HOST:-/var/run/postgresql}"
PYTHON_BIN="${B6H_PYTHON_BIN:-python3}"
DATABASE_URL="postgresql+psycopg://postgres@/${B6H_DISPOSABLE_DATABASE}?host=${SOCKET_HOST}"

dropdb --if-exists "$B6H_DISPOSABLE_DATABASE"
createdb "$B6H_DISPOSABLE_DATABASE"
trap 'dropdb --if-exists "$B6H_DISPOSABLE_DATABASE"' EXIT

DATABASE_URL="$DATABASE_URL" "$PYTHON_BIN" -m alembic upgrade 20260929_0017

B6H_POSTGRES_INTEGRATION=1 DATABASE_URL="$DATABASE_URL" \
  "$PYTHON_BIN" -m pytest tests/test_production_line_population_b6h_postgres.py -p no:cacheprovider -q
