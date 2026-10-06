from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

import backend.app.document.service as service_module
from backend.app.document.payload_builders import DocumentPayloadBuildError
from backend.app.document.service import (
    DocumentPreparationInput,
    build_document_payload_result,
)
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


def _preparation(*, payload_values=None, generated_at=None) -> DocumentPreparationInput:
    return DocumentPreparationInput(
        request=DocumentGenerationRequest(
            family_code="INSPECTION_KE_HOACH_KT",
            requested_by_user_id="user-1",
            case_id="case-1",
            gxp_type="GMP",
            storage_scope="inspection_folder",
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
