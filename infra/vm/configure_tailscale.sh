#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/vm/common.sh
source "${SCRIPT_DIR}/common.sh"

TAILSCALE_AUTH_KEY="${TAILSCALE_AUTH_KEY:-}"
TAILSCALE_HOSTNAME="${TAILSCALE_HOSTNAME:-gxp-web-prod}"

require_root
need_cmd curl
need_cmd systemctl

if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

systemctl enable --now tailscaled
if tailscale status --json >/dev/null 2>&1; then
  tailscale status
  exit 0
fi

[[ -n "${TAILSCALE_AUTH_KEY}" ]] || {
  echo "ERROR: TAILSCALE_AUTH_KEY is required when Tailscale is not already connected." >&2
  exit 1
}
tailscale up --authkey="${TAILSCALE_AUTH_KEY}" --hostname="${TAILSCALE_HOSTNAME}" --ssh
tailscale status
