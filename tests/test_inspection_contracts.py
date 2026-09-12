from datetime import date, time
from pathlib import Path

import pytest

from backend.app.domain.inspection_contracts import (
    InspectionContractViolation,
    next_approval_round,
    role_code_for_sort_order,
    validate_approval_completion,
    validate_ct_parent,
    validate_structured_team_member,
    validate_time_requires_date,
    validate_unique_team_sort_orders,
)


@pytest.mark.parametrize(
    ("sort_order", "role_code"),
    [(1, "LEADER"), (2, "SECRETARY"), (3, "MEMBER"), (9, "MEMBER")],
)
def test_structured_team_role_mapping_is_explicit(sort_order: int, role_code: str):
    assert role_code_for_sort_order(sort_order) == role_code
    validate_structured_team_member(
        inspector_profile_id="profile-id",
        person_id=None,
        role_code=role_code,
        sort_order=sort_order,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"inspector_profile_id": "profile", "person_id": None, "role_code": "MEMBER", "sort_order": 1},
        {"inspector_profile_id": "profile", "person_id": "person", "role_code": "LEADER", "sort_order": 1},
        {"inspector_profile_id": None, "person_id": None, "role_code": "LEADER", "sort_order": 1},
        {"inspector_profile_id": "", "person_id": None, "role_code": "LEADER", "sort_order": 1},
        {"inspector_profile_id": "profile", "person_id": None, "role_code": "LEADER", "sort_order": 0},
    ],
)
def test_structured_team_rejects_invalid_role_order_or_identity(kwargs):
    with pytest.raises(InspectionContractViolation):
        validate_structured_team_member(**kwargs)


def test_team_sort_order_must_be_unique():
    with pytest.raises(InspectionContractViolation, match="unique"):
        validate_unique_team_sort_orders([1, 1])


def test_minutes_and_completion_time_require_dates():
    with pytest.raises(InspectionContractViolation, match="requires a date"):
        validate_time_requires_date(value_date=None, value_time=time(9, 30), label="Minutes")
    validate_time_requires_date(value_date=date(2026, 9, 12), value_time=time(9, 30), label="Minutes")


def test_ct_requires_completed_same_case_pct_parent():
    validate_ct_parent(child_case_id="case", parent_case_id="case", parent_stage="PCT", parent_completed_on=date(2026, 9, 12))
    for parent_case_id, parent_stage, completed_on in [
        ("other", "PCT", date(2026, 9, 12)),
        ("case", "CT", date(2026, 9, 12)),
        ("case", "PCT", None),
    ]:
        with pytest.raises(InspectionContractViolation):
            validate_ct_parent(
                child_case_id="case",
                parent_case_id=parent_case_id,
                parent_stage=parent_stage,
                parent_completed_on=completed_on,
            )


def test_pct_completion_is_explicit_and_immutable_without_ct_requirement():
    validate_approval_completion(
        existing_completed_on=None,
        existing_completed_time=None,
        completed_on=date(2026, 9, 12),
        completed_time=None,
    )
    with pytest.raises(InspectionContractViolation, match="immutable"):
        validate_approval_completion(
            existing_completed_on=date(2026, 9, 12),
            existing_completed_time=None,
            completed_on=date(2026, 9, 13),
            completed_time=None,
        )


def test_approval_round_allocation_rejects_existing_collisions():
    assert next_approval_round([1, 3]) == 4
    with pytest.raises(InspectionContractViolation):
        next_approval_round([1, 1])


def test_batch_one_leaves_legacy_importer_routing_unchanged_and_new_fields_unpopulated():
    importer = Path("backend/app/domain/phase2_import.py").read_text(encoding="utf-8")

    assert "final_evaluation=" not in importer
    assert "minutes_recorded_on=" not in importer
    assert "minutes_recorded_time=" not in importer
    assert "decision_date=" not in importer
    assert "InspectionApprovalSubmission" not in importer
