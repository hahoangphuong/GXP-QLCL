#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/vm/common.sh
source "${SCRIPT_DIR}/common.sh"

GXP_USER="${GXP_USER:-gxp}"
GXP_GROUP="${VM_APP_GROUP:-${GXP_USER}}"
APP_ROOT="${VM_APP_ROOT:-/opt/gxp}"
SRC_DIR="${VM_SRC_DIR:-${APP_ROOT}/src/GXP-QLCL}"
BACKEND_RELEASES_DIR="${VM_BACKEND_RELEASES_DIR:-${APP_ROOT}/backend-releases}"
BACKEND_VENV_RELEASES_DIR="${VM_BACKEND_VENV_RELEASES_DIR:-${APP_ROOT}/backend-venvs}"
CURRENT_BACKEND_RELEASE_LINK="${VM_CURRENT_BACKEND_RELEASE_LINK:-${APP_ROOT}/current-backend}"
CURRENT_BACKEND_VENV_LINK="${VM_CURRENT_BACKEND_VENV_LINK:-${APP_ROOT}/current-venv}"
FRONTEND_DIST_DIR="${VM_FRONTEND_DIST_DIR:-${APP_ROOT}/frontend-dist}"
FRONTEND_RELEASES_DIR="${VM_FRONTEND_RELEASES_DIR:-${APP_ROOT}/frontend-releases}"
RUNTIME_ENV_DIR="$(dirname "${VM_RUNTIME_ENV_FILE:-/etc/gxp/runtime.env}")"
BACKUP_STAGING_DIR="${BACKUP_LOCAL_STAGING_DIR:-/var/backups/gxp-temp}"
PYTHON_SERIES="${VM_PYTHON_SERIES:-3.12}"
PYTHON_BIN="${VM_PYTHON_BIN:-/usr/bin/python3.12}"
NODE_MAJOR="${VM_NODE_MAJOR:-22}"
NODE_MIN_VERSION="${VM_NODE_MIN_VERSION:-22.12.0}"
COREPACK_VERSION="${VM_COREPACK_VERSION:-0.31.0}"
NODE_PACKAGE_MANAGER="${VM_NODE_PACKAGE_MANAGER:-pnpm@11.19.0}"
VM_SWAP_SIZE_GB="${VM_SWAP_SIZE_GB:-4}"
VM_SWAPPINESS="${VM_SWAPPINESS:-10}"
INSTALL_GCLOUD="${INSTALL_GCLOUD:-1}"
APT_PACKAGES=(
  ca-certificates
  curl
  git
  gnupg
  nginx
  postgresql
  postgresql-client
  procps
  "python${PYTHON_SERIES}"
  "python${PYTHON_SERIES}-venv"
  python3-pip
  rsync
  sudo
)

require_root
need_cmd apt-get
need_cmd bash
need_cmd curl
need_cmd gpg
need_cmd apt-cache

ensure_supported_python_packages() {
  apt-get update
  apt-cache show "python${PYTHON_SERIES}" >/dev/null 2>&1 || fail "Host image does not provide python${PYTHON_SERIES}. Recreate the VM with Ubuntu 24.04 LTS or another supported image that ships Python ${PYTHON_SERIES}."
  apt-cache show "python${PYTHON_SERIES}-venv" >/dev/null 2>&1 || fail "Host image does not provide python${PYTHON_SERIES}-venv. Recreate the VM with Ubuntu 24.04 LTS or another supported image that ships Python ${PYTHON_SERIES}."
}

validate_python_baseline() {
  [[ -x "${PYTHON_BIN}" ]] || fail "Supported production Python interpreter not found at ${PYTHON_BIN}. Recreate the VM with Ubuntu 24.04 LTS or another supported image that ships Python ${PYTHON_SERIES}."
  "${PYTHON_BIN}" - "${PYTHON_SERIES}" <<'PY'
import sys

expected = tuple(int(part) for part in sys.argv[1].split("."))
version = tuple(sys.version_info[:2])
if version != expected:
    raise SystemExit(1)
PY
}

install_nodejs() {
  if command -v node >/dev/null 2>&1; then
    local current_version
    current_version="$(node -p 'process.versions.node')"
    if CURRENT_VERSION="${current_version}" python3 - "${NODE_MIN_VERSION}" <<'PY'
import sys
import os

current = tuple(int(part) for part in os.environ["CURRENT_VERSION"].split("."))
required = tuple(int(part) for part in sys.argv[1].split("."))
raise SystemExit(0 if current >= required else 1)
PY
    then
      if ! command -v corepack >/dev/null 2>&1; then
        need_cmd npm
        npm install -g "corepack@${COREPACK_VERSION}"
      fi
      need_cmd corepack
      corepack enable
      corepack prepare "${NODE_PACKAGE_MANAGER}" --activate
      need_cmd pnpm
      [[ "$(pnpm --version)" == "${NODE_PACKAGE_MANAGER#pnpm@}" ]] || fail "pnpm version mismatch after bootstrap. Expected ${NODE_PACKAGE_MANAGER#pnpm@}."
      return
    fi
  fi

  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL "https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key" | gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
  . /etc/os-release
  printf 'deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_%s.x nodistro main\n' "${NODE_MAJOR}" > /etc/apt/sources.list.d/nodesource.list
  apt-get update
  apt-get install -y --no-install-recommends nodejs
  need_cmd node
  if ! command -v corepack >/dev/null 2>&1; then
    need_cmd npm
    npm install -g "corepack@${COREPACK_VERSION}"
  fi
  need_cmd corepack
  local installed_version
  installed_version="$(node -p 'process.versions.node')"
  INSTALLED_VERSION="${installed_version}" python3 - "${NODE_MIN_VERSION}" <<'PY'
import sys
import os

current = tuple(int(part) for part in os.environ["INSTALLED_VERSION"].split("."))
required = tuple(int(part) for part in sys.argv[1].split("."))
if current < required:
    raise SystemExit(1)
PY
  corepack enable
  corepack prepare "${NODE_PACKAGE_MANAGER}" --activate
  need_cmd pnpm
  [[ "$(pnpm --version)" == "${NODE_PACKAGE_MANAGER#pnpm@}" ]] || fail "pnpm version mismatch after bootstrap. Expected ${NODE_PACKAGE_MANAGER#pnpm@}."
}

install_gcloud() {
  if [[ "${INSTALL_GCLOUD}" != "1" ]]; then
    need_cmd gcloud
    return
  fi
  if command -v gcloud >/dev/null 2>&1; then
    return
  fi

  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL "https://packages.cloud.google.com/apt/doc/apt-key.gpg" | gpg --dearmor --yes -o /etc/apt/keyrings/google-cloud-cli.gpg
  printf 'deb [signed-by=/etc/apt/keyrings/google-cloud-cli.gpg] https://packages.cloud.google.com/apt cloud-sdk main\n' > /etc/apt/sources.list.d/google-cloud-cli.list
  apt-get update
  apt-get install -y --no-install-recommends google-cloud-cli
  need_cmd gcloud
}

configure_swap() {
  local swapfile="/swapfile"
  local desired_bytes=$(( VM_SWAP_SIZE_GB * 1024 * 1024 * 1024 ))
  local current_bytes="0"
  if [[ "${VM_SWAP_SIZE_GB}" -le 0 ]]; then
    return
  fi
  if [[ -f "${swapfile}" ]]; then
    current_bytes="$(stat -c '%s' "${swapfile}")"
    if [[ "${current_bytes}" != "${desired_bytes}" ]]; then
      fail "/swapfile exists with size ${current_bytes} bytes; expected ${desired_bytes}. Adjust manually or remove it before rerunning bootstrap."
    fi
  else
    if command -v fallocate >/dev/null 2>&1; then
      fallocate -l "${VM_SWAP_SIZE_GB}G" "${swapfile}"
    else
      dd if=/dev/zero of="${swapfile}" bs=1M count="$(( VM_SWAP_SIZE_GB * 1024 ))" status=progress
    fi
    chmod 0600 "${swapfile}"
    mkswap "${swapfile}" >/dev/null
  fi

  grep -qE '^/swapfile\s+none\s+swap\s+sw\s+0\s+0$' /etc/fstab || printf '/swapfile none swap sw 0 0\n' >> /etc/fstab
  if ! swapon --show=NAME --noheadings | grep -qx '/swapfile'; then
    swapon "${swapfile}"
  fi

  install -d -m 0755 /etc/sysctl.d
  printf 'vm.swappiness=%s\n' "${VM_SWAPPINESS}" > /etc/sysctl.d/60-gxp-vm.conf
  sysctl -p /etc/sysctl.d/60-gxp-vm.conf >/dev/null
  swapon --show
  free -h
}

ensure_supported_python_packages
apt-get install -y --no-install-recommends "${APT_PACKAGES[@]}"
validate_python_baseline

install_nodejs
install_gcloud
configure_swap

if ! getent group "${GXP_GROUP}" >/dev/null 2>&1; then
  groupadd --system "${GXP_GROUP}"
fi
if ! id -u "${GXP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash --gid "${GXP_GROUP}" "${GXP_USER}"
fi

install -d -m 0755 -o "${GXP_USER}" -g "${GXP_GROUP}" \
  "${APP_ROOT}" \
  "${APP_ROOT}/src" \
  "${BACKEND_RELEASES_DIR}" \
  "${BACKEND_VENV_RELEASES_DIR}" \
  "${FRONTEND_RELEASES_DIR}" \
  "${BACKUP_STAGING_DIR}"
install -d -m 0750 -o root -g "${GXP_GROUP}" "${RUNTIME_ENV_DIR}"

if [[ ! -e "${FRONTEND_DIST_DIR}" ]]; then
  empty_release="${FRONTEND_RELEASES_DIR}/empty"
  install -d -m 0755 -o "${GXP_USER}" -g "${GXP_GROUP}" "${empty_release}"
  ln -s "${empty_release}" "${FRONTEND_DIST_DIR}"
fi

if [[ ! -e "${CURRENT_BACKEND_RELEASE_LINK}" ]]; then
  ln -s "${SRC_DIR}" "${CURRENT_BACKEND_RELEASE_LINK}"
  chown -h "${GXP_USER}:${GXP_GROUP}" "${CURRENT_BACKEND_RELEASE_LINK}"
fi

if [[ -d "${APP_ROOT}" ]]; then
  chown -R "${GXP_USER}:${GXP_GROUP}" "${APP_ROOT}"
fi

if [[ ! -d "${SRC_DIR}/.git" ]]; then
  echo "Clone repository manually or run:" >&2
  echo "sudo -u ${GXP_USER} git clone https://github.com/hahoangphuong/GXP-QLCL ${SRC_DIR}" >&2
fi

echo "VM bootstrap completed."
