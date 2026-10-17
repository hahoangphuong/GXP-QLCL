from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import HTTPException, Request


BRIDGE_AUTH_MODE_GOOGLE_OIDC = "google_oidc"
BRIDGE_AUTH_MODE_HMAC_JWT = "hmac_jwt"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    # No padded, non-URL-safe or ambiguous encodings in our issued tokens.
    # Reject before decoding: permissive Base64 decoders otherwise ignore
    # arbitrary invalid characters.
    if not re.fullmatch(r"[A-Za-z0-9_-]+", raw):
        raise ValueError("Malformed Base64URL token component.")
    try:
        decoded = base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Malformed Base64URL token component.") from exc
    if _b64url_encode(decoded) != raw:
        raise ValueError("Noncanonical Base64URL token component.")
    return decoded


@dataclass(frozen=True)
class BridgeAuthConfig:
    mode: str
    audience: str
    client_id: str | None = None
    issuer: str | None = None
    signing_key: str | None = None
    ttl_seconds: int = 300


def load_bridge_auth_config(env: dict[str, str] | None = None) -> BridgeAuthConfig:
    source = os.environ if env is None else env
    mode = source.get("BRIDGE_AUTH_MODE", "").strip().lower()
    audience = source.get("STORAGE_BRIDGE_AUTH_AUDIENCE", "").strip()
    client_id = source.get("STORAGE_BRIDGE_CLIENT_ID", "").strip() or None
    issuer = source.get("STORAGE_BRIDGE_TOKEN_ISSUER", "").strip() or None
    signing_key = source.get("STORAGE_BRIDGE_SIGNING_KEY", "").strip() or None
    ttl_raw = source.get("STORAGE_BRIDGE_TOKEN_TTL_SECONDS", "").strip() or "300"

    if mode not in {BRIDGE_AUTH_MODE_GOOGLE_OIDC, BRIDGE_AUTH_MODE_HMAC_JWT}:
        raise RuntimeError("BRIDGE_AUTH_MODE must be 'google_oidc' or 'hmac_jwt'.")
    if not audience:
        raise RuntimeError("Missing STORAGE_BRIDGE_AUTH_AUDIENCE.")
    if mode == BRIDGE_AUTH_MODE_GOOGLE_OIDC:
        return BridgeAuthConfig(mode=mode, audience=audience)
    if not signing_key:
        raise RuntimeError("Missing STORAGE_BRIDGE_SIGNING_KEY for BRIDGE_AUTH_MODE=hmac_jwt.")
    if not issuer:
        raise RuntimeError("Missing STORAGE_BRIDGE_TOKEN_ISSUER for BRIDGE_AUTH_MODE=hmac_jwt.")
    if not client_id:
        raise RuntimeError("Missing STORAGE_BRIDGE_CLIENT_ID for BRIDGE_AUTH_MODE=hmac_jwt.")
    return BridgeAuthConfig(
        mode=mode,
        audience=audience,
        client_id=client_id,
        issuer=issuer,
        signing_key=signing_key,
        ttl_seconds=max(30, int(ttl_raw)),
    )


def issue_bridge_token(config: BridgeAuthConfig) -> str:
    if config.mode != BRIDGE_AUTH_MODE_HMAC_JWT:
        raise RuntimeError("HMAC token issuance is only valid for BRIDGE_AUTH_MODE=hmac_jwt.")
    if config.signing_key is None or config.issuer is None or config.client_id is None:
        raise RuntimeError("Incomplete HMAC bridge auth configuration.")
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": config.issuer,
        "sub": config.client_id,
        "aud": config.audience,
        "iat": now,
        "exp": now + config.ttl_seconds,
    }
    encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(config.signing_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64url_encode(signature)}"


def verify_bridge_hmac_token(token: str, config: BridgeAuthConfig) -> dict[str, object]:
    if config.mode != BRIDGE_AUTH_MODE_HMAC_JWT:
        raise HTTPException(status_code=401, detail="Bridge auth mode mismatch.")
    if config.signing_key is None or config.issuer is None or config.client_id is None:
        raise HTTPException(status_code=503, detail="Storage bridge HMAC auth is not configured.")
    if len(token) > 8192:
        raise HTTPException(status_code=401, detail="Malformed storage bridge token.")
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        signature = _b64url_decode(encoded_signature)
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(status_code=401, detail="Malformed storage bridge token.") from exc
    expected_signature = hmac.new(config.signing_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=401, detail="Invalid storage bridge token signature.")
    try:
        header = json.loads(_b64url_decode(encoded_header).decode("utf-8"))
        payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Malformed storage bridge token.") from exc
    if not isinstance(header, dict) or header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise HTTPException(status_code=401, detail="Unsupported storage bridge token header.")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=401, detail="Malformed storage bridge token payload.")
    if payload.get("iss") != config.issuer:
        raise HTTPException(status_code=401, detail="Invalid storage bridge token issuer.")
    if payload.get("aud") != config.audience:
        raise HTTPException(status_code=401, detail="Invalid storage bridge token audience.")
    if payload.get("sub") != config.client_id:
        raise HTTPException(status_code=401, detail="Invalid storage bridge token subject.")
    iat, exp = payload.get("iat"), payload.get("exp")
    if type(iat) is not int or type(exp) is not int:
        raise HTTPException(status_code=401, detail="Invalid storage bridge token timestamps.")
    now = int(time.time())
    if iat > now + 30 or exp <= iat or exp - iat > config.ttl_seconds:
        raise HTTPException(status_code=401, detail="Invalid storage bridge token lifetime.")
    if exp <= now:
        raise HTTPException(status_code=401, detail="Expired storage bridge token.")
    return payload


def verify_bridge_token(token: str, config: BridgeAuthConfig) -> dict[str, object]:
    if config.mode == BRIDGE_AUTH_MODE_HMAC_JWT:
        return verify_bridge_hmac_token(token, config)
    return verify_google_oidc_token(token, config)


def verify_google_oidc_token(
    token: str,
    config: BridgeAuthConfig,
    *,
    verifier: Callable[[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if config.mode != BRIDGE_AUTH_MODE_GOOGLE_OIDC:
        raise HTTPException(status_code=401, detail="Bridge auth mode mismatch.")
    verify_fn = verifier or _verify_google_oidc_token
    return verify_fn(token, config.audience)


def _verify_google_oidc_token(token: str, expected_audience: str) -> dict[str, Any]:
    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2 import id_token
    except (ModuleNotFoundError, ImportError) as exc:
        raise HTTPException(
            status_code=503,
            detail="google-auth and requests are required for BRIDGE_AUTH_MODE=google_oidc.",
        ) from exc
    try:
        claims = id_token.verify_oauth2_token(token, GoogleAuthRequest(), audience=expected_audience)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=401, detail="Invalid Google OIDC token.") from exc
    if not isinstance(claims, dict):
        raise HTTPException(status_code=401, detail="Invalid Google OIDC token payload.")
    return claims


def require_bridge_request_auth(request: Request) -> dict[str, object]:
    config = getattr(request.app.state, "bridge_auth_config", None)
    if config is None:
        raise HTTPException(status_code=503, detail="Storage bridge auth is not configured.")
    authorization = (request.headers.get("Authorization") or "").strip()
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing storage bridge bearer token.")
    token = authorization[len("Bearer ") :].strip()
    if config.mode == BRIDGE_AUTH_MODE_HMAC_JWT:
        return verify_bridge_hmac_token(token, config)
    if config.mode == BRIDGE_AUTH_MODE_GOOGLE_OIDC:
        return verify_google_oidc_token(token, config)
    raise HTTPException(status_code=500, detail="Unsupported storage bridge auth mode.")
