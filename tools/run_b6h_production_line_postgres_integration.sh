#!/usr/bin/env bash
# VM-only B6H read-only PostgreSQL fence. Never targets rehearsal or production.
set -euo pipefail

: "${B6H_DISPOSABLE_DATABASE:?set a new disposable database name}"
# Reject URL delimiters and invalid PostgreSQL names before createdb.
# The exact same identifier must be used for creation, URL and cleanup.
if [[ ! "$B6H_DISPOSABLE_DATABASE" =~ ^gxp_b6h_test_[a-z0-9_]+$ ]] || (( ${#B6H_DISPOSABLE_DATABASE} > 63 )); then
  echo "refusing invalid or non-disposable database name" >&2
  exit 2
fi

SOCKET_HOST="${B6H_POSTGRES_SOCKET_HOST:-/var/run/postgresql}"
PYTHON_BIN="${B6H_PYTHON_BIN:-python3}"
DATABASE_URL="postgresql+psycopg://postgres@/${B6H_DISPOSABLE_DATABASE}?host=${SOCKET_HOST}"

# Fail closed if the name already exists.  A cleanup trap is installed only
# after this process has successfully created its own disposable database.
createdb --host="$SOCKET_HOST" --username=postgres "$B6H_DISPOSABLE_DATABASE"
trap 'dropdb --host="$SOCKET_HOST" --username=postgres --if-exists "$B6H_DISPOSABLE_DATABASE"' EXIT

DATABASE_URL="$DATABASE_URL" "$PYTHON_BIN" -m alembic upgrade 20260929_0017

B6H_POSTGRES_INTEGRATION=1 DATABASE_URL="$DATABASE_URL" \
  "$PYTHON_BIN" -m pytest tests/test_production_line_population_b6h_postgres.py -p no:cacheprovider -q
