from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    Case,
    CaseEvaluationScope,
    CaseEvaluationScopeBlock,
    CaseEvaluationScopeSelection,
    CaseEvaluationScopeUnkeyedEntry,
    Company,
    EvaluationScopeTaxonomyNode,
    EvaluationScopeTaxonomyVersion,
    Site,
)
from backend.app.document.evaluation_scope_payload import (
    C5E_SCOPE_PROJECTION_SOURCE,
    assert_no_c5e_scope_field_override,
    enrich_payload_result_with_c5e_scope,
)
from backend.app.document.payload_builders import (
    DocumentPayloadBuildError,
    PayloadBuildInput,
    PayloadBuilderRegistryEntry,
    PayloadBuilderRegistryField,
    build_payload_envelope,
)
from backend.app.document.service import DocumentPreparationInput, build_document_payload_result
from backend.app.document.service_contract import DocumentGenerationRequest
from backend.app.read_models import DocumentGenerationPrepareRequest


def _engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _seed_case(session: Session, *, with_scope: bool = True, unkeyed: bool = False):
    company = Company(legal_name="C5e company")
    session.add(company)
    session.flush()
    site = Site(company_id=company.id, site_name="C5e site")
    session.add(site)
    session.flush()
    case = Case(site_id=site.id, gxp_type="GLP", state=CaseState.DRAFT, inspection_type="Định kỳ")
    session.add(case)
    session.flush()
    if not with_scope:
        session.commit()
        return case.id

    version = EvaluationScopeTaxonomyVersion(
        taxonomy_content_sha256="c" * 64,
        source_workbook_sha256="d" * 64,
        schema_version="evaluation-scope-taxonomy/v1",
    )
    session.add(version)
    session.flush()
    root = EvaluationScopeTaxonomyNode(
        taxonomy_version_id=version.id,
        gxp_type="GLP",
        source_name="PVCN_GLP",
        node_key="1",
        description="Root",
        hint=None,
        main_topic="MAIN",
        short_render="* Root",
        no_expand=None,
        source_order=1,
        source_excel_row=4,
    )
    child = EvaluationScopeTaxonomyNode(
        taxonomy_version_id=version.id,
        parent_node_id=None,
        gxp_type="GLP",
        source_name="PVCN_GLP",
        node_key="2",
        description="Child",
        hint=None,
        main_topic="MAIN",
        short_render="* Child $$",
        no_expand=None,
        source_order=2,
        source_excel_row=5,
    )
    session.add_all([root, child])
    session.flush()
    scope = CaseEvaluationScope(
        case_id=case.id,
        taxonomy_version_id=version.id,
        source_classification="STRUCTURED_VALID",
        raw_legacy_value="{1: legacy}*",
        rendered_prose="Historical prose must not be used",
        limitation_text="Phạm vi chứng nhận beta lactam",
    )
    session.add(scope)
    session.flush()
    block = CaseEvaluationScopeBlock(
        case_evaluation_scope_id=scope.id,
        ordinal=1,
        name=None,
        note=None,
        raw_block_value="{1: legacy}*",
    )
    session.add(block)
    session.flush()
    session.add(
        CaseEvaluationScopeSelection(
            block_id=block.id,
            taxonomy_node_id=root.id,
            source_order=1,
            custom_description="",
            node_key_snapshot="stale-key-must-not-own",
            taxonomy_description_snapshot="stale description",
        )
    )
    if unkeyed:
        session.add(CaseEvaluationScopeUnkeyedEntry(block_id=block.id, source_order=2, text="- legacy skipped"))
    session.commit()
    return case.id


def _registry_for(family_code: str, *field_names: str):
    return (
        PayloadBuilderRegistryEntry(
            family_code=family_code,
            source_procedures=("test-source",),
            fields=tuple(
                PayloadBuilderRegistryField(
                    field_name=field_name,
                    source_procedure="test-source",
                    sensitivity="business",
                )
                for field_name in field_names
            ),
            copy_forward_required=False,
        ),
    )


def _generic_result(family_code: str, values: dict[str, str], *registry_fields: str):
    return build_payload_envelope(
        _registry_for(family_code, *registry_fields),
        PayloadBuildInput(family_code=family_code, values=values, strict=True),
    )


def test_build_document_payload_result_appends_canonical_c5e_scope_fields(monkeypatch):
    engine = _engine()
    with Session(engine) as session:
        case_id = _seed_case(session, unkeyed=True)
        monkeypatch.setattr(
            "backend.app.document.service.load_default_payload_builder_registry",
            lambda: _registry_for("INSPECTION_BBTD_HOSO_DK", "Daychuyen", "Diachicoso"),
        )
        prepared = build_document_payload_result(
            session,
            DocumentPreparationInput(
                request=DocumentGenerationRequest(
                    family_code="INSPECTION_BBTD_HOSO_DK",
                    requested_by_user_id=None,
                    case_id=case_id,
                    storage_scope="inspection_folder",
                ),
                payload_values={"Diachicoso": "123 đường A"},
            ),
        )
        fields = {field.field_name: field for field in prepared.envelope.fields}
        assert fields["Daychuyen"].value == "* Root."
        assert fields["Daychuyen"].source.startswith(C5E_SCOPE_PROJECTION_SOURCE)
        assert "Historical prose must not be used" not in fields["Daychuyen"].value
        assert "legacy skipped" not in fields["Daychuyen"].value
        assert "Daychuyen" in prepared.used_fields
        assert "Daychuyen" not in prepared.missing_registry_fields


def test_c5e_scope_fields_cannot_be_overridden_by_caller_even_when_registry_knows_them():
    with pytest.raises(DocumentPayloadBuildError, match="cannot be supplied by the caller"):
        assert_no_c5e_scope_field_override(
            family_code="INSPECTION_BB_KT",
            values={"Daychuyen": "manual", "GhPviCN": "manual"},
        )


def test_branch_with_no_active_scope_write_requires_no_scope_and_suppresses_registry_false_positives(monkeypatch):
    engine = _engine()
    with Session(engine) as session:
        case_id = _seed_case(session, with_scope=False)
        monkeypatch.setattr(
            "backend.app.document.service.load_default_payload_builder_registry",
            lambda: _registry_for(
                "INSPECTION_QD_KT",
                "Daychuyen", "GhPviCN", "GhPviDG", "GioiHanPvi", "Diachicoso",
            ),
        )
        prepared = build_document_payload_result(
            session,
            DocumentPreparationInput(
                request=DocumentGenerationRequest(
                    family_code="INSPECTION_QD_KT",
                    requested_by_user_id=None,
                    case_id=case_id,
                    storage_scope="inspection_folder",
                ),
                payload_values={"Diachicoso": "123 đường A"},
            ),
        )
        names = {field.field_name for field in prepared.envelope.fields}
        assert names == {"Diachicoso"}
        assert not ({"Daychuyen", "GhPviCN", "GhPviDG", "GioiHanPvi"} & set(prepared.missing_registry_fields))


def test_family_that_actively_writes_scope_fails_closed_without_canonical_scope(monkeypatch):
    engine = _engine()
    with Session(engine) as session:
        case_id = _seed_case(session, with_scope=False)
        monkeypatch.setattr(
            "backend.app.document.service.load_default_payload_builder_registry",
            lambda: _registry_for("INSPECTION_BBTD_HOSO_DK", "Daychuyen", "Diachicoso"),
        )
        with pytest.raises(DocumentPayloadBuildError, match="requires canonical evaluation scope"):
            build_document_payload_result(
                session,
                DocumentPreparationInput(
                    request=DocumentGenerationRequest(
                        family_code="INSPECTION_BBTD_HOSO_DK",
                        requested_by_user_id=None,
                        case_id=case_id,
                        storage_scope="inspection_folder",
                    ),
                    payload_values={"Diachicoso": "123 đường A"},
                ),
            )


def test_pt_ct_copy_pt_true_emits_no_scope_fields_and_needs_no_scope_projection_input():
    engine = _engine()
    with Session(engine) as session:
        case_id = _seed_case(session, with_scope=False)
        generic = _generic_result("INSPECTION_PT_CT", {"Diachicoso": "123 đường A"}, "Daychuyen", "Daychuyen2", "GioihanPvi", "Diachicoso")
        enriched = enrich_payload_result_with_c5e_scope(
            session,
            family_code="INSPECTION_PT_CT",
            case_id=case_id,
            copy_pt=True,
            payload_result=generic,
        )
        assert {field.field_name for field in enriched.envelope.fields} == {"Diachicoso"}
        assert not ({"Daychuyen", "Daychuyen2", "GioihanPvi"} & set(enriched.missing_registry_fields))


def test_assessment_minutes_uses_exact_vba_bookmark_casing_outside_generic_registry():
    engine = _engine()
    with Session(engine) as session:
        case_id = _seed_case(session)
        generic = _generic_result("ASSESSMENT_MINUTES", {"Diachi": "123 đường A"}, "Daychuyen", "Diachi")
        enriched = enrich_payload_result_with_c5e_scope(
            session,
            family_code="ASSESSMENT_MINUTES",
            case_id=case_id,
            copy_pt=False,
            payload_result=generic,
        )
        fields = {field.field_name: field.value for field in enriched.envelope.fields}
        assert "DayChuyen" in fields
        assert "Daychuyen" not in fields
        assert fields["GioiHanPvi"] == "Phạm vi đánh giá β-Lactam"
        assert "Daychuyen" not in enriched.missing_registry_fields


def test_api_request_exposes_copy_pt_as_explicit_branch_condition():
    request = DocumentGenerationPrepareRequest(
        family_code="INSPECTION_PT_CT",
        case_id="case-1",
        payload={"Diachicoso": "123 đường A"},
        copy_pt=True,
    )
    assert request.copy_pt is True
