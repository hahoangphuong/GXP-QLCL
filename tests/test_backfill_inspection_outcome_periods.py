from __future__ import annotations

import inspect
from datetime import date

import pytest

from tools import backfill_inspection_outcome_periods as backfill


def _row(*, inspected_at: str = "20-21/10/2011", bbkt_reference: str = "") -> dict[str, object]:
    return {"__source_ktra": {"ID": "41", "Ngày K.tra": inspected_at, "B. bản": bbkt_reference}}


def _case(*, outcomes: list[dict[str, object]], legacy_id: int = 41) -> dict[str, object]:
    return {"id": "case-41", "legacy_inspection_id": legacy_id, "legacy_lineage": [], "outcomes": outcomes}


def _record(plan: dict[str, object]) -> dict[str, object]:
    return plan["records"][0]  # type: ignore[index]


def test_safe_insert_requires_existing_empty_outcome_and_fills_closed_interval():
    plan = backfill.build_backfill_plan([_row()], [_case(outcomes=[{"id": "outcome-41", "inspected_on": None, "inspected_to_on": None}])])
    record = _record(plan)
    assert record["status"] == "SAFE_INSERT"
    assert record["operation"] == "FILL_BOTH"
    assert record["candidate_start"] == "2011-10-20"
    assert record["candidate_end"] == "2011-10-21"
    assert plan["summary"]["writes_planned"] == 1  # type: ignore[index]


def test_single_day_safe_update_preserves_start_and_fills_equal_end():
    plan = backfill.build_backfill_plan(
        [_row(inspected_at="20/10/2011")],
        [_case(outcomes=[{"id": "outcome-41", "inspected_on": date(2011, 10, 20), "inspected_to_on": None}])],
    )
    record = _record(plan)
    assert record["status"] == "SAFE_UPDATE_IF_EMPTY"
    assert record["operation"] == "FILL_END"
    assert record["expected_post_start"] == "2011-10-20"
    assert record["expected_post_end"] == "2011-10-20"


def test_backfill_never_creates_missing_or_multiple_outcomes():
    missing = backfill.build_backfill_plan([_row()], [_case(outcomes=[])])
    assert _record(missing)["status"] == "NO_EXISTING_INSPECTION_OUTCOME"
    assert missing["summary"]["writes_planned"] == 0  # type: ignore[index]

    multiple = backfill.build_backfill_plan(
        [_row()],
        [_case(outcomes=[{"id": "one", "inspected_on": None, "inspected_to_on": None}, {"id": "two", "inspected_on": None, "inspected_to_on": None}])],
    )
    assert _record(multiple)["status"] == "MULTIPLE_INSPECTION_OUTCOME_ROWS"


def test_backfill_blocks_competing_provenance_and_canonical_drift():
    competing = backfill.build_backfill_plan(
        [_row(bbkt_reference="20/10/2011")],
        [_case(outcomes=[{"id": "outcome-41", "inspected_on": date(2011, 10, 20), "inspected_to_on": None}])],
    )
    assert _record(competing)["status"] == "BLOCKED_PROVENANCE"

    drift = backfill.build_backfill_plan(
        [_row()],
        [_case(outcomes=[{"id": "outcome-41", "inspected_on": date(2011, 10, 22), "inspected_to_on": None}])],
    )
    assert _record(drift)["status"] == "BLOCKED_CANONICAL_DRIFT"


def test_backfill_is_noop_after_exact_period_and_rejects_wrong_database():
    plan = backfill.build_backfill_plan(
        [_row()],
        [_case(outcomes=[{"id": "outcome-41", "inspected_on": date(2011, 10, 20), "inspected_to_on": date(2011, 10, 21)}])],
    )
    assert _record(plan)["status"] == "ALREADY_MATCHES"
    assert plan["summary"].get("writes_planned", 0) == 0  # type: ignore[index]
    with pytest.raises(RuntimeError, match="expected rehearsal database"):
        backfill.require_rehearsal_database("postgresql://user:password@host/production")
    source = inspect.getsource(backfill.main)
    assert "if args.apply" in source
    assert "session.commit()" in source


def test_apply_updates_only_the_existing_outcome_and_is_idempotent(monkeypatch: pytest.MonkeyPatch):
    class Outcome:
        id = "outcome-41"
        inspected_on: date | None = None
        inspected_to_on: date | None = None

    class ScalarResult:
        def __init__(self, outcome: Outcome):
            self.outcome = outcome

        def all(self) -> list[Outcome]:
            return [self.outcome]

    class Session:
        def __init__(self, outcome: Outcome):
            self.outcome = outcome
            self.flushes = 0

        def scalars(self, _statement: object) -> ScalarResult:
            return ScalarResult(self.outcome)

        def flush(self) -> None:
            self.flushes += 1

    outcome = Outcome()
    session = Session(outcome)

    def projection(_session: Session) -> list[dict[str, object]]:
        return [
            _case(
                outcomes=[
                    {
                        "id": outcome.id,
                        "inspected_on": outcome.inspected_on,
                        "inspected_to_on": outcome.inspected_to_on,
                    }
                ]
            )
        ]

    monkeypatch.setattr(backfill, "_case_projection", projection)

    first = backfill.apply_backfill_plan(session, [_row()])
    assert (outcome.inspected_on, outcome.inspected_to_on) == (date(2011, 10, 20), date(2011, 10, 21))
    assert first["summary"]["writes_performed"] == 1  # type: ignore[index]
    assert session.flushes == 1

    second = backfill.apply_backfill_plan(session, [_row()])
    assert second["summary"]["writes_performed"] == 0  # type: ignore[index]
    assert session.flushes == 1
