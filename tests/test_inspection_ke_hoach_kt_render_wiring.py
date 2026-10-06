from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import backend.app.document.service as service_module
import backend.app.services.document_api as document_api_module
from backend.app.document.payload_builders import DocumentPayloadBuildError
from backend.app.document.service import (
    DocumentPreparationInput,
    build_document_payload_result,
)
from backend.app.services.document_api import DocumentWorkflowService
from backend.app.document.service_contract import DocumentGenerationRequest
from backend.app.document.inspection_ke_hoach_kt_payload_input import (
    InspectionKeHoachKtPayloadInput,
)
from backend.app.document.inspection_ke_hoach_kt_team_projection import (
    InspectionKeHoachKtTeamMemberInput,
)


def _payload_input() -> InspectionKeHoachKtPayloadInput:
    return InspectionKeHoachKtPayloadInput(
        case_id="case-1",
        gxp_type="GMP",
        site_name="Cơ sở A",
        site_address="Địa chỉ A",
        province_name="Hà Nội",
        dossier_code=None,
        submitted_on=None,
        decision_reference="123/QĐ-QLD",
        decision_date=date(2026, 9, 20),
        applicable_standard="WHO-GMP",
        daychuyen="Sản xuất thuốc",
        gioi_han_pvi="Không",
        diadiemx="thành phố Hà Nội",
        vknx="Viện Kiểm nghiệm thuốc Trung ương",
        team_members=(
            InspectionKeHoachKtTeamMemberInput(
                display_name="A",
                sort_order=1,
                role_code="LEADER",
                identity_kind="INSPECTOR_PROFILE",
                roster_group="DRUG_ADMINISTRATION_AND_TRADITIONAL_MEDICINE",
            ),
        ),
        generated_on=date(2026, 10, 6),
        fulldate="ngày 06 tháng 10 năm 2026",
    )


def _preparation(
    *,
    payload_values=None,
    generated_at=None,
    gxp_type="GMP",
    language_code="vi",
    **request_overrides,
) -> DocumentPreparationInput:
    return DocumentPreparationInput(
        request=DocumentGenerationRequest(
            family_code="INSPECTION_KE_HOACH_KT",
            requested_by_user_id="user-1",
            case_id="case-1",
            gxp_type=gxp_type,
            storage_scope="inspection_folder",
            language_code=language_code,
            **request_overrides,
        ),
        payload_values={} if payload_values is None else payload_values,
        generated_at=generated_at or datetime(2026, 10, 5, 17, 0, tzinfo=timezone.utc),
    )


def test_khkt_document_payload_result_is_canonical_and_rejects_caller_business_payload():
    result = build_document_payload_result(
        SimpleNamespace(),
        _preparation(),
        khkt_payload_input=_payload_input(),
    )
    values = {field.field_name: field.value for field in result.envelope.fields}
    assert values["Fulldate"] == "ngày 06 tháng 10 năm 2026"
    assert values["Tencoso"] == "Cơ sở A"
    assert values["QDKT"] == "123/QĐ-QLD"
    assert result.missing_registry_fields == ()

    with pytest.raises(DocumentPayloadBuildError, match="DB-owned"):
        build_document_payload_result(
            SimpleNamespace(),
            _preparation(payload_values={"Tencoso": "caller override"}),
            khkt_payload_input=_payload_input(),
        )


@pytest.mark.parametrize("case_id", (None, "", "   "))
def test_khkt_payload_loader_requires_nonblank_case_parent_before_db_load(
    monkeypatch,
    case_id,
):
    load_calls: list[object] = []
    monkeypatch.setattr(
        service_module,
        "load_inspection_ke_hoach_kt_payload_input",
        lambda *args, **kwargs: load_calls.append(object()),
    )
    preparation = _preparation()
    request = DocumentGenerationRequest(
        family_code=preparation.request.family_code,
        requested_by_user_id=preparation.request.requested_by_user_id,
        case_id=case_id,
        gxp_type=preparation.request.gxp_type,
        storage_scope=preparation.request.storage_scope,
        language_code=preparation.request.language_code,
    )

    with pytest.raises(
        DocumentPayloadBuildError,
        match="requires a nonblank case_id",
    ):
        service_module._build_khkt_payload_input(
            SimpleNamespace(),
            DocumentPreparationInput(
                request=request,
                payload_values={},
                generated_at=preparation.generated_at,
            ),
        )

    assert load_calls == []


@pytest.mark.parametrize(
    "parent_field",
    (
        "capa_cycle_id",
        "certificate_id",
        "business_eligibility_certificate_id",
        "change_request_id",
    ),
)
def test_khkt_payload_loader_rejects_non_case_parent_links_before_db_load(
    monkeypatch,
    parent_field,
):
    load_calls: list[object] = []
    monkeypatch.setattr(
        service_module,
        "load_inspection_ke_hoach_kt_payload_input",
        lambda *args, **kwargs: load_calls.append(object()),
    )

    with pytest.raises(
        DocumentPayloadBuildError,
        match=rf"case-owned and rejects additional parent links: {parent_field}",
    ):
        service_module._build_khkt_payload_input(
            SimpleNamespace(),
            _preparation(**{parent_field: f"{parent_field}-1"}),
        )

    assert load_calls == []


def test_khkt_payload_loader_requires_request_gxp_type_matching_canonical_case(
    monkeypatch,
):
    monkeypatch.setattr(
        service_module,
        "load_inspection_ke_hoach_kt_payload_input",
        lambda *args, **kwargs: _payload_input(),
    )

    with pytest.raises(
        DocumentPayloadBuildError,
        match="requires request gxp_type to match the canonical case GxP",
    ):
        service_module._build_khkt_payload_input(
            SimpleNamespace(),
            _preparation(gxp_type=None),
        )

    with pytest.raises(
        DocumentPayloadBuildError,
        match="request/case GxP mismatch",
    ):
        service_module._build_khkt_payload_input(
            SimpleNamespace(),
            _preparation(gxp_type="GLP"),
        )


def test_khkt_payload_loader_requires_vietnamese_language_variant(monkeypatch):
    monkeypatch.setattr(
        service_module,
        "load_inspection_ke_hoach_kt_payload_input",
        lambda *args, **kwargs: _payload_input(),
    )

    assert service_module._build_khkt_payload_input(
        SimpleNamespace(),
        _preparation(language_code="vi"),
    ) == _payload_input()

    for language_code in ("en", "", "VI"):
        with pytest.raises(
            DocumentPayloadBuildError,
            match="language_code is backend-owned and must be 'vi'",
        ):
            service_module._build_khkt_payload_input(
                SimpleNamespace(),
                _preparation(language_code=language_code),
            )


def test_khkt_payload_loader_requires_frozen_generation_timestamp(monkeypatch):
    monkeypatch.setattr(
        service_module,
        "load_inspection_ke_hoach_kt_payload_input",
        lambda *args, **kwargs: _payload_input(),
    )
    preparation = _preparation()
    frozen = service_module._build_khkt_payload_input(SimpleNamespace(), preparation)
    assert frozen is not None

    with pytest.raises(DocumentPayloadBuildError, match="frozen generated_at"):
        service_module._build_khkt_payload_input(
            SimpleNamespace(),
            DocumentPreparationInput(
                request=preparation.request,
                payload_values={},
                generated_at=None,
            ),
        )


def test_khkt_render_output_filename_is_backend_owned_by_exact_variant():
    service = DocumentWorkflowService()
    prepared = SimpleNamespace(
        generation_plan=SimpleNamespace(
            template=SimpleNamespace(family_code="INSPECTION_KE_HOACH_KT")
        ),
        khkt_payload_input=_payload_input(),
    )

    assert service._resolve_render_output_filename(
        prepared,
        "3. Kế hoạch kiểm tra GMP.docx",
    ) == "3. Kế hoạch kiểm tra GMP.docx"

    with pytest.raises(DocumentPayloadBuildError, match="backend-owned"):
        service._resolve_render_output_filename(
            prepared,
            "caller-controlled-name.docx",
        )


def test_non_khkt_render_output_filename_remains_caller_owned():
    service = DocumentWorkflowService()
    prepared = SimpleNamespace(
        generation_plan=SimpleNamespace(
            template=SimpleNamespace(family_code="DDKD_CERTIFICATE")
        ),
        khkt_payload_input=None,
    )

    assert service._resolve_render_output_filename(
        prepared,
        "caller-selected.docx",
    ) == "caller-selected.docx"


def test_khkt_render_rejects_output_filename_drift_before_readiness_and_allocation(
    monkeypatch,
):
    service = DocumentWorkflowService()
    prepared = SimpleNamespace(
        generation_plan=SimpleNamespace(
            template=SimpleNamespace(family_code="INSPECTION_KE_HOACH_KT")
        ),
        khkt_payload_input=_payload_input(),
        persisted_state=SimpleNamespace(
            generation_run_id="run-khkt-filename",
            reused_generation_run=False,
        ),
    )
    failures: list[tuple[str, str]] = []
    allocation_calls: list[object] = []

    monkeypatch.setattr(
        service,
        "_get_or_create_app_user",
        lambda _session, _user: SimpleNamespace(id="user-1"),
    )
    monkeypatch.setattr(
        service,
        "_build_preparation_input",
        lambda _payload, _user_id: SimpleNamespace(),
    )
    monkeypatch.setattr(
        document_api_module,
        "prepare_document_generation_job",
        lambda _session, _preparation_input: prepared,
    )
    monkeypatch.setattr(
        service,
        "_inspect_template_readiness",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("filename drift must fail before template readiness")
        ),
    )
    monkeypatch.setattr(
        service,
        "_mark_generation_run_failed",
        lambda _session, generation_run_id, detail: failures.append(
            (generation_run_id, detail)
        ),
    )
    monkeypatch.setattr(
        document_api_module,
        "prepare_template_aware_docx_generation",
        lambda *_args, **_kwargs: allocation_calls.append(object()),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.render_template_docx(
            SimpleNamespace(),
            storage=object(),
            payload={
                "family_code": "INSPECTION_KE_HOACH_KT",
                "case_id": "case-1",
                "gxp_type": "GMP",
                "storage_scope": "inspection_folder",
                "output_filename": "caller-controlled-name.docx",
                "payload": {},
            },
            user=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 409
    assert "backend-owned" in exc_info.value.detail
    assert allocation_calls == []
    assert failures == [
        (
            "run-khkt-filename",
            "INSPECTION_KE_HOACH_KT output filename is backend-owned by the exact "
            "template variant; expected '3. Kế hoạch kiểm tra GMP.docx'.",
        )
    ]
