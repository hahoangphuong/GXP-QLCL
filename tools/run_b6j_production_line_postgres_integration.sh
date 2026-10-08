#!/usr/bin/env bash
# Disposable-only B6J integration entrypoint.  It cannot target rehearsal.
set -euo pipefail

: "${B6J_DISPOSABLE_DATABASE:?set a disposable database name}"
# Use only simple PostgreSQL identifier characters. This name is embedded
# unescaped in a connection URL and passed to createdb/dropdb: it must have
# identical meaning in both places. PostgreSQL names are at most 63 bytes.
if [[ ! "${B6J_DISPOSABLE_DATABASE}" =~ ^gxp_b6j_test_[a-z0-9_]+$ ]] || (( ${#B6J_DISPOSABLE_DATABASE} > 63 )); then
  echo "B6J refuses invalid or non-disposable database name" >&2
  exit 2
fi

SOCKET_HOST="${B6J_POSTGRES_SOCKET_HOST:-/var/run/postgresql}"
PYTHON_BIN="${B6J_PYTHON_BIN:-python3}"
DATABASE_URL="postgresql+psycopg://postgres@/${B6J_DISPOSABLE_DATABASE}?host=${SOCKET_HOST}"

# Fail closed if the name already exists.  A cleanup trap is installed only
# after this process has successfully created its own disposable database.
createdb --host="$SOCKET_HOST" --username=postgres "${B6J_DISPOSABLE_DATABASE}"
trap 'dropdb --host="$SOCKET_HOST" --username=postgres --if-exists "${B6J_DISPOSABLE_DATABASE}"' EXIT

DATABASE_URL="${DATABASE_URL}" "${PYTHON_BIN}" -m alembic upgrade 20260929_0017
B6J_POSTGRES_INTEGRATION=1 DATABASE_URL="${DATABASE_URL}" \
  "${PYTHON_BIN}" -m pytest tests/test_production_line_population_b6j_postgres.py -p no:cacheprovider -q
