"""Strict, offline-only archive preflight for disposable QĐKT DOTX QA.

No file extraction, filesystem writes, Case source lookup or renderer access.
The limits are intentionally conservative until the original DOTX binaries
have been independently profiled and approved.
"""
from __future__ import annotations

import stat
from zipfile import ZipFile, ZipInfo

MAX_PARTS = 256
MAX_PART_SIZE = 8 * 1024 * 1024
MAX_TOTAL_SIZE = 32 * 1024 * 1024


class QdKtOfflinePackageIntegrityBlocked(ValueError):
    pass


def require_safe_ooxml_members(source: ZipFile) -> tuple[ZipInfo, ...]:
    """Validate names, metadata and CRC before any XML is transformed."""
    members = tuple(source.infolist())
    if len(members) > MAX_PARTS:
        raise QdKtOfflinePackageIntegrityBlocked("QDKT_PACKAGE_PART_COUNT_UNSAFE")
    seen: set[str] = set()
    total = 0
    for part in members:
        name = part.filename
        if (
            not name or name in seen or "\\"
            in name or name.startswith("/") or "\x00" in name
            or ":" in name or any(piece in ("", ".", "..") for piece in name.split("/") if not (part.is_dir() and piece == ""))
        ):
            raise QdKtOfflinePackageIntegrityBlocked("QDKT_PACKAGE_MEMBER_NAME_UNSAFE")
        seen.add(name)
        mode = (part.external_attr >> 16) & 0xFFFF
        if part.create_system == 3 and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise QdKtOfflinePackageIntegrityBlocked("QDKT_PACKAGE_MEMBER_TYPE_UNSAFE")
        if part.flag_bits & 0x1:
            raise QdKtOfflinePackageIntegrityBlocked("QDKT_PACKAGE_ENCRYPTED_PART")
        if part.file_size > MAX_PART_SIZE:
            raise QdKtOfflinePackageIntegrityBlocked("QDKT_PACKAGE_PART_SIZE_UNSAFE")
        total += part.file_size
        if total > MAX_TOTAL_SIZE:
            raise QdKtOfflinePackageIntegrityBlocked("QDKT_PACKAGE_TOTAL_SIZE_UNSAFE")
    if source.testzip() is not None:
        raise QdKtOfflinePackageIntegrityBlocked("QDKT_PACKAGE_CRC_INVALID")
    return members
