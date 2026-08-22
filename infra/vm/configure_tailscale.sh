#!/usr/bin/env bash
set -euo pipefail

TAILSCALE_AUTH_KEY="${TAILSCALE_AUTH_KEY:-}"
TAILSCALE_HOSTNAME="${TAILSCALE_HOSTNAME:-gxp-web-prod}"

[[ -n "${TAILSCALE_AUTH_KEY}" ]] || {
  echo "ERROR: TAILSCALE_AUTH_KEY is required." >&2
  exit 1
}

if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

systemctl enable --now tailscaled
tailscale up --authkey="${TAILSCALE_AUTH_KEY}" --hostname="${TAILSCALE_HOSTNAME}" --ssh
tailscale status
