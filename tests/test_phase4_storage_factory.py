from pathlib import Path

from backend.app.storage import FilesystemStorageService
from backend.app.storage.factory import create_storage_service_from_env


def test_create_storage_service_from_env_returns_filesystem_adapter(tmp_path: Path):
    inspection_root = tmp_path / "inspection"
    inspection_root.mkdir()

    service = create_storage_service_from_env({"STORAGE_INSPECTION_ROOT": str(inspection_root)})

    assert isinstance(service, FilesystemStorageService)
    assert service.config.inspection_root == inspection_root
