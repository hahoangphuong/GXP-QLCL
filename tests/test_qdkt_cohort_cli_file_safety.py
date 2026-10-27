"""Confidential offline report must never clobber input or follow symlinks."""
import json
from hashlib import sha256
import os
import stat

import pytest

from tools.audit_qdkt_snapshot_cohort import (
    QdKtCohortAuditBlocked, main, write_private_report,
)
from backend.app.domain.legacy_snapshot_v2 import (
    AUTHORITATIVE_WORKBOOK_SHA256, SCHEMA_VERSION,
)


def _fixtures(tmp_path):
    snap = tmp_path / "source.json"
    cohort = tmp_path / "cohort.json"
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "workbook": {"sha256": AUTHORITATIVE_WORKBOOK_SHA256},
        "sheets": [{"sheet_name": "db.ktra", "raw_rows": [
            {"source_row_number": 1, "cells": [{"column_ordinal": 1, "raw_value": "ID"}]},
            {"source_row_number": 2, "cells": [{"column_ordinal": 1, "raw_value": 77}]},
            {"source_row_number": 3, "cells": [{"column_ordinal": 3, "raw_value": "private"}]},
        ]}],
    }
    sheet = snapshot["sheets"][0]
    rows = sheet["raw_rows"]
    sheet["content_sha256"] = sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    sheet["raw_row_count"] = sheet["used_row_count"] = len(rows)
    sheet["used_column_count"] = 3
    sheet["raw_coordinate_inventory"] = {"row_count": len(rows), "column_count": 3, "cell_coordinate_count": 3}
    snap.write_text(json.dumps(snapshot), encoding="utf-8")
    cohort.write_text(json.dumps([{"case_id": "secret-case-id", "legacy_inspection_id": 77}]))
    return snap, cohort


def _argv(source, cases, output):
    return ["--snapshot", str(source), "--cases-json", str(cases),
            "--attested-header-row", "1", "--confirm-header-provenance",
            "--output", str(output)]


def test_real_cli_writes_private_aggregate_and_refuses_overwrite(tmp_path):
    snap, cohort = _fixtures(tmp_path)
    output = tmp_path / "report.json"
    assert main(_argv(snap, cohort, output)) == 0
    data = output.read_text()
    assert json.loads(data)["status_counts"] == {"SOURCE_ROW_UNIQUE": 1}
    assert "secret-case-id" not in data and "private" not in data
    if os.name == "posix":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(SystemExit):
        main(_argv(snap, cohort, output))
    assert output.read_text() == data


def test_report_cannot_overwrite_input_even_after_all_guards_pass(tmp_path):
    snap, cohort = _fixtures(tmp_path)
    original = snap.read_bytes()
    with pytest.raises(SystemExit):
        main(_argv(snap, cohort, snap))
    assert snap.read_bytes() == original


def test_existing_symlink_never_followed(tmp_path):
    snap, cohort = _fixtures(tmp_path)
    output = tmp_path / "link.json"
    output.symlink_to(cohort)
    original = cohort.read_bytes()
    with pytest.raises(QdKtCohortAuditBlocked, match="OUTPUT_COLLIDES_WITH_SOURCE_INPUT"):
        write_private_report(output=output, report={"safe": True}, inputs=(snap, cohort))
    assert cohort.read_bytes() == original


def test_bad_source_fails_without_publishing_output(tmp_path):
    snap, cohort = _fixtures(tmp_path)
    output = tmp_path / "report.json"
    snap.write_text("{ invalid")
    with pytest.raises(SystemExit):
        main(_argv(snap, cohort, output))
    assert not output.exists()


def test_opt_in_exception_file_private_and_aggregate_kept_identifer_free(tmp_path):
    snap, cohort = _fixtures(tmp_path)
    # Existing fixture has one unique source ID and a sparse empty ID row.
    report = tmp_path / "aggregate.json"
    private = tmp_path / "exceptions.json"
    assert main(_argv(snap, cohort, report) + ["--exceptions-output", str(private)]) == 0
    assert json.loads(report.read_text())["status_counts"] == {"SOURCE_ROW_UNIQUE": 1}
    result = json.loads(private.read_text())
    assert result["exception_count"] == 0
    assert "secret-case-id" not in report.read_text()
    if os.name == "posix":
        assert stat.S_IMODE(private.stat().st_mode) == 0o600


def test_exception_output_cannot_alias_aggregate_or_input(tmp_path):
    snap, cohort = _fixtures(tmp_path)
    report = tmp_path / "aggregate.json"
    with pytest.raises(SystemExit):
        main(_argv(snap, cohort, report) + ["--exceptions-output", str(report)])
    assert not report.exists()
    with pytest.raises(SystemExit):
        main(_argv(snap, cohort, report) + ["--exceptions-output", str(cohort)])
    assert not report.exists()


def test_pair_rolls_back_aggregate_when_second_file_creation_fails(tmp_path, monkeypatch):
    import tools.audit_qdkt_snapshot_cohort as audit

    output = tmp_path / "aggregate.json"
    exceptions = tmp_path / "exceptions.json"
    old_writer = audit.write_private_report

    def fail_second(*, output, report, inputs):
        if output == exceptions:
            raise OSError("simulated private report I/O failure")
        return old_writer(output=output, report=report, inputs=inputs)

    monkeypatch.setattr(audit, "write_private_report", fail_second)
    with pytest.raises(OSError, match="simulated"):
        audit.write_private_report_pair(
            aggregate_output=output, aggregate_report={"safe": True},
            exceptions_output=exceptions, exceptions_report={"private": "case"},
            inputs=(tmp_path / "source.json", tmp_path / "cases.json"),
        )
    assert not output.exists()
    assert not exceptions.exists()


def test_pair_does_not_delete_replaced_aggregate_on_second_failure(tmp_path, monkeypatch):
    import tools.audit_qdkt_snapshot_cohort as audit

    output = tmp_path / "aggregate.json"
    exceptions = tmp_path / "exceptions.json"
    old_writer = audit.write_private_report
    replacement = b"unrelated replacement"

    def replace_and_fail(*, output: object, report, inputs):
        if output == exceptions:
            aggregate = tmp_path / "aggregate.json"
            aggregate.unlink()
            aggregate.write_bytes(replacement)
            raise OSError("simulated replacement and failure")
        return old_writer(output=output, report=report, inputs=inputs)

    monkeypatch.setattr(audit, "write_private_report", replace_and_fail)
    with pytest.raises(OSError):
        audit.write_private_report_pair(
            aggregate_output=output, aggregate_report={"safe": True},
            exceptions_output=exceptions, exceptions_report={"private": "case"},
            inputs=(tmp_path / "source.json", tmp_path / "cases.json"),
        )
    assert output.read_bytes() == replacement


def test_pair_rejects_existing_private_exception_without_touching_it(tmp_path):
    from tools.audit_qdkt_snapshot_cohort import write_private_report_pair

    output = tmp_path / "aggregate.json"
    exceptions = tmp_path / "exceptions.json"
    exceptions.write_bytes(b"pre-existing private evidence")
    with pytest.raises(QdKtCohortAuditBlocked, match="OUTPUT_ALREADY_EXISTS"):
        write_private_report_pair(
            aggregate_output=output, aggregate_report={"safe": True},
            exceptions_output=exceptions, exceptions_report={"private": "case"},
            inputs=(tmp_path / "source.json", tmp_path / "cases.json"),
        )
    assert not output.exists()
    assert exceptions.read_bytes() == b"pre-existing private evidence"
