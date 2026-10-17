from __future__ import annotations

from io import BytesIO

import pytest

from backend.app.db.enums import StorageResolutionStatus
from backend.app.storage import smb as smb_storage
from backend.app.storage.types import SmbStorageConfig, StorageTargetExistsError


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
        self.directories_by_path: dict[str, list[str]] = {}

    def ClientConfig(self, **kwargs: str | None) -> None:
        self.client_config_calls.append(kwargs)

    def register_session(self, server: str, **kwargs: object) -> None:
        self.registered_sessions.append((server, kwargs))

    def reset_connection_cache(self) -> None:
        self.connection_cache_available = False

    def makedirs(self, path: str, exist_ok: bool = False) -> None:
        return None

    def scandir(self, path: str) -> list[_DirectoryEntry]:
        if not self.connection_cache_available:
            assert self.client_config_calls == [{"username": "test-user", "password": "test-password"}]
        names = self.directories_by_path.get(path, self.directory_names)
        return [_DirectoryEntry(path + "\\" + name, name) for name in names]


class _FakeSmbPath:
    @staticmethod
    def exists(path: str) -> bool:
        return True

    @staticmethod
    def isdir(path: str) -> bool:
        return True


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


def test_smb_exclusive_write_rejects_existing_target(monkeypatch) -> None:
    fake_client, service = _service(monkeypatch, [])
    removed = []
    modes = []

    def stage_file(path, mode):
        assert ".gxp-stage-" in path
        modes.append(mode)
        return BytesIO()

    def collision(*args):
        raise OSError("STATUS_OBJECT_NAME_COLLISION")

    monkeypatch.setattr(fake_client, "open_file", stage_file, raising=False)
    monkeypatch.setattr(fake_client, "rename", collision, raising=False)
    monkeypatch.setattr(fake_client, "remove", removed.append, raising=False)

    with pytest.raises(StorageTargetExistsError, match="will not be overwritten"):
        service.write_stream("2026/existing.docx", BytesIO(b"new"), overwrite=False)

    assert modes == ["xb"]
    assert len(removed) == 1
    assert ".gxp-stage-" in removed[0]
    assert not removed[0].endswith("\\existing.docx")


@pytest.mark.parametrize("operation", ["move", "rename"])
def test_smb_file_operations_reject_existing_destination_before_rename(monkeypatch, operation: str) -> None:
    client, service = _service(monkeypatch, [])
    calls = []
    monkeypatch.setattr(client, "rename", lambda *args: calls.append(args), raising=False)

    with pytest.raises(StorageTargetExistsError, match="will not be overwritten"):
        if operation == "move":
            service.move("2026/source.txt", "2026/existing.txt")
        else:
            service.rename("2026/source.txt", "existing.txt")

    assert calls == []


@pytest.mark.parametrize("operation", ["move", "rename"])
def test_smb_rename_server_collision_after_preflight_returns_conflict(monkeypatch, operation: str):
    client, service = _service(monkeypatch, [])
    checks = []
    def fake_exists(path):
        checks.append(path)
        # Destination is initially absent; the concurrent writer creates it
        # before the server processes the no-replace SMB rename.
        return len(checks) > 1

    monkeypatch.setattr(smb_storage.smbpath, "exists", fake_exists)
    calls = []
    def reject_server_replace(source, target):
        calls.append((source, target))
        raise OSError("STATUS_OBJECT_NAME_COLLISION")

    monkeypatch.setattr(client, "rename", reject_server_replace, raising=False)
    with pytest.raises(StorageTargetExistsError, match="will not be overwritten"):
        if operation == "move":
            service.move("2026/source.txt", "2026/target.txt")
        else:
            service.rename("2026/source.txt", "target.txt")
    assert len(calls) == 1
    assert len(checks) == 2


def test_smb_copy_uses_exclusive_staging_and_never_wb(monkeypatch) -> None:
    client, service = _service(monkeypatch, [])
    modes = []
    removed = []

    def open_file(path, mode):
        modes.append(mode)
        if mode == "rb":
            return BytesIO(b"source")
        if mode == "xb":
            assert ".gxp-stage-" in path
            return BytesIO()
        raise AssertionError(f"Unsafe destination mode: {mode}")

    def collision(*args):
        raise OSError("STATUS_OBJECT_NAME_COLLISION")

    monkeypatch.setattr(client, "open_file", open_file, raising=False)
    monkeypatch.setattr(client, "rename", collision, raising=False)
    monkeypatch.setattr(client, "remove", removed.append, raising=False)

    with pytest.raises(StorageTargetExistsError, match="will not be overwritten"):
        service.copy("2026/source.txt", "2026/existing.txt")

    assert modes == ["rb", "xb"]
    assert len(removed) == 1 and ".gxp-stage-" in removed[0]


def test_smb_exclusive_write_publishes_only_after_stream_closed(monkeypatch) -> None:
    client, service = _service(monkeypatch, [])
    events = []
    removed = []

    class CaptureStream(BytesIO):
        def close(self):
            events.append("closed")
            super().close()

    def open_file(path, mode):
        assert ".gxp-stage-" in path and mode == "xb"
        events.append("stage-open")
        return CaptureStream()

    def rename(source, target):
        assert ".gxp-stage-" in source
        assert events == ["stage-open", "closed"]
        events.append("published")

    monkeypatch.setattr(client, "open_file", open_file, raising=False)
    monkeypatch.setattr(client, "rename", rename, raising=False)
    monkeypatch.setattr(client, "remove", removed.append, raising=False)
    monkeypatch.setattr(client, "stat", lambda path: type("Stat", (), {"st_size": 8})(), raising=False)
    monkeypatch.setattr(smb_storage.smbpath, "isdir", lambda path: False)

    entry = service.write_stream("2026/new.txt", BytesIO(b"complete"), overwrite=False)
    assert entry.relative_path == "2026/new.txt"
    assert events == ["stage-open", "closed", "published"]
    assert removed == []


def test_smb_exclusive_write_stream_interruption_removes_only_temp(monkeypatch) -> None:
    client, service = _service(monkeypatch, [])
    removed = []
    published = []

    class Interrupted:
        calls = 0

        def read(self, size):
            self.calls += 1
            if self.calls == 1:
                return b"partial"
            raise OSError("SMB stream interrupted")

    monkeypatch.setattr(client, "open_file", lambda path, mode: BytesIO(), raising=False)
    monkeypatch.setattr(client, "rename", lambda src, dst: published.append((src, dst)), raising=False)
    monkeypatch.setattr(client, "remove", removed.append, raising=False)

    with pytest.raises(OSError, match="SMB stream interrupted"):
        service.write_stream("2026/new.txt", Interrupted(), overwrite=False)

    assert published == []
    assert len(removed) == 1 and ".gxp-stage-" in removed[0]
    assert not removed[0].endswith("\\new.txt")


def test_smb_service_configures_default_credentials_for_resolution_after_cache_loss(monkeypatch) -> None:
    folder_name = "IMEXPHARM - Đồng Tháp (1)"
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


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Factory (1)", True),
        ("Factory (1) - Lần 2", True),
        ("Factory (ID-1)", False),
        ("Factory (10)", False),
        ("Factory (01)", False),
        ("Factory(1)", False),
        ("Factory (2)", False),
        ("Unkeyed facility", False),
    ],
)
def test_smb_dkkd_matches_exact_legacy_site_token(monkeypatch, name: str, expected: bool) -> None:
    _, service = _service(monkeypatch, [name])

    result = service.resolve_dkkd_folder(site_legacy_id=1)

    assert result.status is (
        StorageResolutionStatus.RESOLVED if expected else StorageResolutionStatus.NOT_FOUND
    )
    assert result.candidate_count == (1 if expected else 0)


def test_smb_dkkd_legacy_duplicate_identity_fails_closed(monkeypatch) -> None:
    _, service = _service(monkeypatch, [
        "TNHH BV Pharma - TP Hồ Chí Minh (284)",
        "BV Pharma - TP Hồ Chí Minh (284)",
    ])

    duplicate = service.resolve_dkkd_folder(site_legacy_id=284)

    assert duplicate.status is StorageResolutionStatus.AMBIGUOUS
    assert duplicate.candidate_count == 2
    assert duplicate.relative_path is None


def test_smb_inspection_resolution_requires_explicit_year(monkeypatch) -> None:
    fake_client, service = _service(monkeypatch, [])
    root = service.inspection_root
    fake_client.directories_by_path = {
        root: ["2024", "2025", "Templates"],
        root + r"\2024": ["Wrong - (ID-10) - (KT-1-GMP)"],
        root + r"\2025": ["Exact - (ID-1) - (KT-1-GMP)", "Legacy - (1) - (KT-1-GMP)"],
        root + r"\Templates": ["Ignored - (ID-1) - (KT-1-GMP)"],
    }

    resolution = service.resolve_inspection_folder(year=None, site_legacy_id=1, inspection_legacy_code="KT-1-GMP")

    assert resolution.status is StorageResolutionStatus.INVALID
    assert fake_client.directories_by_path == {
        root: ["2024", "2025", "Templates"],
        root + r"\2024": ["Wrong - (ID-10) - (KT-1-GMP)"],
        root + r"\2025": ["Exact - (ID-1) - (KT-1-GMP)", "Legacy - (1) - (KT-1-GMP)"],
        root + r"\Templates": ["Ignored - (ID-1) - (KT-1-GMP)"],
    }


def test_smb_inspection_resolution_keeps_explicit_year_exact_identity(monkeypatch) -> None:
    fake_client, service = _service(monkeypatch, [])
    root = service.inspection_root
    fake_client.directories_by_path = {root + r"\2025": ["Exact - (ID-1) - (KT-1-GMP)"]}

    resolution = service.resolve_inspection_folder(year=2025, site_legacy_id=1, inspection_legacy_code="KT-1-GMP")

    assert resolution.status is StorageResolutionStatus.RESOLVED
    assert resolution.relative_path == "2025/Exact - (ID-1) - (KT-1-GMP)"


def test_smb_staging_audit_streams_large_directory_without_materializing(monkeypatch):
    from backend.app.storage.staging import audit_staging_candidates
    from backend.app.storage.types import StorageEntry

    client, service = _service(monkeypatch, [])
    yielded = []
    def incremental(path):
        for i in range(300):
            yielded.append(i)
            yield _DirectoryEntry(path, f"item-{i:03d}.txt")

    monkeypatch.setattr(client, "scandir", incremental, raising=False)
    monkeypatch.setattr(service, "_entry_for", lambda root, target: StorageEntry(
        relative_path=target.rsplit("\\", 1)[-1],
        name=target.rsplit("\\", 1)[-1],
        is_dir=False, size=1,
    ))
    monkeypatch.setattr(service, "list", lambda *args, **kwargs: pytest.fail("materialized SMB list() called"))
    report = audit_staging_candidates(service, max_entries=4)
    assert report.truncated and report.incomplete_reason == "entry_budget_exceeded"
    assert report.scanned_entries == 4
    assert len(yielded) <= 5
