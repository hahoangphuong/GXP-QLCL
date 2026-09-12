from __future__ import annotations

from datetime import date, time
from typing import Iterable


TEAM_ROLE_CODES = frozenset({"LEADER", "SECRETARY", "MEMBER"})
APPROVAL_STAGES = frozenset({"PCT", "CT"})


class InspectionContractViolation(ValueError):
    """A typed inspection fact violates the canonical domain contract."""


def validate_time_requires_date(*, value_date: date | None, value_time: time | None, label: str) -> None:
    if value_time is not None and value_date is None:
        raise InspectionContractViolation(f"{label} time requires a date.")


def role_code_for_sort_order(sort_order: int) -> str:
    if sort_order < 1:
        raise InspectionContractViolation("Inspection team sort_order must start at 1.")
    if sort_order == 1:
        return "LEADER"
    if sort_order == 2:
        return "SECRETARY"
    return "MEMBER"


def validate_structured_team_member(
    *,
    inspector_profile_id: str | None,
    person_id: str | None,
    role_code: str | None,
    sort_order: int,
) -> None:
    has_profile = bool(inspector_profile_id and inspector_profile_id.strip())
    has_person = bool(person_id and person_id.strip())
    if has_profile == has_person:
        raise InspectionContractViolation("Inspection team member must set exactly one identity.")
    normalized_role = str(role_code or "")
    if normalized_role not in TEAM_ROLE_CODES:
        raise InspectionContractViolation("Inspection team member role_code must be LEADER, SECRETARY, or MEMBER.")
    expected_role = role_code_for_sort_order(sort_order)
    if normalized_role != expected_role:
        raise InspectionContractViolation(
            f"Inspection team role_code {normalized_role!r} does not match sort_order {sort_order}."
        )


def validate_unique_team_sort_orders(sort_orders: Iterable[int]) -> None:
    values = list(sort_orders)
    if len(set(values)) != len(values):
        raise InspectionContractViolation("Inspection team sort_order values must be unique.")


def validate_approval_stage(stage: str) -> str:
    normalized = str(stage or "").strip().upper()
    if normalized not in APPROVAL_STAGES:
        raise InspectionContractViolation("Approval submission stage must be PCT or CT.")
    return normalized


def validate_approval_completion(
    *,
    existing_completed_on: date | None,
    existing_completed_time: time | None,
    completed_on: date | None,
    completed_time: time | None,
) -> None:
    validate_time_requires_date(value_date=completed_on, value_time=completed_time, label="Approval completion")
    if existing_completed_on is not None or existing_completed_time is not None:
        raise InspectionContractViolation("Approval completion is immutable once set.")
    if completed_on is None:
        raise InspectionContractViolation("Approval completion requires completed_on.")


def validate_ct_parent(
    *,
    child_case_id: str,
    parent_case_id: str,
    parent_stage: str,
    parent_completed_on: date | None,
) -> None:
    if parent_case_id != child_case_id:
        raise InspectionContractViolation("CT parent must belong to the same case.")
    if parent_stage != "PCT":
        raise InspectionContractViolation("CT parent must be a PCT submission.")
    if parent_completed_on is None:
        raise InspectionContractViolation("CT parent PCT must be completed.")


def next_approval_round(existing_rounds: Iterable[int]) -> int:
    rounds = list(existing_rounds)
    if any(round_no < 1 for round_no in rounds) or len(set(rounds)) != len(rounds):
        raise InspectionContractViolation("Approval rounds must be unique positive integers before allocation.")
    return 1 if not rounds else max(rounds) + 1
