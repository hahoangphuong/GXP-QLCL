from __future__ import annotations

from datetime import date, datetime
from typing import Any


_REDACTED = "<redacted>"
_SENSITIVE_KEY_TOKENS = (
    "password",
    "secret",
    "token",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "credential",
    "private_key",
    "signing_key",
)
_BINARY_KEY_TOKENS = (
    "binary",
    "content_bytes",
    "file_bytes",
    "blob",
)


def normalize_and_redact_audit_payload(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "value"):
        enum_value = getattr(value, "value")
        if isinstance(enum_value, str):
            return enum_value
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            normalized[str(key)] = _REDACTED if _is_sensitive_key(str(key)) else normalize_and_redact_audit_payload(item)
        return normalized
    if isinstance(value, list):
        return [normalize_and_redact_audit_payload(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_and_redact_audit_payload(item) for item in value]
    if isinstance(value, set):
        return [normalize_and_redact_audit_payload(item) for item in sorted(value, key=repr)]
    if isinstance(value, bytes):
        return _REDACTED
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.strip().lower()
    return any(token in lowered for token in (_SENSITIVE_KEY_TOKENS + _BINARY_KEY_TOKENS))
