from __future__ import annotations

from contextlib import contextmanager
import ctypes
import errno
from hashlib import sha256
from pathlib import Path
import os
import shutil
import sys
import tempfile
from typing import BinaryIO, Iterator

from backend.app.db.enums import StorageResolutionStatus
from backend.app.storage.types import (
    StorageConfig,
    StorageEntry,
    StorageOperationError,
    StorageTargetExistsError,
    StorageResolution,
    matches_inspection_identity,
    matches_dkkd_identity,
)


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
        # Directory enumeration yields unresolved child paths. Unlike
        # _path_under(), these may still be symlinks pointing outside root.
        # Check each entry before probing its type, size or other metadata.
        self._ensure_within_root(root, path)
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
        year: int | None = None,
        site_legacy_id: int,
        inspection_legacy_code: str,
    ) -> StorageResolution:
        if year is None or year <= 0 or site_legacy_id <= 0 or not str(inspection_legacy_code or "").strip():
            return StorageResolution(
                status=StorageResolutionStatus.INVALID,
                relative_path=None,
                absolute_path=None,
                candidate_count=0,
                detail="Missing or invalid inspection folder identity input.",
            )

        # Do not enumerate a year directory that resolves outside the
        # inspection root (for example, a year-named symlink).
        year_roots = [self._path_under(self.inspection_root, str(year))]
        matches = [
            path
            for year_root in year_roots
            if year_root.exists() and year_root.is_dir()
            for path in year_root.iterdir()
            if path.is_dir()
            and matches_inspection_identity(
                path.name,
                site_legacy_id=site_legacy_id,
                inspection_legacy_code=inspection_legacy_code,
            )
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

        matches = [
            path
            for path in self.dkkd_root.iterdir()
            if path.is_dir() and matches_dkkd_identity(path.name, site_legacy_id=site_legacy_id)
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
        # Check all matching paths before reporting a count. Without this,
        # multiple outside-root symlinks are reported as AMBIGUOUS and leak
        # information about paths the adapter must never examine.
        for path in matches:
            self._ensure_within_root(root, path)
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

    def write_stream(
        self,
        relative_path: str,
        stream: BinaryIO,
        *,
        root: str = "inspection",
        overwrite: bool = True,
    ) -> StorageEntry:
        base_root = self._select_root(root)
        target = self._path_under(base_root, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Both modes prepare an entire private file before publication.
        # Exclusive creates use kernel-enforced no-replace; they must not
        # expose a partially written document or unlink a competing writer.
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, dir=target.parent) as tmp:
                temp_path = Path(tmp.name)
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    tmp.write(chunk)
            if overwrite:
                os.replace(temp_path, target)
            else:
                self._rename_noreplace(temp_path, target, relative_path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return self._entry_for(base_root, target)

    def delete(self, relative_path: str, *, root: str = "inspection") -> None:
        base_root = self._select_root(root)
        target = self._path_under(base_root, relative_path)
        if not target.exists():
            raise FileNotFoundError(target)
        if target.is_dir():
            raise IsADirectoryError(target)
        target.unlink()

    def create_folder(self, relative_path: str, *, root: str = "inspection") -> StorageEntry:
        base_root = self._select_root(root)
        target = self._path_under(base_root, relative_path)
        target.mkdir(parents=True, exist_ok=True)
        return self._entry_for(base_root, target)

    @staticmethod
    def _require_vacant_target(target: Path, relative_path: str) -> None:
        # lexists also rejects dangling links, which Path.exists() misses.
        if os.path.lexists(target):
            raise StorageTargetExistsError(
                f"Storage target already exists and will not be overwritten: {relative_path!r}."
            )

    def copy(self, source_relative_path: str, target_relative_path: str, *, root: str = "inspection") -> StorageEntry:
        base_root = self._select_root(root)
        source = self._path_under(base_root, source_relative_path)
        target = self._path_under(base_root, target_relative_path)
        self._require_vacant_target(target, target_relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Prepare a complete copy, including metadata, before it becomes
        # visible at the destination. Never unlink a published destination on
        # metadata failure: another writer may have replaced it meanwhile.
        temp_path: Path | None = None
        try:
            with source.open("rb") as stream, tempfile.NamedTemporaryFile(
                delete=False, dir=target.parent
            ) as tmp:
                temp_path = Path(tmp.name)
                shutil.copyfileobj(stream, tmp, length=1024 * 1024)
            shutil.copystat(source, temp_path)
            # Atomic conflict detection also covers a destination created
            # after the preflight check or while bytes are copied.
            self._rename_noreplace(temp_path, target, target_relative_path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return self._entry_for(base_root, target)

    @staticmethod
    def _rename_noreplace(source: Path, target: Path, relative_path: str) -> None:
        """Use an OS-enforced no-replace move; never trust a prior exists check.

        Production Linux requires renameat2(RENAME_NOREPLACE), including on
        mounted CIFS shares. Unsupported filesystems fail closed rather than
        falling back to shutil.move/os.rename, which can overwrite on POSIX.
        """
        if sys.platform.startswith("linux"):
            libc = ctypes.CDLL(None, use_errno=True)
            renameat2 = getattr(libc, "renameat2", None)
            if renameat2 is None:
                raise StorageOperationError("Atomic no-replace rename is unavailable on this runtime.")
            renameat2.argtypes = (
                ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
            )
            renameat2.restype = ctypes.c_int
            # AT_FDCWD=-100, RENAME_NOREPLACE=1, Linux renameat2(2).
            result = renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1)
            if result == 0:
                return
            error_code = ctypes.get_errno()
            if error_code in {errno.EEXIST, errno.ENOTEMPTY}:
                raise StorageTargetExistsError(
                    f"Storage target already exists and will not be overwritten: {relative_path!r}."
                )
            if error_code in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP, errno.EXDEV}:
                raise StorageOperationError(
                    "Atomic no-replace rename is unsupported for this storage location."
                )
            raise OSError(error_code, os.strerror(error_code), str(source))

        if os.name == "nt":
            # Windows os.rename does not replace an existing destination.
            try:
                os.rename(source, target)
            except OSError as exc:
                if os.path.lexists(target):
                    raise StorageTargetExistsError(
                        f"Storage target already exists and will not be overwritten: {relative_path!r}."
                    ) from exc
                raise
            return

        raise StorageOperationError("Atomic no-replace rename is unsupported on this platform.")

    def move(self, source_relative_path: str, target_relative_path: str, *, root: str = "inspection") -> StorageEntry:
        base_root = self._select_root(root)
        source = self._path_under(base_root, source_relative_path)
        target = self._path_under(base_root, target_relative_path)
        self._require_vacant_target(target, target_relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._rename_noreplace(source, target, target_relative_path)
        return self._entry_for(base_root, target)

    def rename(self, source_relative_path: str, new_name: str, *, root: str = "inspection") -> StorageEntry:
        if "/" in new_name or "\\" in new_name or new_name in {"", ".", ".."}:
            raise StorageOperationError("Invalid rename target.")
        base_root = self._select_root(root)
        source = self._path_under(base_root, source_relative_path)
        target = source.with_name(new_name)
        self._ensure_within_root(base_root, target)
        self._require_vacant_target(target, target.relative_to(base_root).as_posix())
        self._rename_noreplace(source, target, target.relative_to(base_root).as_posix())
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
