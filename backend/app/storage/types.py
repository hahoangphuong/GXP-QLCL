from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator, Protocol

from backend.app.db.enums import StorageResolutionStatus


class StorageOperationError(RuntimeError):
    pass


@dataclass(frozen=True)
class StorageConfig:
    inspection_root: Path
    dkkd_root: Path | None = None
    template_root: Path | None = None
    storage_class: str = "local_filesystem_fake"


@dataclass(frozen=True)
class ExternalBridgeStorageConfig:
    base_url: str
    auth_mode: str = "google_oidc"
    auth_audience: str | None = None
    auth_client_id: str | None = None
    auth_token_issuer: str | None = None
    auth_signing_key: str | None = None
    storage_class: str = "external_bridge_http"


@dataclass(frozen=True)
class StorageResolution:
    status: StorageResolutionStatus
    relative_path: str | None
    absolute_path: Path | None
    candidate_count: int
    detail: str | None = None


@dataclass(frozen=True)
class StorageEntry:
    relative_path: str
    name: str
    is_dir: bool
    size: int | None


class StorageServiceProtocol(Protocol):
    config: StorageConfig | ExternalBridgeStorageConfig

    def resolve_inspection_folder(
        self,
        *,
        case_id: str | None = None,
        year: int,
        site_legacy_id: int,
        inspection_legacy_code: str,
    ) -> StorageResolution: ...
    def resolve_dkkd_folder(self, *, case_id: str | None = None, site_legacy_id: int) -> StorageResolution: ...
    def list(self, relative_path: str = "", *, root: str = "inspection") -> list[StorageEntry]: ...
    def stat(self, relative_path: str, *, root: str = "inspection") -> StorageEntry: ...
    def exists(self, relative_path: str, *, root: str = "inspection") -> bool: ...
    def read_stream(self, relative_path: str, *, root: str = "inspection") -> Iterator[BinaryIO]: ...
    def write_stream(self, relative_path: str, stream: BinaryIO, *, root: str = "inspection") -> StorageEntry: ...
    def create_folder(self, relative_path: str, *, root: str = "inspection") -> StorageEntry: ...
    def copy(self, source_relative_path: str, target_relative_path: str, *, root: str = "inspection") -> StorageEntry: ...
    def move(self, source_relative_path: str, target_relative_path: str, *, root: str = "inspection") -> StorageEntry: ...
    def rename(self, source_relative_path: str, new_name: str, *, root: str = "inspection") -> StorageEntry: ...
    def checksum(self, relative_path: str, *, root: str = "inspection") -> str: ...
