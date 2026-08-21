from __future__ import annotations

import os
import socket
from urllib.parse import urlparse


_PATCHED = False


def enable_socket_proxy_from_env(env: dict[str, str] | None = None) -> bool:
    global _PATCHED
    if _PATCHED:
        return True
    source = os.environ if env is None else env
    proxy_url = (source.get("TAILSCALE_SOCKS5_PROXY") or source.get("SOCKS5_PROXY_URL") or "").strip()
    if not proxy_url:
        return False
    parsed = urlparse(proxy_url)
    if parsed.scheme.lower() != "socks5":
        raise RuntimeError("Only socks5:// proxies are supported for bridge socket proxying.")
    if not parsed.hostname or not parsed.port:
        raise RuntimeError("SOCKS5 proxy URL must include host and port.")
    try:
        import socks
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("PySocks is required when TAILSCALE_SOCKS5_PROXY is configured.") from exc
    socks.set_default_proxy(
        socks.SOCKS5,
        parsed.hostname,
        parsed.port,
        username=parsed.username,
        password=parsed.password,
    )
    socket.socket = socks.socksocket
    _PATCHED = True
    return True
