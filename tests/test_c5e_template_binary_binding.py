from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace
import hashlib

import pytest

from backend.app.document import template_binary
from backend.app.document.c5e_certificate_destination_asset_contract import (
    CertificateDestinationAsset,
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
    TemplateBinaryBindingLocator,
    normalize_template_binary_checksum,
    normalize_template_binary_relative_path,
)
from tools.seed_c5e_certificate_template_metadata import (
    C5ECertificateTemplateMetadataSeedError,
    _validate_binary_locator_matches_asset,
)


def _allocated(
    *,
    definition_id="td1",
    binding_id="tb1",
    request_gxp_type=None,
    canonical_gxp_type="GMP",
):
    return SimpleNamespace(
        prepared=SimpleNamespace(
            persisted_state=SimpleNamespace(
                template_definition_id=definition_id,
                template_binding_id=binding_id,
            ),
            generation_plan=SimpleNamespace(
                request=SimpleNamespace(gxp_type=request_gxp_type),
                template=SimpleNamespace(
                    family_code="CERTIFICATE_ISSUANCE_WORD",
                    template_pattern="9. Chung chi {GP} (moi).dotx",
                ),
            ),
            certificate_detail_projection=(
                None
                if canonical_gxp_type is None
                else SimpleNamespace(gxp_type=canonical_gxp_type)
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


def _install_template_lookup(monkeypatch, *, definition, binding=None, locator=None):
    from backend.app.db.models.phase1 import TemplateBinding

    class FakeSession:
        def get(self, model, identity):
            assert model is TemplateBinding
            assert identity == "tb1"
            return binding

    monkeypatch.setattr(
        template_binary,
        "_load_template_definition",
        lambda session, definition_id: definition,
    )
    monkeypatch.setattr(
        template_binary,
        "get_template_binary_binding_locator",
        lambda session, binding_id: locator,
    )
    return FakeSession()


@pytest.mark.parametrize("gxp_type", ["GMP", "GLP"])
def test_c5e_exact_case_gxp_binding_takes_precedence_over_definition(monkeypatch, gxp_type):
    asset = get_certificate_destination_asset(gxp_type)
    definition = _definition(
        template_storage_root="template",
        template_storage_relative_path="wrong-definition.dotx",
        template_checksum_sha256="0" * 64,
    )
    binding = SimpleNamespace(id="tb1", gxp_type=gxp_type)
    locator = SimpleNamespace(
        storage_root=asset.storage_root,
        storage_relative_path=asset.storage_relative_path,
        original_filename=asset.filename,
        checksum_sha256=asset.checksum_sha256,
    )
    session = _install_template_lookup(
        monkeypatch, definition=definition, binding=binding, locator=locator,
    )

    requirement = build_template_binary_requirement(
        session, _allocated(canonical_gxp_type=gxp_type),
    )

    assert requirement.readiness_status == "direct_stream_ready"
    assert requirement.storage_relative_path == asset.storage_relative_path
    assert requirement.checksum_sha256 == asset.checksum_sha256
    assert "exact GxP" in requirement.detail


def test_c5e_generic_template_definition_never_replaces_exact_binding(monkeypatch):
    asset = get_certificate_destination_asset("GMP")
    definition = _definition(
        template_storage_root="template",
        template_storage_relative_path=asset.storage_relative_path,
        template_original_filename=asset.filename,
        template_checksum_sha256=asset.checksum_sha256,
    )
    session = _install_template_lookup(
        monkeypatch, definition=definition, binding=None, locator=None,
    )

    requirement = build_template_binary_requirement(session, _allocated())

    assert requirement.readiness_status == "missing_exact_template_binding"
    assert requirement.storage_relative_path is None


@pytest.mark.parametrize("field", [
    "storage_root", "storage_relative_path", "original_filename", "checksum_sha256",
])
def test_c5e_mismatched_destination_binding_fails_closed(monkeypatch, field):
    asset = get_certificate_destination_asset("GMP")
    values = {
        "storage_root": asset.storage_root,
        "storage_relative_path": asset.storage_relative_path,
        "original_filename": asset.filename,
        "checksum_sha256": asset.checksum_sha256,
    }
    values[field] = "0" * 64 if field == "checksum_sha256" else "untrusted.dotx"
    session = _install_template_lookup(
        monkeypatch,
        definition=_definition(),
        binding=SimpleNamespace(id="tb1", gxp_type="GMP"),
        locator=SimpleNamespace(**values),
    )

    requirement = build_template_binary_requirement(session, _allocated())

    assert requirement.readiness_status == "invalid_template_binding"
    assert requirement.storage_relative_path is None


@pytest.mark.parametrize("gxp_type", ["GSP", "GDP", "GMPbb"])
def test_c5e_unapproved_destination_types_cannot_use_generic_fallback(
    monkeypatch, gxp_type,
):
    session = _install_template_lookup(
        monkeypatch,
        definition=_definition(
            template_storage_root="template",
            template_storage_relative_path="arbitrary.dotx",
            template_checksum_sha256="f" * 64,
        ),
    )

    requirement = build_template_binary_requirement(
        session, _allocated(canonical_gxp_type=gxp_type),
    )

    assert requirement.readiness_status == "invalid_template_binding"
    assert requirement.storage_relative_path is None


def test_c5e_absent_canonical_projection_cannot_use_explicit_request_fallback(monkeypatch):
    session = _install_template_lookup(
        monkeypatch, definition=_definition(),
    )
    requirement = build_template_binary_requirement(
        session,
        _allocated(request_gxp_type="GMP", canonical_gxp_type=None),
    )
    assert requirement.readiness_status == "invalid_template_binding"


def test_c5e_request_gxp_must_not_disagree_with_case_projection(monkeypatch):
    session = _install_template_lookup(
        monkeypatch, definition=_definition(),
    )
    requirement = build_template_binary_requirement(
        session,
        _allocated(request_gxp_type="GLP", canonical_gxp_type="GMP"),
    )
    assert requirement.readiness_status == "invalid_template_binding"


def test_non_c5e_generic_definition_locator_remains_backward_compatible(monkeypatch):
    definition = _definition(
        family_code="OTHER_WORD_FAMILY",
        template_storage_root="template",
        template_storage_relative_path="generic.dotx",
        template_original_filename="generic.dotx",
        template_checksum_sha256="2" * 64,
    )
    session = _install_template_lookup(
        monkeypatch, definition=definition, binding=None, locator=None,
    )

    requirement = build_template_binary_requirement(session, _allocated())
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


def _asset() -> CertificateDestinationAsset:
    return CertificateDestinationAsset(
        gxp_type="GMP",
        filename="9. Chung chi GMP (moi).dotx",
        storage_root="template",
        storage_relative_path="9. Chung chi GMP (moi).dotx",
        checksum_sha256=(
            "1cb661d70bb7badb2dd0260a4fdde82c07db9cbf670bc09da737576d053fbfcb"
        ),
    )


def _locator(**overrides) -> TemplateBinaryBindingLocator:
    asset = _asset()
    values = {
        "template_binding_id": "tb1",
        "storage_root": asset.storage_root,
        "storage_relative_path": asset.storage_relative_path,
        "original_filename": asset.filename,
        "checksum_sha256": asset.checksum_sha256,
    }
    values.update(overrides)
    return TemplateBinaryBindingLocator(**values)


def test_existing_binary_locator_exact_match_is_idempotent():
    _validate_binary_locator_matches_asset(_locator(), _asset())


@pytest.mark.parametrize(
    ("field_name", "wrong_value"),
    [
        ("storage_root", "inspection"),
        ("storage_relative_path", "wrong.dotx"),
        ("original_filename", "wrong.dotx"),
        ("checksum_sha256", "0" * 64),
    ],
)
def test_existing_binary_locator_conflict_fails_closed(field_name, wrong_value):
    with pytest.raises(
        C5ECertificateTemplateMetadataSeedError,
        match="Existing template binary binding conflicts",
    ):
        _validate_binary_locator_matches_asset(
            _locator(**{field_name: wrong_value}),
            _asset(),
        )
