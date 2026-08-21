from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import shutil
from typing import BinaryIO, Iterator
from uuid import uuid4

from backend.app.db.enums import StorageResolutionStatus
from backend.app.storage.local import _normalize_relative
from backend.app.storage.types import SmbStorageConfig, StorageEntry, StorageOperationError, StorageResolution

try:
    import smbclient
    from smbclient import path as smbpath
except ModuleNotFoundError:  # pragma: no cover
    smbclient = None
    smbpath = None


class SmbStorageService:
    def __init__(self, config: SmbStorageConfig):
        if smbclient is None or smbpath is None:  # pragma: no cover
            raise StorageOperationError("smbprotocol is required for STORAGE_CLASS=synology_smb_bridge.")
        self.config = config
        self.inspection_root = self._normalize_root(config.inspection_root)
        self.dkkd_root = self._normalize_root(config.dkkd_root) if config.dkkd_root else None
        self.template_root = self._normalize_root(config.template_root) if config.template_root else None
        self._register_root_session(self.inspection_root)
        if self.dkkd_root:
            self._register_root_session(self.dkkd_root)
        if self.template_root:
            self._register_root_session(self.template_root)

    def _normalize_root(self, root: str) -> str:
        normalized = (root or "").strip().rstrip("\\/")
        if not normalized.startswith("\\\\"):
            raise StorageOperationError("SMB roots must be UNC paths like \\\\host\\share\\folder.")
        return normalized

    def _server_from_root(self, root: str) -> str:
        without_prefix = root.lstrip("\\")
        parts = [part for part in without_prefix.split("\\") if part]
        if len(parts) < 2:
            raise StorageOperationError("SMB root must contain a host and share name.")
        return parts[0]

    def _register_root_session(self, root: str) -> None:
        server = self._server_from_root(root)
        smbclient.register_session(
            server,
            username=self.config.username,
            password=self.config.password,
            port=self.config.port,
            encrypt=self.config.encrypt,
            connection_timeout=self.config.connection_timeout,
            auth_protocol=self.config.auth_protocol,
        )

    def _join_root(self, root: str, relative_path: str) -> str:
        normalized = _normalize_relative(relative_path)
        if not normalized:
            return root
        return root + "\\" + normalized.replace("/", "\\")

    def _entry_for(self, root: str, target: str) -> StorageEntry:
        relative = target[len(root) :].lstrip("\\").replace("\\", "/")
        stat_result = smbclient.stat(target)
        is_dir = smbpath.isdir(target)
        return StorageEntry(
            relative_path=relative,
            name=target.rstrip("\\").split("\\")[-1],
            is_dir=is_dir,
            size=None if is_dir else int(stat_result.st_size),
        )

    def _resolution_from_matches(
        self,
        *,
        root: str,
        matches: list[str],
        not_found_detail: str,
        ambiguous_detail: str,
    ) -> StorageResolution:
        if not matches:
            return StorageResolution(
                status=StorageResolutionStatus.NOT_FOUND,
                relative_path=None,
                absolute_path=None,
                candidate_count=0,
                detail=not_found_detail,
            )
        if len(matches) > 1:
            return StorageResolution(
                status=StorageResolutionStatus.AMBIGUOUS,
                relative_path=None,
                absolute_path=None,
                candidate_count=len(matches),
                detail=ambiguous_detail,
            )
        relative = matches[0][len(root) :].lstrip("\\").replace("\\", "/")
        return StorageResolution(
            status=StorageResolutionStatus.RESOLVED,
            relative_path=relative,
            absolute_path=None,
            candidate_count=1,
            detail=None,
        )

    def resolve_inspection_folder(
        self,
        *,
        case_id: str | None = None,
        year: int,
        site_legacy_id: int,
        inspection_legacy_code: str,
    ) -> StorageResolution:
        if year <= 0 or site_legacy_id <= 0 or not str(inspection_legacy_code or "").strip():
            return StorageResolution(
                status=StorageResolutionStatus.INVALID,
                relative_path=None,
                absolute_path=None,
                candidate_count=0,
                detail="Missing or invalid inspection folder identity input.",
            )
        year_root = self._join_root(self.inspection_root, str(year))
        if not smbpath.exists(year_root) or not smbpath.isdir(year_root):
            return StorageResolution(
                status=StorageResolutionStatus.NOT_FOUND,
                relative_path=None,
                absolute_path=None,
                candidate_count=0,
                detail=f"Year folder '{year}' not found under inspection root.",
            )
        site_token = f"(ID-{site_legacy_id})".lower()
        inspection_token = f"({inspection_legacy_code})".lower()
        matches = [
            entry.path
            for entry in smbclient.scandir(year_root)
            if entry.is_dir() and site_token in entry.name.lower() and inspection_token in entry.name.lower()
        ]
        return self._resolution_from_matches(
            root=self.inspection_root,
            matches=matches,
            not_found_detail="No inspection folder matched the legacy identity tokens.",
            ambiguous_detail="More than one inspection folder matched the legacy identity tokens.",
        )

    def resolve_dkkd_folder(
        self,
        *,
        case_id: str | None = None,
        site_legacy_id: int,
    ) -> StorageResolution:
        if self.dkkd_root is None:
            return StorageResolution(
                status=StorageResolutionStatus.INVALID,
                relative_path=None,
                absolute_path=None,
                candidate_count=0,
                detail="DDKD root is not configured.",
            )
        if site_legacy_id <= 0:
            return StorageResolution(
                status=StorageResolutionStatus.INVALID,
                relative_path=None,
                absolute_path=None,
                candidate_count=0,
                detail="Missing or invalid site legacy ID for DDKD folder resolution.",
            )
        site_token = f"({site_legacy_id})".lower()
        matches = [
            entry.path
            for entry in smbclient.scandir(self.dkkd_root)
            if entry.is_dir() and site_token in entry.name.lower()
        ]
        return self._resolution_from_matches(
            root=self.dkkd_root,
            matches=matches,
            not_found_detail="No DDKD folder matched the site legacy token.",
            ambiguous_detail="More than one DDKD folder matched the site legacy token.",
        )

    def list(self, relative_path: str = "", *, root: str = "inspection") -> list[StorageEntry]:
        base_root = self._select_root(root)
        target = self._join_root(base_root, relative_path)
        if not smbpath.exists(target):
            raise FileNotFoundError(target)
        if not smbpath.isdir(target):
            raise NotADirectoryError(target)
        return [
            self._entry_for(base_root, entry.path)
            for entry in sorted(smbclient.scandir(target), key=lambda item: (not item.is_dir(), item.name.lower()))
        ]

    def stat(self, relative_path: str, *, root: str = "inspection") -> StorageEntry:
        base_root = self._select_root(root)
        target = self._join_root(base_root, relative_path)
        if not smbpath.exists(target):
            raise FileNotFoundError(target)
        return self._entry_for(base_root, target)

    def exists(self, relative_path: str, *, root: str = "inspection") -> bool:
        return smbpath.exists(self._join_root(self._select_root(root), relative_path))

    @contextmanager
    def read_stream(self, relative_path: str, *, root: str = "inspection") -> Iterator[BinaryIO]:
        target = self._join_root(self._select_root(root), relative_path)
        with smbclient.open_file(target, mode="rb") as fh:
            yield fh

    def write_stream(self, relative_path: str, stream: BinaryIO, *, root: str = "inspection") -> StorageEntry:
        base_root = self._select_root(root)
        target = self._join_root(base_root, relative_path)
        parent = target.rsplit("\\", 1)[0]
        smbclient.makedirs(parent, exist_ok=True)
        temp_target = target + f".tmp-{uuid4().hex}"
        try:
            with smbclient.open_file(temp_target, mode="wb") as fh:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
            smbclient.replace(temp_target, target)
        except Exception:
            if smbpath.exists(temp_target):
                smbclient.remove(temp_target)
            raise
        return self._entry_for(base_root, target)

    def create_folder(self, relative_path: str, *, root: str = "inspection") -> StorageEntry:
        base_root = self._select_root(root)
        target = self._join_root(base_root, relative_path)
        smbclient.makedirs(target, exist_ok=True)
        return self._entry_for(base_root, target)

    def copy(self, source_relative_path: str, target_relative_path: str, *, root: str = "inspection") -> StorageEntry:
        base_root = self._select_root(root)
        source = self._join_root(base_root, source_relative_path)
        target = self._join_root(base_root, target_relative_path)
        parent = target.rsplit("\\", 1)[0]
        smbclient.makedirs(parent, exist_ok=True)
        with smbclient.open_file(source, mode="rb") as src, smbclient.open_file(target, mode="wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        return self._entry_for(base_root, target)

    def move(self, source_relative_path: str, target_relative_path: str, *, root: str = "inspection") -> StorageEntry:
        base_root = self._select_root(root)
        source = self._join_root(base_root, source_relative_path)
        target = self._join_root(base_root, target_relative_path)
        parent = target.rsplit("\\", 1)[0]
        smbclient.makedirs(parent, exist_ok=True)
        smbclient.rename(source, target)
        return self._entry_for(base_root, target)

    def rename(self, source_relative_path: str, new_name: str, *, root: str = "inspection") -> StorageEntry:
        if "/" in new_name or "\\" in new_name or new_name in {"", ".", ".."}:
            raise StorageOperationError("Invalid rename target.")
        base_root = self._select_root(root)
        source = self._join_root(base_root, source_relative_path)
        target = source.rsplit("\\", 1)[0] + "\\" + new_name
        smbclient.rename(source, target)
        return self._entry_for(base_root, target)

    def checksum(self, relative_path: str, *, root: str = "inspection") -> str:
        target = self._join_root(self._select_root(root), relative_path)
        digest = sha256()
        with smbclient.open_file(target, mode="rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _select_root(self, root: str) -> str:
        if root == "inspection":
            return self.inspection_root
        if root == "dkkd":
            if self.dkkd_root is None:
                raise StorageOperationError("DDKD root is not configured.")
            return self.dkkd_root
        if root == "template":
            if self.template_root is None:
                raise StorageOperationError("Template root is not configured.")
            return self.template_root
        raise StorageOperationError(f"Unsupported root '{root}'.")
