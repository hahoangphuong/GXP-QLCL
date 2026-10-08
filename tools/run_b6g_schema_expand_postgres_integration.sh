#!/usr/bin/env bash
# VM-only B6G migration gate. Never point this at rehearsal or production.
set -euo pipefail

: "${B6G_DISPOSABLE_DATABASE:?set a new disposable database name}"
case "$B6G_DISPOSABLE_DATABASE" in
  gxp_b6g_test_*) ;;
  *) echo "refusing non-disposable or protected database" >&2; exit 2 ;;
esac

SOCKET_HOST="${B6G_POSTGRES_SOCKET_HOST:-/var/run/postgresql}"
PYTHON_BIN="${B6G_PYTHON_BIN:-python3}"
DATABASE_URL="postgresql+psycopg://postgres@/${B6G_DISPOSABLE_DATABASE}?host=${SOCKET_HOST}"

dropdb --if-exists "$B6G_DISPOSABLE_DATABASE"
createdb "$B6G_DISPOSABLE_DATABASE"
trap 'dropdb --if-exists "$B6G_DISPOSABLE_DATABASE"' EXIT

# The test itself verifies 0016 -> 0017 -> 0016 -> 0017.
DATABASE_URL="$DATABASE_URL" "$PYTHON_BIN" -m alembic upgrade 20260915_0016
B6G_POSTGRES_INTEGRATION=1 DATABASE_URL="$DATABASE_URL" \
  "$PYTHON_BIN" -m pytest tests/test_b6g_schema_expand_foundation_postgres.py \
    -p no:cacheprovider -q
