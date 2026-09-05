from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace
import hashlib

import pytest

from backend.app.document import template_binary
from backend.app.document.c5e_certificate_destination_asset_contract import (
    CertificateDestinationAssetContractError,
    get_certificate_destination_asset,
    load_certificate_destination_assets,
)
from backend.app.document.template_binary import (
    TemplateBinaryError,
    TemplateBinaryRequirement,
    build_template_binary_requirement,
    open_template_binary_stream,
)
from backend.app.document.template_binary_binding import (
    TemplateBinaryBindingError,
    normalize_template_binary_checksum,
    normalize_template_binary_relative_path,
)


def _allocated(*, definition_id="td1", binding_id="tb1"):
    return SimpleNamespace(
        prepared=SimpleNamespace(
            persisted_state=SimpleNamespace(
                template_definition_id=definition_id,
                template_binding_id=binding_id,
            ),
            generation_plan=SimpleNamespace(
                template=SimpleNamespace(
                    family_code="CERTIFICATE_ISSUANCE_WORD",
                    template_pattern="9. Chung chi {GP} (moi).dotx",
                )
            ),
        )
    )


def _definition(**overrides):
    values = {
        "id": "td1",
        "family_code": "CERTIFICATE_ISSUANCE_WORD",
        "template_name": "9. Chung chi {GP} (moi).dotx",
        "template_storage_root": None,
        "template_storage_relative_path": None,
        "template_original_filename": None,
        "template_checksum_sha256": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_destination_contract_contains_exactly_gmp_and_glp():
    assets = load_certificate_destination_assets()
    assert {asset.gxp_type for asset in assets} == {"GMP", "GLP"}
    assert get_certificate_destination_asset("GMP").checksum_sha256 == (
        "1cb661d70bb7badb2dd0260a4fdde82c07db9cbf670bc09da737576d053fbfcb"
    )
    assert get_certificate_destination_asset("GLP").checksum_sha256 == (
        "e5565b9b2cca73cb19438aa61b456d7d99ac4223cf2c6764a0e2f5d7dc36b07d"
    )


def test_destination_contract_fails_closed_for_gsp_and_gdp():
    with pytest.raises(CertificateDestinationAssetContractError):
        get_certificate_destination_asset("GSP")
    with pytest.raises(CertificateDestinationAssetContractError):
        get_certificate_destination_asset("GDP")


def test_template_binary_binding_normalization_contract():
    assert normalize_template_binary_relative_path(r"a\b.dotx") == "a/b.dotx"
    digest = "A" * 64
    assert normalize_template_binary_checksum(digest) == "a" * 64

    with pytest.raises(TemplateBinaryBindingError):
        normalize_template_binary_relative_path("../escape.dotx")
    with pytest.raises(TemplateBinaryBindingError):
        normalize_template_binary_checksum("not-a-sha")


def test_binding_locator_precedes_definition_locator(monkeypatch):
    definition = _definition(
        template_storage_root="template",
        template_storage_relative_path="wrong-definition.dotx",
        template_checksum_sha256="0" * 64,
    )
    monkeypatch.setattr(
        template_binary,
        "_load_template_definition",
        lambda session, definition_id: definition,
    )
    monkeypatch.setattr(
        template_binary,
        "get_template_binary_binding_locator",
        lambda session, binding_id: SimpleNamespace(
            storage_root="template",
            storage_relative_path="9. Chung chi GMP (moi).dotx",
            original_filename="9. Chung chi GMP (moi).dotx",
            checksum_sha256="1" * 64,
        ),
    )

    requirement = build_template_binary_requirement(object(), _allocated())

    assert requirement.readiness_status == "direct_stream_ready"
    assert requirement.storage_relative_path == "9. Chung chi GMP (moi).dotx"
    assert requirement.checksum_sha256 == "1" * 64
    assert "TemplateBinding" in requirement.detail


def test_definition_locator_remains_backward_compatible(monkeypatch):
    definition = _definition(
        template_storage_root="template",
        template_storage_relative_path="generic.dotx",
        template_original_filename="generic.dotx",
        template_checksum_sha256="2" * 64,
    )
    monkeypatch.setattr(
        template_binary,
        "_load_template_definition",
        lambda session, definition_id: definition,
    )
    monkeypatch.setattr(
        template_binary,
        "get_template_binary_binding_locator",
        lambda session, binding_id: None,
    )

    requirement = build_template_binary_requirement(object(), _allocated())

    assert requirement.readiness_status == "direct_stream_ready"
    assert requirement.storage_relative_path == "generic.dotx"
    assert requirement.checksum_sha256 == "2" * 64
    assert "TemplateDefinition" in requirement.detail


class _FakeStorage:
    def __init__(self, payload: bytes):
        self.payload = payload

    @contextmanager
    def read_stream(self, relative_path: str, *, root: str = "inspection"):
        yield BytesIO(self.payload)


def _requirement(payload: bytes, *, checksum: str | None = None):
    return TemplateBinaryRequirement(
        template_definition_id="td1",
        family_code="CERTIFICATE_ISSUANCE_WORD",
        template_name="certificate",
        storage_root="template",
        storage_relative_path="certificate.dotx",
        original_filename="certificate.dotx",
        checksum_sha256=(checksum or hashlib.sha256(payload).hexdigest()),
        readiness_status="direct_stream_ready",
        detail="test",
    )


def test_open_template_binary_stream_verifies_checksum():
    payload = b"template-bytes"
    storage = _FakeStorage(payload)
    with open_template_binary_stream(storage, _requirement(payload)) as stream:
        assert stream.read() == payload


def test_open_template_binary_stream_fails_closed_on_checksum_mismatch():
    payload = b"template-bytes"
    storage = _FakeStorage(payload)
    requirement = _requirement(payload, checksum="0" * 64)
    with pytest.raises(TemplateBinaryError, match="checksum mismatch"):
        with open_template_binary_stream(storage, requirement):
            pass
