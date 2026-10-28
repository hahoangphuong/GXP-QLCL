from __future__ import annotations

from contextlib import contextmanager
import ctypes
import errno
from hashlib import sha256
from pathlib import Path
import os
import shutil
import stat
import sys
import tempfile
from typing import BinaryIO, Iterator

from backend.app.storage.staging import new_staging_name

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

    def iter_entries_for_audit(self, relative_path: str = "", *, root: str = "inspection") -> Iterator[StorageEntry]:
        """Stream entries without sorting/materializing a large directory.

        This iterator is for bounded, read-only audits; every child retains
        the same root-containment check used by normal listing.
        """
        base_root = self._select_root(root)
        target = self._path_under(base_root, relative_path)
        if not target.exists():
            raise FileNotFoundError(target)
        if not target.is_dir():
            raise NotADirectoryError(target)
        with os.scandir(target) as listing:
            for entry in listing:
                yield self._entry_for(base_root, Path(entry.path))

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
        # On POSIX, hold descriptors for each directory and reject symlinks.
        # A path.resolve() check followed by Path.open() can be raced by
        # replacing a parent directory with a symlink to another tree.
        # This is descriptor-anchored containment, NOT an immutable version pin.
        if os.name != "posix":
            target = self._path_under(base_root, relative_path)
            with target.open("rb") as fh:
                yield fh
            return
        normalized = _normalize_relative(relative_path)
        if not normalized:
            raise StorageOperationError("A regular file path is required for storage read.")
        parts = normalized.split("/")
        flags = os.O_RDONLY | os.O_NOFOLLOW
        dirflags = flags | os.O_DIRECTORY
        fds: list[int] = []
        try:
            directory_fd = os.open(base_root, dirflags)
            fds.append(directory_fd)
            for part in parts[:-1]:
                directory_fd = os.open(part, dirflags, dir_fd=directory_fd)
                fds.append(directory_fd)
            file_fd = os.open(parts[-1], flags | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
            fds.append(file_fd)
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise StorageOperationError("Storage read target is not a regular file.")
            # fdopen may fail before it takes ownership of file_fd. Keep the
            # descriptor in the cleanup stack until wrapping succeeds.
            fh = os.fdopen(file_fd, "rb")
            fds.pop()
            with fh:
                yield fh
        finally:
            for fd in reversed(fds):
                os.close(fd)

    def _write_stream_posix(
        self, base_root: Path, relative_path: str, stream: BinaryIO, *, overwrite: bool,
    ) -> StorageEntry:
        """Keep a directory fd through staging, publication and cleanup.

        No post-containment pathname lookup can redirect writes outside root.
        An exclusive publish requires Linux renameat2(RENAME_NOREPLACE).
        """
        normalized = _normalize_relative(relative_path)
        if not normalized:
            raise StorageOperationError("A regular file path is required for storage write.")
        parts = normalized.split("/")
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
        fds: list[int] = []
        staging_name: str | None = None
        published_size: int | None = None
        import secrets

        try:
            parent_fd = os.open(base_root, flags)
            fds.append(parent_fd)
            for part in parts[:-1]:
                try:
                    os.mkdir(part, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                parent_fd = os.open(part, flags, dir_fd=parent_fd)
                fds.append(parent_fd)

            name = parts[-1]
            for _ in range(8):
                candidate = ".gxp-stage-" + secrets.token_hex(16) + ".tmp"
                try:
                    staged_fd = os.open(
                        candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600, dir_fd=parent_fd,
                    )
                except FileExistsError:
                    continue
                staging_name = candidate
                break
            else:
                raise StorageOperationError("Unable to allocate a private staging file.")

            # fdopen takes ownership only after successful wrapping.
            try:
                staged_stream = os.fdopen(staged_fd, "wb")
            except BaseException:
                os.close(staged_fd)
                raise
            with staged_stream:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    staged_stream.write(chunk)
                staged_stream.flush()
                published_size = os.fstat(staged_stream.fileno()).st_size

            if overwrite:
                os.replace(staging_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            else:
                if not sys.platform.startswith("linux"):
                    raise StorageOperationError("Atomic no-replace rename is unsupported on this platform.")
                libc = ctypes.CDLL(None, use_errno=True)
                renameat2 = getattr(libc, "renameat2", None)
                if renameat2 is None:
                    raise StorageOperationError("Atomic no-replace rename is unavailable on this runtime.")
                renameat2.argtypes = (
                    ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
                )
                renameat2.restype = ctypes.c_int
                result = renameat2(parent_fd, os.fsencode(staging_name), parent_fd, os.fsencode(name), 1)
                if result != 0:
                    error_code = ctypes.get_errno()
                    if error_code in {errno.EEXIST, errno.ENOTEMPTY}:
                        raise StorageTargetExistsError(
                            f"Storage target already exists and will not be overwritten: {relative_path!r}."
                        )
                    if error_code in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP, errno.EXDEV}:
                        raise StorageOperationError(
                            "Atomic no-replace rename is unsupported for this storage location."
                        )
                    raise OSError(error_code, os.strerror(error_code), normalized)
            staging_name = None
        finally:
            if staging_name is not None and fds:
                try:
                    os.unlink(staging_name, dir_fd=fds[-1])
                except FileNotFoundError:
                    pass
            for fd in reversed(fds):
                os.close(fd)
        # Publication was relative to the held parent fd. Do not reopen the
        # pathname for the result: a swapped parent can now point outside
        # the root even though the publication itself remained contained.
        return StorageEntry(relative_path=normalized, name=name, is_dir=False, size=published_size)

    def write_stream(
        self,
        relative_path: str,
        stream: BinaryIO,
        *,
        root: str = "inspection",
        overwrite: bool = True,
    ) -> StorageEntry:
        base_root = self._select_root(root)
        if os.name == "posix":
            return self._write_stream_posix(base_root, relative_path, stream, overwrite=overwrite)
        target = self._path_under(base_root, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Non-POSIX retains the existing pathname-based publication contract.
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, dir=target.parent, prefix=".gxp-stage-", suffix=".tmp") as tmp:
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
        if os.name == "posix":
            normalized = _normalize_relative(relative_path)
            if not normalized:
                raise IsADirectoryError(base_root)
            parts = normalized.split("/")
            directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            fds: list[int] = []
            try:
                parent_fd = os.open(base_root, directory_flags)
                fds.append(parent_fd)
                for component in parts[:-1]:
                    parent_fd = os.open(component, directory_flags, dir_fd=parent_fd)
                    fds.append(parent_fd)
                name = parts[-1]
                # Inspect and unlink relative to the *same* held parent
                # directory, not a pathname that can be swapped to a symlink.
                mode = os.stat(name, dir_fd=parent_fd, follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    raise IsADirectoryError(normalized)
                if not stat.S_ISREG(mode):
                    raise StorageOperationError("Storage delete target is not a regular file.")
                os.unlink(name, dir_fd=parent_fd)
            finally:
                for fd in reversed(fds):
                    os.close(fd)
            return
        target = self._path_under(base_root, relative_path)
        if not target.exists():
            raise FileNotFoundError(target)
        if target.is_dir():
            raise IsADirectoryError(target)
        target.unlink()

    def create_folder(self, relative_path: str, *, root: str = "inspection") -> StorageEntry:
        base_root = self._select_root(root)
        if os.name == "posix":
            normalized = _normalize_relative(relative_path)
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            fds: list[int] = []
            try:
                directory_fd = os.open(base_root, flags)
                fds.append(directory_fd)
                for component in normalized.split("/") if normalized else ():
                    try:
                        os.mkdir(component, dir_fd=directory_fd)
                    except FileExistsError:
                        pass
                    directory_fd = os.open(component, flags, dir_fd=directory_fd)
                    fds.append(directory_fd)
            finally:
                for fd in reversed(fds):
                    os.close(fd)
            return StorageEntry(
                relative_path=normalized,
                name=normalized.rsplit("/", 1)[-1] if normalized else base_root.name,
                is_dir=True,
                size=None,
            )
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

    @staticmethod
    def _rename_noreplace_dirfd(parent_fd: int, source_name: str, target_name: str, relative_path: str) -> None:
        """OS-enforced exclusive publication within one held directory."""
        if not sys.platform.startswith("linux"):
            raise StorageOperationError("Atomic no-replace rename is unsupported on this platform.")
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise StorageOperationError("Atomic no-replace rename is unavailable on this runtime.")
        renameat2.argtypes = (
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
        )
        renameat2.restype = ctypes.c_int
        result = renameat2(
            parent_fd, os.fsencode(source_name), parent_fd, os.fsencode(target_name), 1,
        )
        if result != 0:
            error_code = ctypes.get_errno()
            if error_code in {errno.EEXIST, errno.ENOTEMPTY}:
                raise StorageTargetExistsError(
                    f"Storage target already exists and will not be overwritten: {relative_path!r}."
                )
            if error_code in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP, errno.EXDEV}:
                raise StorageOperationError(
                    "Atomic no-replace rename is unsupported for this storage location."
                )
            raise OSError(error_code, os.strerror(error_code), relative_path)

    def _copy_posix(self, source_relative_path: str, target_relative_path: str, *, root: str) -> StorageEntry:
        """Stage and publish a copy relative to one held destination directory fd.

        Linux renameat2 enforces no-replace. This pins directories, not the
        final destination's immutable generation or a DB transaction.
        """
        import secrets

        base_root = self._select_root(root)
        normalized = _normalize_relative(target_relative_path)
        if not normalized:
            raise StorageOperationError("A regular file path is required for storage copy.")
        parts = normalized.split("/")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fds: list[int] = []
        staging_name: str | None = None
        size: int | None = None
        try:
            parent_fd = os.open(base_root, flags)
            fds.append(parent_fd)
            for component in parts[:-1]:
                try:
                    os.mkdir(component, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                parent_fd = os.open(component, flags, dir_fd=parent_fd)
                fds.append(parent_fd)

            with self.read_stream(source_relative_path, root=root) as stream:
                source_stat = os.fstat(stream.fileno())
                for _ in range(8):
                    candidate = ".gxp-stage-" + secrets.token_hex(16) + ".tmp"
                    try:
                        staged_fd = os.open(
                            candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o600, dir_fd=parent_fd,
                        )
                    except FileExistsError:
                        continue
                    staging_name = candidate
                    break
                else:
                    raise StorageOperationError("Unable to allocate a private staging file.")

                try:
                    staged_stream = os.fdopen(staged_fd, "wb")
                except BaseException:
                    os.close(staged_fd)
                    raise
                with staged_stream:
                    shutil.copyfileobj(stream, staged_stream, length=1024 * 1024)
                    staged_stream.flush()
                    os.fchmod(staged_stream.fileno(), stat.S_IMODE(source_stat.st_mode))
                    os.utime(
                        staged_stream.fileno(),
                        ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns),
                    )
                    size = os.fstat(staged_stream.fileno()).st_size

            self._rename_noreplace_dirfd(parent_fd, staging_name, parts[-1], target_relative_path)
            staging_name = None
        finally:
            if staging_name is not None and fds:
                try:
                    os.unlink(staging_name, dir_fd=fds[-1])
                except FileNotFoundError:
                    pass
            for fd in reversed(fds):
                os.close(fd)
        return StorageEntry(relative_path=normalized, name=parts[-1], is_dir=False, size=size)

    def copy(self, source_relative_path: str, target_relative_path: str, *, root: str = "inspection") -> StorageEntry:
        if os.name == "posix":
            return self._copy_posix(source_relative_path, target_relative_path, root=root)
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
            # Hold the verified source descriptor while copying bytes and
            # metadata. Re-opening source or copystat(source) after checking
            # containment can follow a concurrently swapped parent symlink.
            with self.read_stream(source_relative_path, root=root) as stream, tempfile.NamedTemporaryFile(
                delete=False, dir=target.parent, prefix=".gxp-stage-", suffix=".tmp"
            ) as tmp:
                temp_path = Path(tmp.name)
                source_stat = os.fstat(stream.fileno())
                shutil.copyfileobj(stream, tmp, length=1024 * 1024)
                tmp.flush()  # Buffered writes must finish before setting mtime.
                if os.name == "posix":
                    os.fchmod(tmp.fileno(), stat.S_IMODE(source_stat.st_mode))
                    os.utime(tmp.fileno(), ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
                else:
                    # No POSIX descriptor-anchored contract on this platform.
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

    @staticmethod
    def _rename_noreplace_between_dirfds(
        source_fd: int, source_name: str, target_fd: int, target_name: str,
        relative_path: str,
    ) -> None:
        """Atomic Linux no-replace between descriptor-pinned parents."""
        if not sys.platform.startswith("linux"):
            raise StorageOperationError("Atomic no-replace rename is unsupported on this platform.")
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise StorageOperationError("Atomic no-replace rename is unavailable on this runtime.")
        renameat2.argtypes = (
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
        )
        renameat2.restype = ctypes.c_int
        result = renameat2(
            source_fd, os.fsencode(source_parts[-1]),
            target_fd, os.fsencode(target_parts[-1]), 1,
        )
        if result != 0:
            code = ctypes.get_errno()
            if code in {errno.EEXIST, errno.ENOTEMPTY}:
                raise StorageTargetExistsError(
                f"Storage target already exists and will not be overwritten: {relative_path!r}."
                )
            if code in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP, errno.EXDEV}:
                raise StorageOperationError("Atomic no-replace rename is unsupported for this storage location.")
            raise OSError(code, os.strerror(code), relative_path)
    def _relocate_posix(
        self, source_relative_path: str, target_relative_path: str, *, root: str,
        create_target_parents: bool,
    ) -> StorageEntry:
        """No-follow source/destination parents, held through atomic no-replace.

        Final-leaf identity may change between stat and rename; directory FDs
        protect against parent symlink redirection, not generation pinning.
        """
        base_root = self._select_root(root)
        source_rel = _normalize_relative(source_relative_path)
        target_rel = _normalize_relative(target_relative_path)
        if not source_rel or not target_rel:
            raise StorageOperationError("Regular source and destination paths are required.")
        source_parts, target_parts = source_rel.split("/"), target_rel.split("/")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fds: list[int] = []
        try:
            source_fd = os.open(base_root, flags)
            fds.append(source_fd)
            for part in source_parts[:-1]:
                source_fd = os.open(part, flags, dir_fd=source_fd)
                fds.append(source_fd)
            source_stat = os.stat(source_parts[-1], dir_fd=source_fd, follow_symlinks=False)
            if not (stat.S_ISREG(source_stat.st_mode) or stat.S_ISDIR(source_stat.st_mode)):
                raise StorageOperationError("Storage relocation source must be a regular file or directory.")

            target_fd = os.open(base_root, flags)
            fds.append(target_fd)
            for part in target_parts[:-1]:
                if create_target_parents:
                    try:
                        os.mkdir(part, dir_fd=target_fd)
                    except FileExistsError:
                        pass
                target_fd = os.open(part, flags, dir_fd=target_fd)
                fds.append(target_fd)
            self._rename_noreplace_between_dirfds(
                source_fd, source_parts[-1], target_fd, target_parts[-1], target_relative_path,
            )
            return StorageEntry(
                relative_path=target_rel, name=target_parts[-1],
                is_dir=stat.S_ISDIR(source_stat.st_mode),
                size=None if stat.S_ISDIR(source_stat.st_mode) else source_stat.st_size,
            )
        finally:
            for fd in reversed(fds):
                os.close(fd)

    def move(self, source_relative_path: str, target_relative_path: str, *, root: str = "inspection") -> StorageEntry:
        if os.name == "posix":
            return self._relocate_posix(source_relative_path, target_relative_path, root=root, create_target_parents=True)
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
        if os.name == "posix":
            normalized = _normalize_relative(source_relative_path)
            if not normalized:
                raise StorageOperationError("Regular source path is required.")
            target_relative_path = normalized.rsplit("/", 1)[0] + "/" + new_name if "/" in normalized else new_name
            return self._relocate_posix(
                source_relative_path, target_relative_path, root=root,
                create_target_parents=False,
            )
        base_root = self._select_root(root)
        source = self._path_under(base_root, source_relative_path)
        target = source.with_name(new_name)
        self._ensure_within_root(base_root, target)
        self._require_vacant_target(target, target.relative_to(base_root).as_posix())
        self._rename_noreplace(source, target, target.relative_to(base_root).as_posix())
        return self._entry_for(base_root, target)

    def checksum(self, relative_path: str, *, root: str = "inspection") -> str:
        # Use the same descriptor-anchored, no-follow read path as binary audits.
        # Resolving a pathname and then reopening it has a symlink-swap window.
        digest = sha256()
        with self.read_stream(relative_path, root=root) as fh:
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
