from __future__ import annotations

import inspect
from datetime import date
from hashlib import sha256

import pytest

from tools import backfill_inspection_outcome_periods as backfill


def _row(*, inspected_at: str = "20-21/10/2011", bbkt_reference: str = "") -> dict[str, object]:
    return {"__source_ktra": {"ID": "41", "Ngày K.tra": inspected_at, "B. bản": bbkt_reference}}


def _case(*, outcomes: list[dict[str, object]], legacy_id: int = 41) -> dict[str, object]:
    return {
        "id": "case-41",
        "legacy_inspection_id": legacy_id,
        "legacy_lineage": [],
        "outcome": outcomes[0] if len(outcomes) == 1 else {},
        "outcomes": outcomes,
    }


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
    assert _record(missing)["status"] == "BLOCKED_OUTCOME_CARDINALITY"
    assert missing["summary"]["writes_planned"] == 0  # type: ignore[index]

    multiple = backfill.build_backfill_plan(
        [_row()],
        [_case(outcomes=[{"id": "one", "inspected_on": None, "inspected_to_on": None}, {"id": "two", "inspected_on": None, "inspected_to_on": None}])],
    )
    assert _record(multiple)["status"] == "BLOCKED_OUTCOME_CARDINALITY"


def test_backfill_ignores_b_ban_and_blocks_canonical_drift():
    competing = backfill.build_backfill_plan(
        [_row(bbkt_reference="20/10/2011")],
        [_case(outcomes=[{"id": "outcome-41", "inspected_on": date(2011, 10, 20), "inspected_to_on": None}])],
    )
    assert _record(competing)["status"] == "SAFE_UPDATE_IF_EMPTY"

    drift = backfill.build_backfill_plan(
        [_row()],
        [_case(outcomes=[{"id": "outcome-41", "inspected_on": date(2011, 10, 22), "inspected_to_on": None}])],
    )
    assert _record(drift)["status"] == "CONFLICT_EXISTING_CANONICAL"


def test_backfill_is_noop_after_exact_period_and_rejects_wrong_database():
    plan = backfill.build_backfill_plan(
        [_row()],
        [_case(outcomes=[{"id": "outcome-41", "inspected_on": date(2011, 10, 20), "inspected_to_on": date(2011, 10, 21)}])],
    )
    assert _record(plan)["status"] == "ALREADY_MATCHES"
    assert plan["summary"].get("writes_planned", 0) == 0  # type: ignore[index]
    with pytest.raises(RuntimeError, match="expected rehearsal database"):
        backfill.require_rehearsal_database("postgresql://user:password@host/production")
    source = inspect.getsource(backfill.run_backfill_from_snapshot)
    assert "apply_backfill_plan" in source
    assert "transaction.commit()" in source


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

        def get(self, _model: object, _identifier: object, **_kwargs: object) -> Outcome:
            return self.outcome

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
    monkeypatch.setattr(backfill, "_locked_case_projection", lambda _session, _legacy_id: projection(session))

    first = backfill.apply_backfill_plan(session, [_row()])
    assert (outcome.inspected_on, outcome.inspected_to_on) == (date(2011, 10, 20), date(2011, 10, 21))
    assert first["summary"]["writes_performed"] == 1  # type: ignore[index]
    assert session.flushes == 1

    second = backfill.apply_backfill_plan(session, [_row()])
    assert second["summary"]["writes_performed"] == 0  # type: ignore[index]
    assert session.flushes == 1


def test_only_planner_safe_single_segment_facts_can_become_migration_writes():
    safe = backfill.build_backfill_plan(
        [_row(bbkt_reference="20/10/2011")],
        [_case(outcomes=[{"id": "outcome-41", "inspected_on": date(2011, 10, 20), "inspected_to_on": None}])],
    )
    conflict = backfill.build_backfill_plan(
        [_row(bbkt_reference="20/10/2011")],
        [_case(outcomes=[{"id": "outcome-41", "inspected_on": date(2011, 10, 20), "inspected_to_on": date(2011, 10, 22)}])],
    )
    assert _record(safe)["planner_status"] == "SAFE_UPDATE_IF_EMPTY"
    assert _record(conflict)["planner_status"] == "CONFLICT_EXISTING_CANONICAL"
    assert safe["summary"]["writes_planned"] == 1  # type: ignore[index]
    assert conflict["summary"]["writes_planned"] == 0  # type: ignore[index]
    source = inspect.getsource(backfill.build_backfill_plan)
    assert "build_reconciliation_plan" in source
    assert "_date_reconciliation" not in source


def test_snapshot_provenance_and_file_integrity_fail_closed(tmp_path, monkeypatch: pytest.MonkeyPatch):
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text("{}", encoding="utf-8")
    actual_sha = sha256(snapshot_path.read_bytes()).hexdigest()
    with pytest.raises(backfill.BackfillInvariantError, match="workbook provenance"):
        backfill.load_audited_snapshot_json(
            snapshot_path,
            expected_workbook_sha256="0" * 64,
            expected_snapshot_sha256=backfill.CANONICAL_SNAPSHOT_SHA256,
        )
    with pytest.raises(backfill.BackfillInvariantError, match="snapshot integrity"):
        backfill.load_audited_snapshot_json(
            snapshot_path,
            expected_workbook_sha256=backfill.CANONICAL_WORKBOOK_SHA256,
            expected_snapshot_sha256="0" * 64,
        )
    monkeypatch.setattr(backfill, "CANONICAL_SNAPSHOT_SHA256", actual_sha)
    monkeypatch.setattr(
        backfill,
        "load_legacy_snapshot_json",
        lambda _path, *, expected_workbook_sha256: {
            "legacy_rows": [],
            "provenance": {"source_workbook_sha256": expected_workbook_sha256},
        },
    )
    loaded = backfill.load_audited_snapshot_json(
        snapshot_path,
        expected_workbook_sha256=backfill.CANONICAL_WORKBOOK_SHA256,
        expected_snapshot_sha256=actual_sha,
    )
    assert loaded["file_integrity_sha256"] == actual_sha
    monkeypatch.setattr(
        backfill,
        "load_legacy_snapshot_json",
        lambda _path, *, expected_workbook_sha256: {
            "legacy_rows": [],
            "provenance": {"source_workbook_sha256": "f" * 64},
        },
    )
    with pytest.raises(backfill.BackfillInvariantError, match="workbook provenance changed"):
        backfill.load_audited_snapshot_json(
            snapshot_path,
            expected_workbook_sha256=backfill.CANONICAL_WORKBOOK_SHA256,
            expected_snapshot_sha256=actual_sha,
        )


def test_connection_guard_requires_actual_rehearsal_database_and_read_only_transaction():
    class ScalarResult:
        def __init__(self, value: str):
            self.value = value

        def scalar_one(self) -> str:
            return self.value

    class Connection:
        def __init__(self, database_name: str = "gxp_legacy_rehearsal", read_only: str = "on"):
            self.database_name = database_name
            self.read_only = read_only
            self.statements: list[str] = []

        def execute(self, statement: object) -> ScalarResult:
            sql = str(statement)
            self.statements.append(sql)
            if sql.startswith("SELECT current_database"):
                return ScalarResult(self.database_name)
            if sql.startswith("SHOW transaction_read_only"):
                return ScalarResult(self.read_only)
            raise AssertionError(f"unexpected SQL: {sql}")

    connection = Connection()
    assert backfill._verify_rehearsal_connection(connection, require_read_only=True) == {
        "actual_database_name": "gxp_legacy_rehearsal",
        "transaction_read_only": True,
    }
    with pytest.raises(backfill.BackfillInvariantError, match="other than gxp_legacy_rehearsal"):
        backfill._verify_rehearsal_connection(Connection(database_name="other"), require_read_only=False)
    with pytest.raises(backfill.BackfillInvariantError, match="read-only"):
        backfill._verify_rehearsal_connection(Connection(read_only="off"), require_read_only=True)
    assert "SET TRANSACTION READ ONLY" in inspect.getsource(backfill.run_backfill_from_snapshot)


@pytest.mark.parametrize(
    ("locked_case", "message"),
    [
        (
            {"id": "other-case", "legacy_inspection_id": 41, "legacy_lineage": [], "outcome": {}, "outcomes": []},
            "case identity changed",
        ),
        (
            {"id": "case-41", "legacy_inspection_id": 41, "legacy_lineage": [], "outcome": {"id": "other-outcome", "inspected_on": None, "inspected_to_on": None}, "outcomes": [{"id": "other-outcome", "inspected_on": None, "inspected_to_on": None}]},
            "inspection outcome identity changed",
        ),
        (
            {"id": "case-41", "legacy_inspection_id": 41, "legacy_lineage": [], "outcome": {"id": "outcome-41", "inspected_on": date(2011, 10, 22), "inspected_to_on": None}, "outcomes": [{"id": "outcome-41", "inspected_on": date(2011, 10, 22), "inspected_to_on": None}]},
            "canonical inspection period drifted",
        ),
    ],
)
def test_write_time_identity_and_period_drift_fail_closed(monkeypatch: pytest.MonkeyPatch, locked_case: dict[str, object], message: str):
    record = _record(backfill.build_backfill_plan([_row()], [_case(outcomes=[{"id": "outcome-41", "inspected_on": None, "inspected_to_on": None}])]))
    monkeypatch.setattr(backfill, "_locked_case_projection", lambda _session, _legacy_id: [locked_case])
    with pytest.raises(backfill.BackfillInvariantError, match=message):
        backfill._revalidate_locked_write(object(), record, _row())


def test_backfill_has_no_outcome_constructor_or_bbkt_date_fallback():
    source = inspect.getsource(backfill)
    assert "InspectionOutcome(" not in source
    assert "parse_legacy_inspection_periods(source_value)" in source
    assert "bbkt_reference" not in source
