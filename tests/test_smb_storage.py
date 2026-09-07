from __future__ import annotations

from backend.app.db.enums import StorageResolutionStatus
from backend.app.storage import smb as smb_storage
from backend.app.storage.types import SmbStorageConfig


class _DirectoryEntry:
    def __init__(self, path: str, name: str) -> None:
        self.path = path
        self.name = name

    def is_dir(self) -> bool:
        return True


class _FakeSmbClient:
    def __init__(self, directory_names: list[str]) -> None:
        self.client_config_calls: list[dict[str, str | None]] = []
        self.registered_sessions: list[tuple[str, dict[str, object]]] = []
        self.connection_cache_available = True
        self.directory_names = directory_names

    def ClientConfig(self, **kwargs: str | None) -> None:
        self.client_config_calls.append(kwargs)

    def register_session(self, server: str, **kwargs: object) -> None:
        self.registered_sessions.append((server, kwargs))

    def reset_connection_cache(self) -> None:
        self.connection_cache_available = False

    def scandir(self, path: str) -> list[_DirectoryEntry]:
        if not self.connection_cache_available:
            assert self.client_config_calls == [{"username": "test-user", "password": "test-password"}]
        return [_DirectoryEntry(path + "\\" + name, name) for name in self.directory_names]


class _FakeSmbPath:
    pass


def _service(monkeypatch, directory_names: list[str]) -> tuple[_FakeSmbClient, smb_storage.SmbStorageService]:
    fake_client = _FakeSmbClient(directory_names)
    monkeypatch.setattr(smb_storage, "smbclient", fake_client)
    monkeypatch.setattr(smb_storage, "smbpath", _FakeSmbPath())
    service = smb_storage.SmbStorageService(
        SmbStorageConfig(
            inspection_root=r"\\server\inspection",
            dkkd_root=r"\\server\dkkd",
            username="test-user",
            password="test-password",
            port=1445,
            encrypt=True,
            connection_timeout=17,
            auth_protocol="kerberos",
        )
    )
    return fake_client, service


def test_smb_service_configures_default_credentials_for_resolution_after_cache_loss(monkeypatch) -> None:
    folder_name = "IMEXPHARM - Đồng Tháp (ID-1)"
    fake_client, service = _service(monkeypatch, [folder_name])

    initial = service.resolve_dkkd_folder(site_legacy_id=1)
    fake_client.reset_connection_cache()
    after_cache_loss = service.resolve_dkkd_folder(site_legacy_id=1)

    assert initial.status is StorageResolutionStatus.RESOLVED
    assert after_cache_loss.status is StorageResolutionStatus.RESOLVED
    assert initial.candidate_count == 1
    assert initial.relative_path == folder_name
    assert fake_client.client_config_calls == [{"username": "test-user", "password": "test-password"}]
    assert len(fake_client.registered_sessions) == 2
    assert fake_client.registered_sessions[0][1] == {
        "username": "test-user",
        "password": "test-password",
        "port": 1445,
        "encrypt": True,
        "connection_timeout": 17,
        "auth_protocol": "kerberos",
    }


def test_smb_dkkd_resolution_rejects_obsolete_unkeyed_and_duplicate_identity_forms(monkeypatch) -> None:
    fake_client, service = _service(monkeypatch, ["Legacy sample (1)"])
    obsolete = service.resolve_dkkd_folder(site_legacy_id=1)

    assert obsolete.status is StorageResolutionStatus.NOT_FOUND
    assert obsolete.candidate_count == 0

    fake_client.directory_names = ["Phương Đông TNHH"]
    unkeyed = service.resolve_dkkd_folder(site_legacy_id=1)

    assert unkeyed.status is StorageResolutionStatus.NOT_FOUND
    assert unkeyed.candidate_count == 0

    fake_client.directory_names = [
        "TNHH BV Pharma - TP Hồ Chí Minh (ID-284)",
        "BV Pharma - TP Hồ Chí Minh (ID-284)",
    ]
    duplicate = service.resolve_dkkd_folder(site_legacy_id=284)

    assert duplicate.status is StorageResolutionStatus.AMBIGUOUS
    assert duplicate.candidate_count == 2
    assert duplicate.relative_path is None
