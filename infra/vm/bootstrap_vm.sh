#!/usr/bin/env bash
set -euo pipefail

GXP_USER="${GXP_USER:-gxp}"
APP_ROOT="${VM_APP_ROOT:-/opt/gxp}"
SRC_DIR="${VM_SRC_DIR:-${APP_ROOT}/src/GXP-QLCL}"
FRONTEND_DIST_DIR="${VM_FRONTEND_DIST_DIR:-${APP_ROOT}/frontend-dist}"
VENV_DIR="${VM_VENV_DIR:-${APP_ROOT}/venv}"
RUNTIME_ENV_DIR="$(dirname "${VM_RUNTIME_ENV_FILE:-/etc/gxp/runtime.env}")"
BACKUP_STAGING_DIR="${BACKUP_LOCAL_STAGING_DIR:-/var/backups/gxp-temp}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $1" >&2
    exit 1
  }
}

need_cmd apt-get

apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  git \
  gnupg \
  nginx \
  postgresql \
  postgresql-client \
  python3 \
  python3-venv \
  python3-pip \
  rsync

if ! id -u "${GXP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash "${GXP_USER}"
fi

install -d -m 0755 -o "${GXP_USER}" -g "${GXP_USER}" "${APP_ROOT}" "${APP_ROOT}/src" "${FRONTEND_DIST_DIR}" "${BACKUP_STAGING_DIR}"
install -d -m 0750 -o root -g "${GXP_USER}" "${RUNTIME_ENV_DIR}"
install -d -m 0755 -o "${GXP_USER}" -g "${GXP_USER}" "$(dirname "${VENV_DIR}")"

if [[ ! -d "${SRC_DIR}/.git" ]]; then
  echo "Clone repository manually or run:" >&2
  echo "git clone https://github.com/hahoangphuong/GXP-QLCL ${SRC_DIR}" >&2
fi

echo "VM bootstrap completed."
