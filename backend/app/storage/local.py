from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import os
import shutil
import tempfile
from typing import BinaryIO, Iterator

from backend.app.db.enums import StorageResolutionStatus
from backend.app.storage.types import StorageConfig, StorageEntry, StorageOperationError, StorageResolution


def _normalize_relative(relative_path: str) -> str:
    normalized = str(relative_path or "").replace("\\", "/").strip().strip("/")
    if not normalized:
        return ""
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise StorageOperationError("Path traversal is not allowed.")
    return "/".join(parts)


class LocalStorageService:
    def __init__(self, config: StorageConfig):
        self.config = config
        self.inspection_root = config.inspection_root.resolve()
        self.dkkd_root = config.dkkd_root.resolve() if config.dkkd_root else None
        self.template_root = config.template_root.resolve() if config.template_root else None

    def _ensure_within_root(self, root: Path, target: Path) -> Path:
        resolved = target.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise StorageOperationError("Resolved path escapes configured storage root.") from exc
        return resolved

    def _path_under(self, root: Path, relative_path: str) -> Path:
        normalized = _normalize_relative(relative_path)
        candidate = root / normalized if normalized else root
        return self._ensure_within_root(root, candidate)

    def _entry_for(self, root: Path, path: Path) -> StorageEntry:
        rel = path.relative_to(root).as_posix()
        return StorageEntry(
            relative_path="" if rel == "." else rel,
            name=path.name,
            is_dir=path.is_dir(),
            size=None if path.is_dir() else path.stat().st_size,
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

        year_root = self.inspection_root / str(year)
        if not year_root.exists() or not year_root.is_dir():
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
            path
            for path in year_root.iterdir()
            if path.is_dir()
            and site_token in path.name.lower()
            and inspection_token in path.name.lower()
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
            path
            for path in self.dkkd_root.iterdir()
            if path.is_dir() and site_token in path.name.lower()
        ]
        return self._resolution_from_matches(
            root=self.dkkd_root,
            matches=matches,
            not_found_detail="No DDKD folder matched the site legacy token.",
            ambiguous_detail="More than one DDKD folder matched the site legacy token.",
        )

    def _resolution_from_matches(
        self,
        *,
        root: Path,
        matches: list[Path],
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
        match = self._ensure_within_root(root, matches[0])
        return StorageResolution(
            status=StorageResolutionStatus.RESOLVED,
            relative_path=match.relative_to(root).as_posix(),
            absolute_path=match,
            candidate_count=1,
            detail=None,
        )

    def list(self, relative_path: str = "", *, root: str = "inspection") -> list[StorageEntry]:
        base_root = self._select_root(root)
        target = self._path_under(base_root, relative_path)
        if not target.exists():
            raise FileNotFoundError(target)
        if not target.is_dir():
            raise NotADirectoryError(target)
        return [self._entry_for(base_root, child) for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))]

    def stat(self, relative_path: str, *, root: str = "inspection") -> StorageEntry:
        base_root = self._select_root(root)
        target = self._path_under(base_root, relative_path)
        if not target.exists():
            raise FileNotFoundError(target)
        return self._entry_for(base_root, target)

    def exists(self, relative_path: str, *, root: str = "inspection") -> bool:
        base_root = self._select_root(root)
        target = self._path_under(base_root, relative_path)
        return target.exists()

    @contextmanager
    def read_stream(self, relative_path: str, *, root: str = "inspection") -> Iterator[BinaryIO]:
        base_root = self._select_root(root)
        target = self._path_under(base_root, relative_path)
        with target.open("rb") as fh:
            yield fh

    def write_stream(self, relative_path: str, stream: BinaryIO, *, root: str = "inspection") -> StorageEntry:
        base_root = self._select_root(root)
        target = self._path_under(base_root, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, dir=target.parent) as tmp:
                temp_path = Path(tmp.name)
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    tmp.write(chunk)
            os.replace(temp_path, target)
        except Exception:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise
        return self._entry_for(base_root, target)

    def create_folder(self, relative_path: str, *, root: str = "inspection") -> StorageEntry:
        base_root = self._select_root(root)
        target = self._path_under(base_root, relative_path)
        target.mkdir(parents=True, exist_ok=True)
        return self._entry_for(base_root, target)

    def copy(self, source_relative_path: str, target_relative_path: str, *, root: str = "inspection") -> StorageEntry:
        base_root = self._select_root(root)
        source = self._path_under(base_root, source_relative_path)
        target = self._path_under(base_root, target_relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return self._entry_for(base_root, target)

    def move(self, source_relative_path: str, target_relative_path: str, *, root: str = "inspection") -> StorageEntry:
        base_root = self._select_root(root)
        source = self._path_under(base_root, source_relative_path)
        target = self._path_under(base_root, target_relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        return self._entry_for(base_root, target)

    def rename(self, source_relative_path: str, new_name: str, *, root: str = "inspection") -> StorageEntry:
        if "/" in new_name or "\\" in new_name or new_name in {"", ".", ".."}:
            raise StorageOperationError("Invalid rename target.")
        base_root = self._select_root(root)
        source = self._path_under(base_root, source_relative_path)
        target = source.with_name(new_name)
        self._ensure_within_root(base_root, target)
        source.rename(target)
        return self._entry_for(base_root, target)

    def checksum(self, relative_path: str, *, root: str = "inspection") -> str:
        base_root = self._select_root(root)
        target = self._path_under(base_root, relative_path)
        digest = sha256()
        with target.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _select_root(self, root: str) -> Path:
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
