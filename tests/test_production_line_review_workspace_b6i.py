from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import os
import subprocess
from zipfile import ZipFile

import pytest

from backend.app.domain.production_line_population import CANONICAL_STATE_SCHEMA_VERSION, canonical_json_bytes
from backend.app.domain.production_line_review_workspace import (
    PENDING_DECISION,
    ProductionLineReviewWorkspaceError,
    build_cross_site_text_report,
    build_certificate_site_mismatch_report,
    build_review_workspace,
    build_review_summary,
    reviewed_roster_from_rows,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_NODE = Path(r"C:\Users\hahoa\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe")
RUNTIME_MODULES = r"C:\Users\hahoa\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"
RUNTIME_ARTIFACT_TOOL = Path(RUNTIME_MODULES) / "@oai" / "artifact-tool" / "dist" / "artifact_tool.mjs"


SNAPSHOT_SHA = "484cf37603aacc5ff01a7bde5ffab01ed444748d5c7b1a0b30e7fc3a04936caa"
SITE_7 = "00000000-0000-0000-0000-000000000007"
SITE_8 = "00000000-0000-0000-0000-000000000008"
CASE_10 = "00000000-0000-0000-0000-000000000010"
CERTIFICATE_20 = "00000000-0000-0000-0000-000000000020"


def _row(number: int, values: dict[int, object]) -> dict[str, object]:
    return {"source_row_number": number, "cells": [{"column_ordinal": key, "raw_value": value} for key, value in values.items()]}


def _snapshot() -> dict[str, object]:
    return {"schema_version": "legacy-workbook-snapshot/v2", "sheets": [
        {"sheet_name": "db.ktra", "raw_rows": [_row(4, {1: "ID", 2: "LOẠI KT", 3: "ID CƠ SỞ", 4: "MÃ DC", 9: "Mã hồ sơ"}), _row(5, {1: 10, 2: "GMP", 3: 7, 4: "A+C", 9: "SCOPE-10"}), _row(6, {1: 11, 2: "GMP", 3: 8, 4: "A+C", 9: "SCOPE-11"})]},
        {"sheet_name": "db.cc", "raw_rows": [_row(4, {1: "ID", 4: "LOẠI CC", 5: "ID ĐỢT KTRA", 8: "ID CƠ SỞ", 9: "MÃ DC", 20: "Mã số CC"}), _row(5, {1: 20, 4: "GMP", 5: 10, 8: 7, 9: "A+C", 20: "CC-20"})]},
        {"sheet_name": "db.cso", "raw_rows": [_row(4, {1: "ID", 6: "TÊN CƠ SỞ"}), _row(5, {1: 7, 6: "Site Seven"}), _row(6, {1: 8, 6: "Site Eight"})]},
    ]}


def _state() -> dict[str, object]:
    state = {"schema_version": CANONICAL_STATE_SCHEMA_VERSION, "exported_at": None, "source_database_identity": {"database_name": "fixture"}, "source_alembic_revision": "20260929_0017", "sites": [{"id": SITE_7, "legacy_site_id": 7}, {"id": SITE_8, "legacy_site_id": 8}], "existing_production_lines": [], "cases": [{"id": CASE_10, "legacy_inspection_id": 10, "site_id": SITE_7, "production_line_id": None}, {"id": "00000000-0000-0000-0000-000000000011", "legacy_inspection_id": 11, "site_id": SITE_8, "production_line_id": None}], "certificates": [{"id": CERTIFICATE_20, "legacy_certificate_id": 20, "case_id": CASE_10, "site_id": SITE_7, "production_line_id": None}], "physical_line_evidence": [], "transformations": []}
    state["source_state_fingerprint"] = sha256(canonical_json_bytes(state)).hexdigest()
    return state


def _workspace():
    state = _state()
    state_sha = sha256(canonical_json_bytes(state)).hexdigest()
    return build_review_workspace(_snapshot(), snapshot_sha256=SNAPSHOT_SHA, canonical_state=state, canonical_state_sha256=state_sha)


def test_review_workspace_propagates_useful_tags_batches_and_compact_evidence():
    workspace = _workspace()
    roster = workspace["roster"]
    assert len(roster["items"]) == 2
    first = next(item for item in roster["items"] if item["source_site_legacy_id"] == 7)
    assert first["review_tags"] == ["CASE_AND_CERTIFICATE_AGREE", "SINGLE_CASE_SINGLE_CERTIFICATE", "CROSS_SITE_TEXT_REUSE", "COMBINED_NOTATION", "HIGH_INFORMATION_FOR_REVIEW"]
    assert first["primary_review_batch"] == "C_SPECIAL_EXCEPTION"
    assert first["site_display_name"] == "Site Seven"
    assert workspace["evidence"][0]["certificate_samples"][0]["certificate_reference"] == "CC-20"
    cross_site = build_cross_site_text_report(roster)
    assert cross_site["records"][0]["classification"] == "SEPARATE_SITE_SCOPED_CANDIDATES"
    assert len(cross_site["records"][0]["candidate_keys"]) == 2


def test_review_decision_contract_and_tampering_fail_closed():
    roster = _workspace()["roster"]
    metadata = {key: roster[key] for key in ("legacy_snapshot_sha256", "canonical_state_sha256", "planner_version", "candidate_set_sha256")}
    rows = [{key: item.get(key) for key in ("candidate_key", "source_site_legacy_id", "canonical_site_id", "canonical_line_text", "review_decision", "approved_display_code", "existing_production_line_id", "review_reason", "reviewer", "reviewed_at")} for item in roster["items"]]
    round_trip = reviewed_roster_from_rows(roster, workbook_metadata=metadata, review_rows=rows, existing_line_ids=set())
    assert all(item["review_decision"] == PENDING_DECISION for item in round_trip["items"])
    edited = deepcopy(rows)
    edited[0].update({"review_decision": "APPROVE_NEW_PHYSICAL_LINE", "approved_display_code": "A+C", "review_reason": "Evidence reviewed"})
    reviewed = reviewed_roster_from_rows(roster, workbook_metadata=metadata, review_rows=edited, existing_line_ids=set())
    assert reviewed["items"][0]["review_status"] == "REVIEWED"
    tampered = deepcopy(rows)
    tampered[0]["canonical_line_text"] = "OTHER"
    with pytest.raises(ProductionLineReviewWorkspaceError, match="immutable"):
        reviewed_roster_from_rows(roster, workbook_metadata=metadata, review_rows=tampered, existing_line_ids=set())
    with pytest.raises(ProductionLineReviewWorkspaceError, match="candidate set"):
        reviewed_roster_from_rows(roster, workbook_metadata=metadata, review_rows=rows[:-1], existing_line_ids=set())
    with pytest.raises(ProductionLineReviewWorkspaceError, match="provenance"):
        reviewed_roster_from_rows(roster, workbook_metadata={**metadata, "candidate_set_sha256": "x"}, review_rows=rows, existing_line_ids=set())


def test_mapping_is_rejected_without_bound_existing_line_and_reject_requires_reason():
    roster = _workspace()["roster"]
    metadata = {key: roster[key] for key in ("legacy_snapshot_sha256", "canonical_state_sha256", "planner_version", "candidate_set_sha256")}
    rows = [{key: item.get(key) for key in ("candidate_key", "source_site_legacy_id", "canonical_site_id", "canonical_line_text", "review_decision", "approved_display_code", "existing_production_line_id", "review_reason", "reviewer", "reviewed_at")} for item in roster["items"]]
    rows[0].update({"review_decision": "MAP_TO_EXISTING_PRODUCTION_LINE", "existing_production_line_id": SITE_7, "review_reason": "Not allowed in current state"})
    with pytest.raises(ProductionLineReviewWorkspaceError, match="not available"):
        reviewed_roster_from_rows(roster, workbook_metadata=metadata, review_rows=rows, existing_line_ids=set())
    rows[0].update({"review_decision": "REJECT_NOT_PHYSICAL_LINE", "existing_production_line_id": None, "review_reason": None})
    with pytest.raises(ProductionLineReviewWorkspaceError, match="review_reason"):
        reviewed_roster_from_rows(roster, workbook_metadata=metadata, review_rows=rows, existing_line_ids=set())


@pytest.mark.parametrize("tamper", ["candidate", "site", "duplicate", "foreign"])
def test_candidate_set_tampering_is_rejected(tamper):
    roster = _workspace()["roster"]
    metadata = {key: roster[key] for key in ("legacy_snapshot_sha256", "canonical_state_sha256", "planner_version", "candidate_set_sha256")}
    rows = [{key: item.get(key) for key in ("candidate_key", "source_site_legacy_id", "canonical_site_id", "canonical_line_text", "review_decision", "approved_display_code", "existing_production_line_id", "review_reason", "reviewer", "reviewed_at")} for item in roster["items"]]
    if tamper == "candidate":
        rows[0]["candidate_key"] = "legacy-line:foreign"
    elif tamper == "site":
        rows[0]["canonical_site_id"] = SITE_8
    elif tamper == "duplicate":
        rows.append(deepcopy(rows[0]))
    else:
        rows.append({**deepcopy(rows[0]), "candidate_key": "legacy-line:foreign"})
    with pytest.raises(ProductionLineReviewWorkspaceError):
        reviewed_roster_from_rows(roster, workbook_metadata=metadata, review_rows=rows, existing_line_ids=set())


def test_reviewed_roster_is_deterministic_for_approve_defer_and_reject():
    roster = _workspace()["roster"]
    metadata = {key: roster[key] for key in ("legacy_snapshot_sha256", "canonical_state_sha256", "planner_version", "candidate_set_sha256")}
    rows = [{key: item.get(key) for key in ("candidate_key", "source_site_legacy_id", "canonical_site_id", "canonical_line_text", "review_decision", "approved_display_code", "existing_production_line_id", "review_reason", "reviewer", "reviewed_at")} for item in roster["items"]]
    rows[0].update({"review_decision": "APPROVE_NEW_PHYSICAL_LINE", "approved_display_code": "LINE-A-C", "review_reason": "Corroborated review evidence"})
    rows[1].update({"review_decision": "REJECT_NOT_PHYSICAL_LINE", "review_reason": "Reviewer found a non-line notation"})
    first = reviewed_roster_from_rows(roster, workbook_metadata=metadata, review_rows=rows, existing_line_ids=set())
    second = reviewed_roster_from_rows(roster, workbook_metadata=metadata, review_rows=deepcopy(rows), existing_line_ids=set())
    assert first == second
    assert [item["review_decision"] for item in first["items"]] == ["APPROVE_NEW_PHYSICAL_LINE", "REJECT_NOT_PHYSICAL_LINE"]


def test_certificate_site_mismatch_report_remains_read_only_and_evidence_limited():
    snapshot = _snapshot()
    snapshot["sheets"][1]["raw_rows"][1]["cells"] = [
        {"column_ordinal": 1, "raw_value": 20}, {"column_ordinal": 4, "raw_value": "GMP"},
        {"column_ordinal": 5, "raw_value": 10}, {"column_ordinal": 8, "raw_value": 8},
        {"column_ordinal": 9, "raw_value": "A+C"}, {"column_ordinal": 20, "raw_value": "CC-20"},
    ]
    state = _state()
    state_sha = sha256(canonical_json_bytes(state)).hexdigest()
    workspace = build_review_workspace(snapshot, snapshot_sha256=SNAPSHOT_SHA, canonical_state=state, canonical_state_sha256=state_sha)
    report = build_certificate_site_mismatch_report(workspace, state)
    assert report["records"][0]["planner_block_reason"] == "CASE_CERTIFICATE_SITE_DIFFERS"
    assert report["records"][0]["review_classification"] == "INSUFFICIENT_EVIDENCE"
    mismatch_item = next(item for item in workspace["roster"]["items"] if 20 in item["source_certificate_ids"])
    assert "CERTIFICATE_SITE_MISMATCH_CONTEXT" in mismatch_item["review_tags"]
    assert mismatch_item["primary_review_batch"] == "C_SPECIAL_EXCEPTION"


def test_cross_site_and_letter_only_tags_are_secondary_to_evidence_quality():
    snapshot = _snapshot()
    for row in snapshot["sheets"][0]["raw_rows"][1:]:
        for cell in row["cells"]:
            if cell["column_ordinal"] == 4:
                cell["raw_value"] = "A"
    for cell in snapshot["sheets"][1]["raw_rows"][1]["cells"]:
        if cell["column_ordinal"] == 9:
            cell["raw_value"] = "A"
    state = _state()
    workspace = build_review_workspace(snapshot, snapshot_sha256=SNAPSHOT_SHA, canonical_state=state, canonical_state_sha256=sha256(canonical_json_bytes(state)).hexdigest())
    multi_source = next(item for item in workspace["roster"]["items"] if item["source_site_legacy_id"] == 7)
    case_only = next(item for item in workspace["roster"]["items"] if item["source_site_legacy_id"] == 8)
    assert {"CROSS_SITE_TEXT_REUSE", "LETTER_ONLY", "CASE_AND_CERTIFICATE_AGREE"}.issubset(multi_source["review_tags"])
    assert multi_source["primary_review_batch"] == "A_MULTI_SOURCE_HIGH_INFORMATION"
    assert {"CROSS_SITE_TEXT_REUSE", "LETTER_ONLY", "CASE_ONLY"}.issubset(case_only["review_tags"])
    assert case_only["primary_review_batch"] == "B_CASE_ONLY"


def test_summary_reads_mismatch_review_classification_and_omits_universal_tag_priority():
    workspace = _workspace()
    report = {"records": [{"review_classification": "INSUFFICIENT_EVIDENCE"}]}
    cross_site = build_cross_site_text_report(workspace["roster"])
    summary = build_review_summary(workspace["roster"], certificate_mismatch_report=report, cross_site_report=cross_site)
    assert "Certificate Site mismatch INSUFFICIENT_EVIDENCE: 1" in summary
    assert "LETTER_ONLY:" not in summary


def test_xlsx_workspace_round_trip_preserves_pending_rows_and_metadata(tmp_path):
    if not RUNTIME_NODE.exists():
        pytest.skip("bundled artifact-tool Node runtime is unavailable")
    workspace = _workspace()
    roster = tmp_path / "roster.json"
    evidence = tmp_path / "evidence.json"
    workbook = tmp_path / "review.xlsx"
    extracted = tmp_path / "extracted.json"
    roster.write_text(json.dumps(workspace["roster"], ensure_ascii=False), encoding="utf-8")
    evidence.write_text(json.dumps({"records": workspace["evidence"]}, ensure_ascii=False), encoding="utf-8")
    environment = {**os.environ, "NODE_PATH": RUNTIME_MODULES, "B6I_ARTIFACT_TOOL_URL": RUNTIME_ARTIFACT_TOOL.as_uri()}
    subprocess.run([str(RUNTIME_NODE), str(ROOT / "tools" / "build_production_line_review_workbook_b6i.mjs"), "--roster", str(roster), "--evidence", str(evidence), "--output", str(workbook)], check=True, env=environment)
    subprocess.run([str(RUNTIME_NODE), str(ROOT / "tools" / "extract_production_line_review_workbook_b6i.mjs"), "--input", str(workbook), "--output", str(extracted)], check=True, env=environment)
    payload = json.loads(extracted.read_text(encoding="utf-8"))
    assert payload["metadata"]["candidate_set_sha256"] == workspace["roster"]["candidate_set_sha256"]
    assert len(payload["rows"]) == len(workspace["roster"]["items"])
    assert {row["review_decision"] for row in payload["rows"]} == {PENDING_DECISION}
    with ZipFile(workbook) as archive:
        review_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        table_xml = archive.read("xl/tables/table1.xml").decode("utf-8")
    assert 'ySplit="3"' in review_xml
    assert 'sqref="P4:P5"' in review_xml
    assert "tableParts" in review_xml
    assert 'name="ProductionLineReviewCandidates"' in table_xml
    assert 'ref="A3:U5"' in table_xml
    assert '<x:autoFilter ref="A3:U5" />' in table_xml
    reviewed = tmp_path / "reviewed.json"
    subprocess.run([
        "py", "tools/import_production_line_review_workbook_b6i.py", "--workbook", str(workbook), "--template", str(roster),
        "--output", str(reviewed), "--node", str(RUNTIME_NODE), "--artifact-tool-url", RUNTIME_ARTIFACT_TOOL.as_uri(),
    ], cwd=ROOT, check=True, env=environment)
    assert json.loads(reviewed.read_text(encoding="utf-8"))["candidate_set_sha256"] == workspace["roster"]["candidate_set_sha256"]



@pytest.mark.parametrize("target", ("workbook", "template", "existing_output", "hardlink_template"))
def test_b6i_import_cli_never_clobbers_inputs_or_existing_review(tmp_path, capsys, target):
    from tools import import_production_line_review_workbook_b6i as importer

    workbook = tmp_path / "review.xlsx"
    template = tmp_path / "roster_template.json"
    output = tmp_path / "reviewed.json"
    workbook.write_bytes(b"keep-original-workbook")
    template.write_bytes(b"keep-original-template")
    if target == "workbook":
        output = workbook
    elif target == "template":
        output = template
    elif target == "existing_output":
        output.write_bytes(b"keep-previous-reviewed-roster")
    else:
        output.hardlink_to(template)
    before = (workbook.read_bytes(), template.read_bytes(), output.read_bytes())
    with pytest.raises(SystemExit) as error:
        importer.main([
            "--workbook", str(workbook), "--template", str(template),
            "--output", str(output),
        ])
    assert error.value.code == 2
    assert "output" in capsys.readouterr().err
    assert (workbook.read_bytes(), template.read_bytes(), output.read_bytes()) == before


def test_b6i_import_cli_uses_private_extraction_path_and_preserves_existing_neighbor(tmp_path, monkeypatch):
    from tools import import_production_line_review_workbook_b6i as importer

    roster = _workspace()["roster"]
    template = tmp_path / "template.json"
    workbook = tmp_path / "review.xlsx"
    output = tmp_path / "reviewed.json"
    legacy_extracted = output.with_suffix(".extracted.json")
    template.write_text(json.dumps(roster), encoding="utf-8")
    workbook.write_bytes(b"mock workbook, extractor is replaced")
    legacy_extracted.write_bytes(b"do-not-delete-preexisting-evidence")
    metadata = {key: roster[key] for key in ("legacy_snapshot_sha256", "canonical_state_sha256", "planner_version", "candidate_set_sha256")}
    row_fields = ("candidate_key", "source_site_legacy_id", "canonical_site_id", "canonical_line_text",
                  "review_decision", "approved_display_code", "existing_production_line_id",
                  "review_reason", "reviewer", "reviewed_at")
    rows = [{key: item.get(key) for key in row_fields} for item in roster["items"]]
    extraction_paths = []

    def fake_extract(command, *, check, env):
        path = Path(command[command.index("--output") + 1])
        extraction_paths.append(path)
        assert check is True
        assert path != legacy_extracted
        path.write_text(json.dumps({"metadata": metadata, "rows": rows}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_extract)
    assert importer.main([
        "--workbook", str(workbook), "--template", str(template), "--output", str(output),
    ]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["candidate_set_sha256"] == roster["candidate_set_sha256"]
    assert legacy_extracted.read_bytes() == b"do-not-delete-preexisting-evidence"
    assert len(extraction_paths) == 1
    assert not extraction_paths[0].exists()
