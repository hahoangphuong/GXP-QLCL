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
SUPPORTED_POSTGRES_MAJORS="${VM_SUPPORTED_POSTGRES_MAJORS:-17,18}"
POSTGRES_MAJOR="${VM_POSTGRES_MAJOR:-18}"
POSTGRES_CLUSTER_NAME="${VM_POSTGRES_CLUSTER_NAME:-main}"
EXPECTED_PROJECT_ID="${VM_EXPECTED_PROJECT_ID:-}"
EXPECTED_INSTANCE_NAME="${VM_EXPECTED_INSTANCE_NAME:-}"
EXPECTED_ZONE="${VM_EXPECTED_ZONE:-}"
APT_KEYRINGS_DIR="${VM_APT_KEYRINGS_DIR:-/etc/apt/keyrings}"
APT_SOURCES_DIR="${VM_APT_SOURCES_DIR:-/etc/apt/sources.list.d}"
SYSCTL_DIR="${VM_SYSCTL_DIR:-/etc/sysctl.d}"
SYSCTL_FILE="${VM_SYSCTL_FILE:-${SYSCTL_DIR}/60-gxp-vm.conf}"
FSTAB_FILE="${VM_FSTAB_FILE:-/etc/fstab}"
SWAPFILE_PATH="${VM_SWAPFILE_PATH:-/swapfile}"
OS_RELEASE_FILE="${VM_OS_RELEASE_FILE:-/etc/os-release}"
BOOTSTRAP_MINIMAL_APT_PACKAGES=(
  ca-certificates
  coreutils
  curl
  gnupg
  mount
  procps
  util-linux
)
APT_PACKAGES=(
  git
  nginx
  "python${PYTHON_SERIES}"
  "python${PYTHON_SERIES}-venv"
  python3-pip
  rsync
  sudo
  "postgresql-${POSTGRES_MAJOR}"
  "postgresql-client-${POSTGRES_MAJOR}"
)

require_root_for_bootstrap() {
  if [[ "${BOOTSTRAP_UNSAFE_SKIP_ROOT_CHECK:-0}" == "1" ]]; then
    return
  fi
  require_root
}

ensure_stage0_commands() {
  need_cmd bash
  need_cmd apt-get
  need_cmd apt-cache
  [[ -x "${PYTHON_BIN}" ]] || fail "Supported production Python interpreter not found at ${PYTHON_BIN}. Recreate the VM with Ubuntu 24.04 LTS or another supported image that ships Python ${PYTHON_SERIES}."
}

ensure_dir() {
  local path="$1"
  local mode="$2"
  local owner="${3:-}"
  local group="${4:-}"

  mkdir -p "${path}"
  chmod "${mode}" "${path}"
  if [[ -n "${owner}" && -n "${group}" ]]; then
    maybe_chown "${owner}:${group}" "${path}"
  fi
}

maybe_chown() {
  if [[ "${BOOTSTRAP_UNSAFE_SKIP_ROOT_CHECK:-0}" == "1" ]]; then
    return
  fi
  chown "$@"
}

create_link() {
  local target="$1"
  local link_path="$2"
  if [[ "${BOOTSTRAP_UNSAFE_SKIP_ROOT_CHECK:-0}" == "1" ]]; then
    mkdir -p "$(dirname "${link_path}")"
    printf '%s\n' "${target}" > "${link_path}"
    return
  fi
  ln -s "${target}" "${link_path}"
}

validate_supported_postgres_major() {
  case ",${SUPPORTED_POSTGRES_MAJORS}," in
    *",${POSTGRES_MAJOR},"*) ;;
    *) fail "VM_POSTGRES_MAJOR=${POSTGRES_MAJOR} is unsupported. Supported majors: ${SUPPORTED_POSTGRES_MAJORS}." ;;
  esac
}

ensure_not_cloud_shell() {
  if [[ "${BOOTSTRAP_UNSAFE_ALLOW_CLOUD_SHELL:-0}" == "1" ]]; then
    return
  fi
  if [[ -n "${DEVSHELL_PROJECT_ID:-}" || -n "${CLOUD_SHELL:-}" ]]; then
    fail "bootstrap_vm.sh must run on the target Compute Engine VM, not Cloud Shell."
  fi
}

metadata_value() {
  local path="$1"
  "${PYTHON_BIN}" - "$path" <<'PY'
import os
import sys
import urllib.error
import urllib.request

base_url = os.environ.get("VM_METADATA_BASE_URL", "http://metadata.google.internal/computeMetadata/v1").rstrip("/")
path = sys.argv[1].lstrip("/")
request = urllib.request.Request(
    f"{base_url}/{path}",
    headers={"Metadata-Flavor": "Google"},
)
try:
    with urllib.request.urlopen(request, timeout=1.5) as response:
        print(response.read().decode("utf-8").strip())
except (OSError, urllib.error.URLError, TimeoutError):
    raise SystemExit(2)
PY
}

validate_compute_engine_identity() {
  local instance_name=""
  local project_id=""
  local zone_path=""
  local service_account=""

  if instance_name="$(metadata_value "instance/name" 2>/dev/null)"; then
    project_id="$(metadata_value "project/project-id" 2>/dev/null || true)"
    zone_path="$(metadata_value "instance/zone" 2>/dev/null || true)"
    service_account="$(metadata_value "instance/service-accounts/default/email" 2>/dev/null || true)"
    local zone="${zone_path##*/}"
    echo "Detected Compute Engine instance: ${instance_name}" >&2
    echo "Detected Compute Engine project: ${project_id:-unknown}" >&2
    echo "Detected Compute Engine zone: ${zone:-unknown}" >&2
    echo "Detected Compute Engine service account: ${service_account:-unknown}" >&2

    [[ -z "${EXPECTED_PROJECT_ID}" || "${project_id}" == "${EXPECTED_PROJECT_ID}" ]] || fail "Compute Engine project mismatch. Expected ${EXPECTED_PROJECT_ID}, got ${project_id}."
    [[ -z "${EXPECTED_INSTANCE_NAME}" || "${instance_name}" == "${EXPECTED_INSTANCE_NAME}" ]] || fail "Compute Engine instance mismatch. Expected ${EXPECTED_INSTANCE_NAME}, got ${instance_name}."
    [[ -z "${EXPECTED_ZONE}" || "${zone}" == "${EXPECTED_ZONE}" ]] || fail "Compute Engine zone mismatch. Expected ${EXPECTED_ZONE}, got ${zone}."
    return
  fi

  if [[ -n "${EXPECTED_PROJECT_ID}" || -n "${EXPECTED_INSTANCE_NAME}" || -n "${EXPECTED_ZONE}" ]]; then
    fail "Could not verify Compute Engine metadata for the expected VM identity. Run bootstrap on the target VM or unset VM_EXPECTED_* overrides."
  fi
}

ensure_supported_python_packages() {
  apt-get update
  apt-cache show "python${PYTHON_SERIES}" >/dev/null 2>&1 || fail "Host image does not provide python${PYTHON_SERIES}. Recreate the VM with Ubuntu 24.04 LTS or another supported image that ships Python ${PYTHON_SERIES}."
  apt-cache show "python${PYTHON_SERIES}-venv" >/dev/null 2>&1 || fail "Host image does not provide python${PYTHON_SERIES}-venv. Recreate the VM with Ubuntu 24.04 LTS or another supported image that ships Python ${PYTHON_SERIES}."
}

validate_python_baseline() {
  "${PYTHON_BIN}" - "${PYTHON_SERIES}" <<'PY'
import sys

expected = tuple(int(part) for part in sys.argv[1].split("."))
version = tuple(sys.version_info[:2])
if version != expected:
    raise SystemExit(1)
PY
}

install_minimal_bootstrap_prerequisites() {
  apt-get install -y --no-install-recommends "${BOOTSTRAP_MINIMAL_APT_PACKAGES[@]}"
  need_cmd curl
  need_cmd gpg
  need_cmd stat
  need_cmd swapon
  need_cmd mkswap
  need_cmd sysctl
  need_cmd free
  need_cmd fallocate
}

ensure_pgdg_repository() {
  apt-cache show "postgresql-${POSTGRES_MAJOR}" >/dev/null 2>&1 && return

  [[ -f "${OS_RELEASE_FILE}" ]] || fail "OS release file not found: ${OS_RELEASE_FILE}"
  # shellcheck disable=SC1090
  . "${OS_RELEASE_FILE}"
  [[ "${ID:-}" == "ubuntu" ]] || fail "PGDG bootstrap is only supported on Ubuntu hosts. Current ID=${ID:-unknown}."
  [[ -n "${VERSION_CODENAME:-}" ]] || fail "VERSION_CODENAME is missing from ${OS_RELEASE_FILE}."

  ensure_dir "${APT_KEYRINGS_DIR}" 0755
  ensure_dir "${APT_SOURCES_DIR}" 0755
  curl -fsSL "https://www.postgresql.org/media/keys/ACCC4CF8.asc" | gpg --dearmor --yes -o "${APT_KEYRINGS_DIR}/postgresql.gpg"
  printf 'deb [signed-by=%s/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' "${APT_KEYRINGS_DIR}" "${VERSION_CODENAME}" > "${APT_SOURCES_DIR}/pgdg.list"
  apt-get update
  apt-cache show "postgresql-${POSTGRES_MAJOR}" >/dev/null 2>&1 || fail "Requested PostgreSQL package postgresql-${POSTGRES_MAJOR} is unavailable even after configuring PGDG."
}

install_postgresql_packages() {
  apt-get install -y --no-install-recommends "${APT_PACKAGES[@]}"
  need_cmd pg_lsclusters
  need_cmd pg_createcluster
}

ensure_postgres_cluster_state() {
  local clusters=()
  mapfile -t clusters < <(pg_lsclusters --no-header 2>/dev/null || true)

  if (( ${#clusters[@]} == 0 )); then
    pg_createcluster "${POSTGRES_MAJOR}" "${POSTGRES_CLUSTER_NAME}" >/dev/null
    mapfile -t clusters < <(pg_lsclusters --no-header 2>/dev/null || true)
  fi

  local matching_clusters=0
  local unexpected_clusters=()
  local line version name
  for line in "${clusters[@]}"; do
    [[ -n "${line}" ]] || continue
    read -r version name _ <<<"${line}"
    if [[ "${version}" == "${POSTGRES_MAJOR}" && "${name}" == "${POSTGRES_CLUSTER_NAME}" ]]; then
      matching_clusters=$(( matching_clusters + 1 ))
    else
      unexpected_clusters+=("${version}/${name}")
    fi
  done

  (( ${#unexpected_clusters[@]} == 0 )) || fail "Unexpected PostgreSQL clusters detected: ${unexpected_clusters[*]}. Refusing to continue. Remove or reconcile stray clusters manually."
  [[ "${matching_clusters}" == "1" ]] || fail "Expected exactly one PostgreSQL cluster ${POSTGRES_MAJOR}/${POSTGRES_CLUSTER_NAME}, found ${matching_clusters}."
}

install_nodejs() {
  if command -v node >/dev/null 2>&1; then
    local current_version
    current_version="$(node -p 'process.versions.node')"
    if CURRENT_VERSION="${current_version}" "${PYTHON_BIN}" - "${NODE_MIN_VERSION}" <<'PY'
import os
import sys

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

  ensure_dir "${APT_KEYRINGS_DIR}" 0755
  ensure_dir "${APT_SOURCES_DIR}" 0755
  curl -fsSL "https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key" | gpg --dearmor --yes -o "${APT_KEYRINGS_DIR}/nodesource.gpg"
  printf 'deb [signed-by=%s/nodesource.gpg] https://deb.nodesource.com/node_%s.x nodistro main\n' "${APT_KEYRINGS_DIR}" "${NODE_MAJOR}" > "${APT_SOURCES_DIR}/nodesource.list"
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
  INSTALLED_VERSION="${installed_version}" "${PYTHON_BIN}" - "${NODE_MIN_VERSION}" <<'PY'
import os
import sys

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

  ensure_dir "${APT_KEYRINGS_DIR}" 0755
  ensure_dir "${APT_SOURCES_DIR}" 0755
  curl -fsSL "https://packages.cloud.google.com/apt/doc/apt-key.gpg" | gpg --dearmor --yes -o "${APT_KEYRINGS_DIR}/google-cloud-cli.gpg"
  printf 'deb [signed-by=%s/google-cloud-cli.gpg] https://packages.cloud.google.com/apt cloud-sdk main\n' "${APT_KEYRINGS_DIR}" > "${APT_SOURCES_DIR}/google-cloud-cli.list"
  apt-get update
  apt-get install -y --no-install-recommends google-cloud-cli
  need_cmd gcloud
}

configure_swap() {
  need_cmd swapon
  need_cmd mkswap
  need_cmd sysctl
  need_cmd free
  need_cmd stat
  local desired_bytes=$(( VM_SWAP_SIZE_GB * 1024 * 1024 * 1024 ))
  local current_bytes="0"
  if [[ "${VM_SWAP_SIZE_GB}" -le 0 ]]; then
    return
  fi
  if [[ -f "${SWAPFILE_PATH}" ]]; then
    current_bytes="$(stat -c '%s' "${SWAPFILE_PATH}")"
    if [[ "${current_bytes}" != "${desired_bytes}" ]]; then
      fail "${SWAPFILE_PATH} exists with size ${current_bytes} bytes; expected ${desired_bytes}. Adjust manually or remove it before rerunning bootstrap."
    fi
  else
    if command -v fallocate >/dev/null 2>&1; then
      fallocate -l "${VM_SWAP_SIZE_GB}G" "${SWAPFILE_PATH}"
    else
      dd if=/dev/zero of="${SWAPFILE_PATH}" bs=1M count="$(( VM_SWAP_SIZE_GB * 1024 ))" status=progress
    fi
    chmod 0600 "${SWAPFILE_PATH}"
    mkswap "${SWAPFILE_PATH}" >/dev/null
  fi

  grep -qE "^${SWAPFILE_PATH//\//\\/}\\s+none\\s+swap\\s+sw\\s+0\\s+0$" "${FSTAB_FILE}" || printf '%s none swap sw 0 0\n' "${SWAPFILE_PATH}" >> "${FSTAB_FILE}"
  if ! swapon --show=NAME --noheadings | grep -qx "${SWAPFILE_PATH}"; then
    swapon "${SWAPFILE_PATH}"
  fi

  ensure_dir "${SYSCTL_DIR}" 0755
  printf 'vm.swappiness=%s\n' "${VM_SWAPPINESS}" > "${SYSCTL_FILE}"
  sysctl -p "${SYSCTL_FILE}" >/dev/null
  swapon --show
  free -h
}

require_root_for_bootstrap
ensure_stage0_commands
validate_supported_postgres_major
ensure_not_cloud_shell
validate_compute_engine_identity
ensure_supported_python_packages
validate_python_baseline
install_minimal_bootstrap_prerequisites
configure_swap
ensure_pgdg_repository
install_postgresql_packages
ensure_postgres_cluster_state
install_nodejs
install_gcloud

if ! getent group "${GXP_GROUP}" >/dev/null 2>&1; then
  groupadd --system "${GXP_GROUP}"
fi
if ! id -u "${GXP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash --gid "${GXP_GROUP}" "${GXP_USER}"
fi

ensure_dir "${APP_ROOT}" 0755 "${GXP_USER}" "${GXP_GROUP}"
ensure_dir "${APP_ROOT}/src" 0755 "${GXP_USER}" "${GXP_GROUP}"
ensure_dir "${BACKEND_RELEASES_DIR}" 0755 "${GXP_USER}" "${GXP_GROUP}"
ensure_dir "${BACKEND_VENV_RELEASES_DIR}" 0755 "${GXP_USER}" "${GXP_GROUP}"
ensure_dir "${FRONTEND_RELEASES_DIR}" 0755 "${GXP_USER}" "${GXP_GROUP}"
ensure_dir "${BACKUP_STAGING_DIR}" 0755 "${GXP_USER}" "${GXP_GROUP}"
ensure_dir "${RUNTIME_ENV_DIR}" 0750 root "${GXP_GROUP}"

if [[ ! -e "${FRONTEND_DIST_DIR}" ]]; then
  empty_release="${FRONTEND_RELEASES_DIR}/empty"
  ensure_dir "${empty_release}" 0755 "${GXP_USER}" "${GXP_GROUP}"
  create_link "${empty_release}" "${FRONTEND_DIST_DIR}"
fi

if [[ ! -e "${CURRENT_BACKEND_RELEASE_LINK}" ]]; then
  create_link "${SRC_DIR}" "${CURRENT_BACKEND_RELEASE_LINK}"
  maybe_chown -h "${GXP_USER}:${GXP_GROUP}" "${CURRENT_BACKEND_RELEASE_LINK}"
fi

if [[ -d "${APP_ROOT}" ]]; then
  maybe_chown -R "${GXP_USER}:${GXP_GROUP}" "${APP_ROOT}"
fi

if [[ ! -d "${SRC_DIR}/.git" ]]; then
  echo "Clone repository manually or run:" >&2
  echo "sudo -u ${GXP_USER} git clone https://github.com/hahoangphuong/GXP-QLCL ${SRC_DIR}" >&2
fi

echo "VM bootstrap completed."
