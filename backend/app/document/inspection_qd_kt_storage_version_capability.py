"""Fail-closed QĐKT storage-version capability inventory; no I/O or activation."""
from dataclasses import dataclass
from enum import Enum


class StorageVersionPinStatus(str, Enum):
    UNSUPPORTED = "UNSUPPORTED"
    UNVERIFIED_ADAPTER = "UNVERIFIED_ADAPTER"


@dataclass(frozen=True)
class QdKtStorageVersionCapability:
    status: StorageVersionPinStatus
    adapter: str
    immutable_version_read_verified: bool = False
    ready_to_render: bool = False


class QdKtStorageVersionPinBlocked(ValueError):
    pass


_KNOWN_UNVERSIONED = frozenset({
    "local_filesystem_fake", "synology_smb", "external_bridge_http",
})


def inspect_qdkt_storage_version_capability(storage) -> QdKtStorageVersionCapability:
    """Inventory declared adapter type without opening files or trusting metadata."""
    adapter = getattr(getattr(storage, "config", None), "storage_class", None)
    if not isinstance(adapter, str) or not adapter.strip():
        return QdKtStorageVersionCapability(StorageVersionPinStatus.UNVERIFIED_ADAPTER, "unknown")
    status = (StorageVersionPinStatus.UNSUPPORTED if adapter in _KNOWN_UNVERSIONED
              else StorageVersionPinStatus.UNVERIFIED_ADAPTER)
    return QdKtStorageVersionCapability(status, adapter)


def require_qdkt_immutable_storage_version(storage) -> None:
    """Never infer immutable generation pinning from checksum/ETag or double-read."""
    capability = inspect_qdkt_storage_version_capability(storage)
    raise QdKtStorageVersionPinBlocked(
        f"QDKT_STORAGE_IMMUTABLE_VERSION_UNPROVEN:{capability.status.value}"
    )
