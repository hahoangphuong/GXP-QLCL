"""Confidential offline report must never clobber input or follow symlinks."""
import json
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
    snap.write_text(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "workbook": {"sha256": AUTHORITATIVE_WORKBOOK_SHA256},
        "sheets": [{"sheet_name": "db.ktra", "raw_rows": [
            {"source_row_number": 1, "cells": [{"column_ordinal": 1, "raw_value": "ID"}]},
            {"source_row_number": 2, "cells": [{"column_ordinal": 1, "raw_value": 77}]},
            {"source_row_number": 3, "cells": [{"column_ordinal": 3, "raw_value": "private"}]},
        ]}],
    }), encoding="utf-8")
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
