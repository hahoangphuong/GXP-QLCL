from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

import backend.app.document.inspection_ke_hoach_kt_payload_input as module
from backend.app.db.models.phase1 import Case, CaseApplication, InspectionPlan, Site
from backend.app.document.inspection_ke_hoach_kt_payload_input import (
    InspectionKeHoachKtPayloadInputError,
    load_inspection_ke_hoach_kt_payload_input,
)
from backend.app.document.inspection_ke_hoach_kt_team_projection import (
    InspectionKeHoachKtTeamMemberInput,
)


class FakeSession:
    def __init__(self, *, case, site, application, plan):
        self.case = case
        self.site = site
        self.application = application
        self.plan = plan

    def get(self, entity, identity):
        if entity is Case:
            return self.case if identity == self.case.id else None
        if entity is Site:
            return self.site if identity == self.site.id else None
        raise AssertionError(f"unexpected get entity: {entity}")

    def scalar(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is CaseApplication:
            return self.application
        if entity is InspectionPlan:
            return self.plan
        raise AssertionError(f"unexpected scalar entity: {entity}")


def _session(**overrides):
    case = SimpleNamespace(
        id="case-1",
        site_id="site-1",
        gxp_type="GMP",
        applicable_standard="WHO-GMP",
    )
    site = SimpleNamespace(
        id="site-1",
        site_name="Cơ sở A",
        site_address="Số 1 Đường A",
        province_name="Hà Nội",
    )
    application = SimpleNamespace(
        dossier_code="HS-001",
        submitted_on=datetime(2026, 9, 1, 2, 0, tzinfo=timezone.utc),
    )
    plan = SimpleNamespace(
        decision_reference="123/QĐ-QLD",
        decision_date=date(2026, 9, 20),
    )
    values = {
        "case": case,
        "site": site,
        "application": application,
        "plan": plan,
    }
    values.update(overrides)
    return FakeSession(**values)


def _patch_projections(monkeypatch):
    monkeypatch.setattr(
        module,
        "load_c5e_evaluation_scope_projection_input",
        lambda session, case_id: SimpleNamespace(
            blocks=(),
            taxonomy_nodes=(),
            limitation_text=None,
            gxp_type="GMP",
        ),
    )
    monkeypatch.setattr(
        module,
        "project_vba_document_scope_fields",
        lambda **kwargs: SimpleNamespace(
            fields={"Daychuyen": "Sản xuất thuốc", "GioiHanPvi": "Không"}
        ),
    )
    monkeypatch.setattr(
        module,
        "project_inspection_ke_hoach_kt_province",
        lambda **kwargs: SimpleNamespace(
            diadiemx="thành phố Hà Nội",
            vknx="Viện Kiểm nghiệm thuốc Trung ương",
        ),
    )
    monkeypatch.setattr(
        module,
        "load_inspection_ke_hoach_kt_team_members",
        lambda session, case_id: (
            InspectionKeHoachKtTeamMemberInput(
                display_name="Trưởng đoàn",
                sort_order=1,
                role_code="TRUONG_DOAN",
                identity_kind="INSPECTOR_PROFILE",
                roster_group="DRUG_ADMINISTRATION_AND_TRADITIONAL_MEDICINE",
            ),
        ),
    )


def test_khkt_payload_input_loads_only_canonical_and_proven_projection_values(monkeypatch):
    _patch_projections(monkeypatch)

    payload = load_inspection_ke_hoach_kt_payload_input(
        _session(),
        case_id="case-1",
        generated_at=datetime(2026, 10, 5, 17, 0, tzinfo=timezone.utc),
    )

    assert payload.case_id == "case-1"
    assert payload.gxp_type == "GMP"
    assert payload.site_name == "Cơ sở A"
    assert payload.site_address == "Số 1 Đường A"
    assert payload.province_name == "Hà Nội"
    assert payload.dossier_code == "HS-001"
    assert payload.decision_reference == "123/QĐ-QLD"
    assert payload.decision_date == date(2026, 9, 20)
    assert payload.applicable_standard == "WHO-GMP"
    assert payload.daychuyen == "Sản xuất thuốc"
    assert payload.gioi_han_pvi == "Không"
    assert payload.diadiemx == "thành phố Hà Nội"
    assert payload.generated_on == date(2026, 10, 6)
    assert payload.fulldate == "ngày 06 tháng 10 năm 2026"
    assert len(payload.team_members) == 1


def test_khkt_payload_input_allows_absent_optional_application(monkeypatch):
    _patch_projections(monkeypatch)

    payload = load_inspection_ke_hoach_kt_payload_input(
        _session(application=None),
        case_id="case-1",
        generated_at=datetime(2026, 10, 6, 5, 0, tzinfo=timezone.utc),
    )

    assert payload.dossier_code is None
    assert payload.submitted_on is None


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    [
        ("site_name", "", "site_name"),
        ("site_address", None, "site_address"),
        ("province_name", "", "province_name"),
    ],
)
def test_khkt_payload_input_fails_closed_on_missing_required_site_owner(
    monkeypatch,
    attribute,
    value,
    message,
):
    _patch_projections(monkeypatch)
    site = SimpleNamespace(
        id="site-1",
        site_name="Cơ sở A",
        site_address="Số 1 Đường A",
        province_name="Hà Nội",
    )
    setattr(site, attribute, value)

    with pytest.raises(InspectionKeHoachKtPayloadInputError, match=message):
        load_inspection_ke_hoach_kt_payload_input(
            _session(site=site),
            case_id="case-1",
            generated_at=datetime(2026, 10, 6, 5, 0, tzinfo=timezone.utc),
        )


def test_khkt_payload_input_fails_closed_without_inspection_plan(monkeypatch):
    _patch_projections(monkeypatch)

    with pytest.raises(
        InspectionKeHoachKtPayloadInputError,
        match="inspection plan is missing",
    ):
        load_inspection_ke_hoach_kt_payload_input(
            _session(plan=None),
            case_id="case-1",
            generated_at=datetime(2026, 10, 6, 5, 0, tzinfo=timezone.utc),
        )


def test_khkt_payload_input_rejects_naive_generation_time(monkeypatch):
    _patch_projections(monkeypatch)

    with pytest.raises(
        InspectionKeHoachKtPayloadInputError,
        match="timezone-aware",
    ):
        load_inspection_ke_hoach_kt_payload_input(
            _session(),
            case_id="case-1",
            generated_at=datetime(2026, 10, 6, 12, 0),
        )
