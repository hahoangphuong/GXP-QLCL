from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import DocumentVariantType
from backend.app.db.models.phase1 import TemplateBinding, TemplateDefinition
from backend.app.document.contextual_actions import get_case_document_context_spec
from backend.app.document.inspection_qd_kt_template_asset_contract import (
    get_inspection_qd_kt_template_asset,
    load_inspection_qd_kt_template_assets,
)
from backend.app.document.persistence import _lookup_template_binding
from backend.app.document.registry import TemplateRegistryEntry
from backend.app.document.service_contract import (
    DocumentGenerationPlan,
    DocumentGenerationRequest,
    DocumentPayloadEnvelope,
    TemplateSelectionInput,
    TemplateSelectionResult,
    select_template_entry,
)
from backend.app.document.template_binary import (
    TemplateBinaryError,
    build_template_binary_requirement,
    open_template_binary_stream,
)
from backend.app.document.template_binary_binding import (
    TemplateBinaryBinding,
    TemplateBinaryBindingError,
    assign_template_binary_binding,
    get_template_binary_binding_locator,
    normalize_template_binary_relative_path,
)
from tools.seed_inspection_qd_kt_template_metadata import (
    InspectionQdKtTemplateMetadataSeedError,
    _preflight_assets,
)


def _definition() -> TemplateDefinition:
    return TemplateDefinition(
        family_code="INSPECTION_QD_KT",
        document_type_code="inspection_qd_kt",
        source_application="Word",
        storage_scope="inspection_folder",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_number=2,
        variant_type=DocumentVariantType.EDITABLE_DOCX,
        template_name="2. QD KT - {GP}.dotx",
        template_pattern="2. QD KT - {GP}.dotx",
        bookmark_contract=None,
        is_active=True,
    )


def _allocation(definition_id: str, binding_id: str | None, gxp_type: str = "GMP"):
    return SimpleNamespace(
        prepared=SimpleNamespace(
            persisted_state=SimpleNamespace(
                template_definition_id=definition_id,
                template_binding_id=binding_id,
            ),
            generation_plan=SimpleNamespace(
                request=SimpleNamespace(gxp_type=gxp_type),
                template=SimpleNamespace(
                    family_code="INSPECTION_QD_KT",
                    template_pattern="2. QD KT - {GP}.dotx",
                ),
            ),
        )
    )


def _plan(gxp_type: str) -> DocumentGenerationPlan:
    template = TemplateSelectionResult(
        family_code="INSPECTION_QD_KT",
        logical_name="Quyết định kiểm tra",
        template_pattern="2. QD KT - {GP}.dotx",
        source_application="Word",
        storage_scope="inspection_folder",
        host_procedure="RecordForm.CreateFile",
        population_procedures=(),
        bookmarks=(),
        copy_forward_dependencies=(),
    )
    return DocumentGenerationPlan(
        request=DocumentGenerationRequest(
            family_code="INSPECTION_QD_KT",
            requested_by_user_id=None,
            gxp_type=gxp_type,
            storage_scope="inspection_folder",
        ),
        template=template,
        payload=DocumentPayloadEnvelope(
            family_code="INSPECTION_QD_KT",
            fields=(),
            source_procedures=(),
        ),
        source_dependencies=(),
    )


def _session() -> Session:
    # Importing TemplateBinaryBinding registers its table before the in-memory schema is created.
    _ = TemplateBinaryBinding
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_qd_asset_contract_contains_authoritative_four_gxp_mappings():
    assets = {asset.gxp_type: asset for asset in load_inspection_qd_kt_template_assets()}

    assert set(assets) == {"GMP", "GLP", "GMPbb", "GSP"}
    for gxp_type, asset in assets.items():
        assert asset.storage_root == "template"
        assert asset.storage_relative_path == f"2. QD KT - {gxp_type}.dotx"
        assert asset.filename == f"2. QD KT - {gxp_type}.dotx"
        assert len(asset.checksum_sha256) == 64


@pytest.mark.parametrize("path", ["../escape.dotx", "/etc/passwd", r"C:\\temp\\template.dotx", r"\\server\\share\\x.dotx"])
def test_template_binary_locator_rejects_traversal_and_absolute_paths(path):
    with pytest.raises(TemplateBinaryBindingError):
        normalize_template_binary_relative_path(path)
    with pytest.raises(TemplateBinaryError):
        from backend.app.document.template_binary import _normalize_relative_path

        _normalize_relative_path(path)


def test_generic_registry_selector_accepts_gxp_placeholder():
    entry = TemplateRegistryEntry(
        family_code="INSPECTION_QD_KT",
        logical_name="Quyết định kiểm tra",
        source_application="Word",
        storage_scope="inspection_folder",
        legacy_host_procedure="RecordForm.CreateFile",
        legacy_case_numbers=(2,),
        template_pattern="2. QD KT - {GP}.dotx",
        selection_legacy_mode=None,
        population_procedures=(),
        bookmarks=(),
    )

    selected = select_template_entry(
        (entry,),
        TemplateSelectionInput(
            family_code="INSPECTION_QD_KT",
            gxp_type="GMPbb",
            storage_scope="inspection_folder",
        ),
    )

    assert selected.template_pattern == "2. QD KT - {GP}.dotx"


@pytest.mark.parametrize("gxp_type", ["GMP", "GLP", "GMPbb", "GSP"])
def test_qd_exact_binding_is_selected_and_resolves_its_exact_binary(gxp_type):
    session = _session()
    try:
        definition = _definition()
        session.add(definition)
        session.flush()
        generic = TemplateBinding(
            family_code=definition.family_code,
            template_definition_id=definition.id,
            gxp_type="{GP}",
            legacy_mode=None,
            storage_scope=definition.storage_scope,
            is_active=True,
        )
        exact = TemplateBinding(
            family_code=definition.family_code,
            template_definition_id=definition.id,
            gxp_type=gxp_type,
            legacy_mode=None,
            storage_scope=definition.storage_scope,
            is_active=True,
        )
        session.add_all([generic, exact])
        session.flush()
        asset = get_inspection_qd_kt_template_asset(gxp_type)
        assign_template_binary_binding(
            session,
            template_binding_id=exact.id,
            storage_root=asset.storage_root,
            storage_relative_path=asset.storage_relative_path,
            original_filename=asset.filename,
            checksum_sha256=asset.checksum_sha256,
        )

        selected = _lookup_template_binding(session, _plan(gxp_type), definition)
        requirement = build_template_binary_requirement(session, _allocation(definition.id, selected.id, gxp_type))

        assert selected.id == exact.id
        assert requirement.readiness_status == "direct_stream_ready"
        assert requirement.storage_relative_path == asset.storage_relative_path
        assert requirement.checksum_sha256 == asset.checksum_sha256
    finally:
        session.close()


def test_qd_missing_exact_binding_cannot_fall_back_to_generic_definition_locator():
    session = _session()
    try:
        definition = _definition()
        definition.template_storage_root = "template"
        definition.template_storage_relative_path = "generic.dotx"
        session.add(definition)
        session.flush()
        generic = TemplateBinding(
            family_code=definition.family_code,
            template_definition_id=definition.id,
            gxp_type="{GP}",
            legacy_mode=None,
            storage_scope=definition.storage_scope,
            is_active=True,
        )
        session.add(generic)
        session.flush()

        requirement = build_template_binary_requirement(session, _allocation(definition.id, generic.id))

        assert requirement.readiness_status == "missing_exact_template_binding"
        assert requirement.storage_relative_path is None
    finally:
        session.close()


class _FakeStorage:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.calls: list[tuple[str, str]] = []

    @contextmanager
    def read_stream(self, relative_path: str, *, root: str = "inspection"):
        self.calls.append((root, relative_path))
        yield BytesIO(self.payload)


def test_renderer_stream_opens_the_exact_resolved_qd_locator():
    payload = b"isolated-template-fixture"
    asset = get_inspection_qd_kt_template_asset("GMP")
    storage = _FakeStorage(payload)
    requirement = SimpleNamespace(
        readiness_status="direct_stream_ready",
        storage_root=asset.storage_root,
        storage_relative_path=asset.storage_relative_path,
        checksum_sha256=sha256(payload).hexdigest(),
    )

    with open_template_binary_stream(storage, requirement) as stream:
        assert stream.read() == payload

    assert storage.calls == [("template", "2. QD KT - GMP.dotx")]


def test_missing_binary_preflight_fails_closed_without_database_access():
    class MissingStorage:
        def exists(self, relative_path: str, *, root: str) -> bool:
            return False

    with pytest.raises(InspectionQdKtTemplateMetadataSeedError, match="is missing"):
        _preflight_assets(MissingStorage())


def test_ambiguous_binary_binding_is_rejected():
    class DuplicateSession:
        def scalars(self, _statement):
            return [object(), object()]

    with pytest.raises(TemplateBinaryBindingError, match="Ambiguous"):
        get_template_binary_binding_locator(DuplicateSession(), "binding-1")


def test_qd_contextual_create_remains_business_input_blocked():
    spec = get_case_document_context_spec("INSPECTION_QD_KT")

    assert spec is not None
    assert spec.create_readiness == "BUSINESS_INPUT_CONTRACT_MISSING"
