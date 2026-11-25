"""Shared exact relative-path policy for QĐKT storage evidence."""
from __future__ import annotations

from unicodedata import category, normalize


def is_safe_qdkt_relative_path(value: object) -> bool:
    return (
        isinstance(value, str) and bool(value)
        and "\\" not in value and not value.startswith("/")
        and ":" not in value
        # Disallow invisible control/format characters (including C1 and bidi
        # overrides) and non-canonical Unicode aliases before adapter access.
        and normalize("NFC", value) == value
        and not any(category(char) in ("Cc", "Cf", "Cs") for char in value)
        and all(_safe_storage_component(part) for part in value.split("/"))
    )



# SMB/Windows clients may interpret trailing dots/spaces and DOS device names
# as aliases rather than distinct objects. Refuse them for audit locators.
_WINDOWS_DEVICE_NAMES = frozenset(
    ("CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$")
    + tuple(f"COM{i}" for i in range(1, 10))
    + tuple(f"LPT{i}" for i in range(1, 10))
    # Windows also reserves device aliases with superscript 1/2/3.
    + tuple(f"{prefix}{digit}" for prefix in ("COM", "LPT") for digit in ("¹", "²", "³"))
)


def _safe_storage_component(part: str) -> bool:
    return (
        part not in ("", ".", "..")
        and not part.endswith((" ", "."))
        and part.split(".", 1)[0].upper() not in _WINDOWS_DEVICE_NAMES
    )
