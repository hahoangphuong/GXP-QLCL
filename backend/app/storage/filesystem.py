from __future__ import annotations

from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig


class FilesystemStorageService(LocalStorageService):
    """
    Filesystem-backed adapter usable for both local paths and private-share/UNC
    paths, as long as the host OS can mount or access them as a filesystem root.
    """

    def __init__(self, config: StorageConfig):
        super().__init__(config)
