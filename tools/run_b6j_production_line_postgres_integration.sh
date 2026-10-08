#!/usr/bin/env bash
# Disposable-only B6J integration entrypoint.  It cannot target rehearsal.
set -euo pipefail

: "${B6J_DISPOSABLE_DATABASE:?set a disposable database name}"
case "${B6J_DISPOSABLE_DATABASE}" in
  gxp_b6j_test_*) ;;
  *) echo "B6J refuses non-disposable database" >&2; exit 2 ;;
esac

SOCKET_HOST="${B6J_POSTGRES_SOCKET_HOST:-/var/run/postgresql}"
PYTHON_BIN="${B6J_PYTHON_BIN:-python3}"
DATABASE_URL="postgresql+psycopg://postgres@/${B6J_DISPOSABLE_DATABASE}?host=${SOCKET_HOST}"

dropdb --if-exists "${B6J_DISPOSABLE_DATABASE}"
createdb "${B6J_DISPOSABLE_DATABASE}"
trap 'dropdb --if-exists "${B6J_DISPOSABLE_DATABASE}"' EXIT

DATABASE_URL="${DATABASE_URL}" "${PYTHON_BIN}" -m alembic upgrade 20260929_0017
B6J_POSTGRES_INTEGRATION=1 DATABASE_URL="${DATABASE_URL}" \
  "${PYTHON_BIN}" -m pytest tests/test_production_line_population_b6j_postgres.py -p no:cacheprovider -q
