"""Local offline package acquisition only; not a StorageService adapter.

No network paths, writes, symlink following, or pathname reopen after hashing.
POSIX walks pinned directory descriptors; Windows holds no-write/no-delete
handles to ancestors and checks reparse attributes and final handle paths.
"""
from contextlib import ExitStack, contextmanager
import os
from pathlib import Path
import re
import stat

JSON_LIMIT = 1024 * 1024
FILE_LIMIT = 32 * 1024 * 1024
PACKAGE_LIMIT = 128 * 1024 * 1024


class EvidenceBlocked(ValueError):
    """Contains a fixed non-sensitive code, never a filesystem exception text."""


def relative_parts(value: str) -> tuple[str, ...]:
    if type(value) is not str or len(value) > 512:
        raise EvidenceBlocked("QDKT_PACKAGE_PATH_UNSAFE")
    parts = tuple(value.split("/"))
    for part in parts:
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,127}", part)
            or part.endswith((".", " "))
            or part.split(".")[0].rstrip(" ").upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}):
            raise EvidenceBlocked("QDKT_PACKAGE_PATH_UNSAFE")
    return parts


@contextmanager
def _windows_fd(root: Path, parts: tuple[str, ...]):
    import ctypes
    from ctypes import wintypes
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    kernel.GetFileType.argtypes = [wintypes.HANDLE]

    class Attributes(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]

    if not re.fullmatch(r"[A-Za-z]:\\", root.anchor):
        raise EvidenceBlocked("QDKT_PACKAGE_PATH_UNSAFE")
    with ExitStack() as stack:
        current = Path(root.anchor)
        components = list(root.parts[1:]) + list(parts)
        for index in range(-1, len(components)):
            if index >= 0:
                current /= components[index]
            # OPEN_EXISTING; FILE_SHARE_READ only locks out writers and rename.
            handle = kernel.CreateFileW(str(current), 0x80000000, 1, None, 3, 0x02200000, None)
            if handle == wintypes.HANDLE(-1).value:
                raise EvidenceBlocked("QDKT_PACKAGE_FILE_UNAVAILABLE")
            owned_handle = [handle]
            stack.callback(lambda owned: kernel.CloseHandle(owned[0]) if owned else None, owned_handle)
            info = Attributes()
            if not kernel.GetFileInformationByHandleEx(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
                raise EvidenceBlocked("QDKT_PACKAGE_FILE_UNAVAILABLE")
            if info.attributes & 0x400:
                raise EvidenceBlocked("QDKT_PACKAGE_LINK_FORBIDDEN")
            final = ctypes.create_unicode_buffer(32768)
            length = kernel.GetFinalPathNameByHandleW(handle, final, len(final), 0)
            if (not length or length >= len(final) or kernel.GetFileType(handle) != 1
                or os.path.normcase(os.path.normpath(final.value.removeprefix("\\\\?\\"))) != os.path.normcase(os.path.normpath(str(current)))):
                raise EvidenceBlocked("QDKT_PACKAGE_PATH_UNSAFE")
            is_directory = bool(info.attributes & 0x10)
            if is_directory != (index < len(components) - 1):
                raise EvidenceBlocked("QDKT_PACKAGE_FILE_TYPE_INVALID")
            if not is_directory:
                fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
                # Transfer the one file handle to fd; directory callbacks stay.
                owned_handle.clear()
                try:
                    yield fd
                finally:
                    os.close(fd)


@contextmanager
def _posix_fd(root: Path, parts: tuple[str, ...]):
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise EvidenceBlocked("QDKT_PACKAGE_PLATFORM_UNSUPPORTED")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
    with ExitStack() as stack:
        parent = os.open("/", flags)
        stack.callback(os.close, parent)
        for component in (*root.parts[1:], *parts[:-1]):
            parent = os.open(component, flags, dir_fd=parent)
            stack.callback(os.close, parent)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        stack.callback(os.close, fd)
        yield fd


def read_evidence(root: Path, relative: str, limit: int) -> bytes:
    parts = relative_parts(relative)
    try:
        reader = _windows_fd if os.name == "nt" else _posix_fd
        with reader(root, parts) as fd:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise EvidenceBlocked("QDKT_PACKAGE_FILE_TYPE_INVALID")
            if before.st_size > limit:
                raise EvidenceBlocked("QDKT_PACKAGE_FILE_TOO_LARGE")
            chunks, count = [], 0
            while chunk := os.read(fd, min(65536, limit + 1 - count)):
                count += len(chunk)
                if count > limit:
                    raise EvidenceBlocked("QDKT_PACKAGE_FILE_TOO_LARGE")
                chunks.append(chunk)
            after = os.fstat(fd)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
            ) or count != before.st_size or after.st_nlink != 1:
                raise EvidenceBlocked("QDKT_PACKAGE_FILE_CHANGED")
            return b"".join(chunks)
    except OSError as exc:
        raise EvidenceBlocked("QDKT_PACKAGE_FILE_UNAVAILABLE") from exc
