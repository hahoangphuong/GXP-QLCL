#!/usr/bin/env bash
# VM-only disposable PostgreSQL gate.  Never point this at rehearsal.
set -euo pipefail

: "${B6B_DISPOSABLE_DATABASE:?set a new disposable database name}"
case "$B6B_DISPOSABLE_DATABASE" in
  gxp_b6b_test_*) ;;
  *) echo "refusing non-disposable or protected database" >&2; exit 2 ;;
esac

SOCKET_HOST="${B6B_POSTGRES_SOCKET_HOST:-/var/run/postgresql}"
PYTHON_BIN="${B6B_PYTHON_BIN:-python3}"
DATABASE_URL="postgresql+psycopg://postgres@/${B6B_DISPOSABLE_DATABASE}?host=${SOCKET_HOST}"

# Requires separate operational approval because these commands create and
# drop a disposable database.  They never target the rehearsal database.
dropdb --if-exists "$B6B_DISPOSABLE_DATABASE"
createdb "$B6B_DISPOSABLE_DATABASE"
trap 'dropdb --if-exists "$B6B_DISPOSABLE_DATABASE"' EXIT

DATABASE_URL="$DATABASE_URL" "$PYTHON_BIN" -m alembic upgrade 20260914_0015
# This module is PostgreSQL-only: it seeds a minimal owner topology and proves
# real row locking, commit, rollback, stale-write and reconciliation behavior.
B6B_POSTGRES_INTEGRATION=1 DATABASE_URL="$DATABASE_URL" \
  "$PYTHON_BIN" -m pytest tests/test_apply_db_ktra_repeatable_v2_postgres.py \
    -m b6b_postgres_integration -q
