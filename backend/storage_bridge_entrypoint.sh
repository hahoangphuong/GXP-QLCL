#!/bin/sh
set -eu

if [ "${TAILSCALE_ENABLE:-0}" = "1" ]; then
  if [ -z "${TAILSCALE_AUTHKEY:-}" ]; then
    echo "TAILSCALE_AUTHKEY is required when TAILSCALE_ENABLE=1" >&2
    exit 1
  fi
  /app/tailscaled \
    --tun=userspace-networking \
    --socks5-server=127.0.0.1:1055 \
    --state=mem: &
  /app/tailscale up \
    --auth-key="${TAILSCALE_AUTHKEY}" \
    --hostname="${TAILSCALE_HOSTNAME:-gxp-storage-bridge}"
  export TAILSCALE_SOCKS5_PROXY="${TAILSCALE_SOCKS5_PROXY:-socks5://127.0.0.1:1055}"
fi

exec uvicorn backend.storage_bridge_main:app --host 0.0.0.0 --port "${PORT:-8080}"
