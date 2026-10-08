#!/usr/bin/env bash
# VM-only B6G migration gate. Never point this at rehearsal or production.
set -euo pipefail

: "${B6G_DISPOSABLE_DATABASE:?set a new disposable database name}"
# Reject URL delimiters and invalid PostgreSQL names before createdb.
# The exact same identifier must be used for creation, URL and cleanup.
if [[ ! "$B6G_DISPOSABLE_DATABASE" =~ ^gxp_b6g_test_[a-z0-9_]+$ ]] || (( ${#B6G_DISPOSABLE_DATABASE} > 63 )); then
  echo "refusing invalid or non-disposable database name" >&2
  exit 2
fi

SOCKET_HOST="${B6G_POSTGRES_SOCKET_HOST:-/var/run/postgresql}"
PYTHON_BIN="${B6G_PYTHON_BIN:-python3}"
DATABASE_URL="postgresql+psycopg://postgres@/${B6G_DISPOSABLE_DATABASE}?host=${SOCKET_HOST}"

# Fail closed if the name already exists.  A cleanup trap is installed only
# after this process has successfully created its own disposable database.
createdb --host="$SOCKET_HOST" --username=postgres "$B6G_DISPOSABLE_DATABASE"
trap 'dropdb --host="$SOCKET_HOST" --username=postgres --if-exists "$B6G_DISPOSABLE_DATABASE"' EXIT

# The test itself verifies 0016 -> 0017 -> 0016 -> 0017.
DATABASE_URL="$DATABASE_URL" "$PYTHON_BIN" -m alembic upgrade 20260915_0016
B6G_POSTGRES_INTEGRATION=1 DATABASE_URL="$DATABASE_URL" \
  "$PYTHON_BIN" -m pytest tests/test_b6g_schema_expand_foundation_postgres.py \
    -p no:cacheprovider -q
