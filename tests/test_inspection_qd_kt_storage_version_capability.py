"""Synthetic capability checks: no DB, NAS, GCS or bridge access."""
from types import SimpleNamespace
import pytest
from backend.app.document.inspection_qd_kt_storage_version_capability import (
    QdKtStorageVersionPinBlocked, StorageVersionPinStatus,
    inspect_qdkt_storage_version_capability, require_qdkt_immutable_storage_version,
)


@pytest.mark.parametrize("adapter", ["local_filesystem_fake", "synology_smb", "external_bridge_http"])
def test_known_adapters_cannot_claim_immutable_generation(adapter):
    fake = SimpleNamespace(config=SimpleNamespace(storage_class=adapter))
    evidence = inspect_qdkt_storage_version_capability(fake)
    assert evidence.status is StorageVersionPinStatus.UNSUPPORTED
    assert not evidence.immutable_version_read_verified
    assert not evidence.ready_to_render
    with pytest.raises(QdKtStorageVersionPinBlocked, match="IMMUTABLE_VERSION_UNPROVEN:UNSUPPORTED"):
        require_qdkt_immutable_storage_version(fake)


@pytest.mark.parametrize("adapter", [None, "", "future_adapter"])
def test_unknown_adapters_default_to_unverified(adapter):
    fake = SimpleNamespace(config=SimpleNamespace(storage_class=adapter))
    evidence = inspect_qdkt_storage_version_capability(fake)
    assert evidence.status is StorageVersionPinStatus.UNVERIFIED_ADAPTER
    assert not evidence.immutable_version_read_verified
    with pytest.raises(QdKtStorageVersionPinBlocked, match="UNVERIFIED_ADAPTER"):
        require_qdkt_immutable_storage_version(fake)


def test_metadata_claims_cannot_upgrade_storage_adapter():
    fake = SimpleNamespace(
        config=SimpleNamespace(storage_class="synology_smb"),
        generation="1234", etag='"trusted"', checksum_sha256="a" * 64,
        size=100, version_id="version-1", immutable_version_read_verified=True,
    )
    with pytest.raises(QdKtStorageVersionPinBlocked, match="UNSUPPORTED"):
        require_qdkt_immutable_storage_version(fake)
