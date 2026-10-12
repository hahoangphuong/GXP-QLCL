"""Owner-only source reconciliation tests; no workbook or DB dependency."""
from __future__ import annotations

import copy
import hashlib
import json
import sys

import pytest

from backend.app.domain.legacy_snapshot import _core_source_row
from tools.audit_ddk_idcc_physical import (
    MissingPhysicalEvidence, audit, discover_ddk_group_layout,
)
from tools.reconcile_ddk_source_artifacts import reconcile, main


def evidence(workbook_sha="b" * 64):
    fields = [
        "ID CC", "PHẠM VI CHỨNG NHẬN",
        "TIÊU CHUẨN ÁP DỤNG", "HOẠT ĐỘNG KINH DOANH",
    ]
    headers = ["ID", "ID CƠ SỞ", "ID CTY"] + fields * 4
    above = [""] * len(headers)
    for col, role in [(4, "GMP"), (8, "GLP"), (12, "GSP"), (16, "GDP")]:
        above[col - 1] = role
    plans = discover_ddk_group_layout(headers, above)
    vals = [
        "400", "10", "1",
        " 200; 201 ", " GMP scope \n", "WHO-GMP", " Manufacture ",
        "", "GLP scope", "", "",
        "", "", "", "",
        "", "", "", "GDP activity only",
    ]
    from tools.audit_ddk_idcc_physical import capture_ddk_source_row
    source = capture_ddk_source_row(
        headers, vals, 7, __import__(
            "backend.app.domain.legacy_snapshot", fromlist=["_core_header_plan"]
        )._core_header_plan(headers), plans,
    )
    snapshot = {
        "db.dkkd": [source],
        "db.cty": [{"ID": "1"}],
        "db.cso": [{"ID": "10", "ID CTY": "1"}],
        "db.cc": [
            {"ID": "200", "ID CƠ SỞ": "10", "ID CTY": "1", "LOẠI CC": "GMP"},
            {"ID": "201", "ID CƠ SỞ": "10", "ID CTY": "1", "LOẠI CC": "GMP"},
        ],
    }
    v3 = audit(
        snapshot, source_sha256=workbook_sha,
        header_evidence={
            "source_reader": "MICROSOFT_EXCEL_COM_VALUE2_READONLY",
            "source_read_only": True,
            "id_cc_literal_formula_checks": [
                {"excel_column": plan["ordinal"], "has_formula": False}
                for plan in plans
            ],
            "id_cc_columns": plans,
        },
    )
    g = {
        "schema": "GXP_DDK_GROUPED_SOURCE_EVIDENCE_V1",
        "source_sha256": workbook_sha,
        "ddk_rows": 1,
        "header_evidence": [
            {
                "group": p["observed_group_header"],
                "id_cc_column": p["ordinal"],
                "fields": p["group_field_columns"],
            }
            for p in plans
        ],
        "source_rows": [{
            "source_row_number": 7,
            "ddk_legacy_id": "400",
            "groups": [
                {
                    "source_group": x["source_group"],
                    "id_cc_excel_column": x["id_cc_excel_column"],
                    "fields": {
                        name: {
                            **field,
                            "raw_value": field["raw_value"].strip(),
                        }
                        for name, field in x["fields"].items()
                    },
                }
                for x in v3["grouped_source_rows"][0]["groups"]
            ],
        }],
    }
    l = {
        "schema": "GXP_DDK_XLSB_INDEPENDENT_SOURCE_ANALYSIS_V1",
        "source_workbook_sha256": workbook_sha,
        "summary": {"ddk_rows": 1, "token_references": 2},
        "candidates": [
            {
                "ddk_excel_row": 7, "physical_col": 4, "ddk_id": 400,
                "source_role": "GMP", "raw_cell": "200; 201",
                "token": t, "certificate_id": int(t),
            }
            for t in ("200", "201")
        ],
    }
    return g, l, v3


def test_independent_only_explicit_partial_gate_and_conservation():
    g, l, v3 = evidence()
    result = reconcile(workbook_hash="b" * 64, grouped=g, links=l)
    assert result["status"] == "PARTIAL_INDEPENDENT_EXPORTS_ONLY"
    assert result["metrics"]["ddk_rows"] == 1
    assert result["metrics"]["source_groups"] == 4
    assert result["metrics"]["source_field_cells"] == 16
    assert result["metrics"]["reference_tokens"] == 2
    assert result["metrics"]["GDP_business_activity_populated"] == 1
    assert result["approval_status"] == "NOT_APPROVED_NO_LINKS_CREATED"


def test_verified_com_v3_group_values_agree_with_independent_export():
    g, l, v3 = evidence()
    result = reconcile(workbook_hash="b" * 64, grouped=g, links=l, v3_audit=v3)
    assert result["status"] == "COM_V3_AND_INDEPENDENT_EXPORTS_CONSISTENT"
    assert result["metrics"]["reference_tokens"] == 2
    assert result["metrics"]["GLP_certificate_scope_populated"] == 1


def test_missing_or_swapped_reference_token_fails_closed():
    g, l, _ = evidence()
    wrong = copy.deepcopy(l)
    wrong["candidates"][0]["token"] = "999"
    with pytest.raises(MissingPhysicalEvidence, match="references disagree"):
        reconcile(workbook_hash="b" * 64, grouped=g, links=wrong)
    wrong = copy.deepcopy(l)
    wrong["candidates"][0]["physical_col"] = 8
    with pytest.raises(MissingPhysicalEvidence, match="Reference raw cell differs|wrong GxP"):
        reconcile(workbook_hash="b" * 64, grouped=g, links=wrong)


def test_missing_or_mutated_group_cell_blocks_and_does_not_drop_gdp():
    g, l, _ = evidence()
    broken = copy.deepcopy(g)
    del broken["source_rows"][0]["groups"][3]["fields"]["business_activity"]
    with pytest.raises(MissingPhysicalEvidence, match="missing one"):
        reconcile(workbook_hash="b" * 64, grouped=broken, links=l)
    broken = copy.deepcopy(g)
    broken["source_rows"][0]["groups"][3]["fields"]["business_activity"]["excel_column"] = 23
    with pytest.raises(MissingPhysicalEvidence, match="coordinate"):
        reconcile(workbook_hash="b" * 64, grouped=broken, links=l)


def test_wrong_workbook_fingerprint_and_com_source_drift_block():
    g, l, v3 = evidence()
    with pytest.raises(MissingPhysicalEvidence, match="fingerprints"):
        reconcile(workbook_hash="c" * 64, grouped=g, links=l)
    tampered = copy.deepcopy(v3)
    tampered["grouped_source_rows"][0]["groups"][3]["fields"]["business_activity"]["raw_value"] = "changed"
    with pytest.raises(MissingPhysicalEvidence, match="source cell differs"):
        reconcile(workbook_hash="b" * 64, grouped=g, links=l, v3_audit=tampered)
    tampered = copy.deepcopy(v3)
    tampered["candidates"][0]["raw_fk_token"] = "wrong"
    with pytest.raises(MissingPhysicalEvidence, match="V3 references disagree"):
        reconcile(workbook_hash="b" * 64, grouped=g, links=l, v3_audit=tampered)


def test_cli_never_overwrites_inputs_or_previous_outputs(tmp_path, monkeypatch):
    workbook = tmp_path / "source.xlsb"
    workbook.write_bytes(b"test XLSB placeholder; checks only SHA, not workbook parser")
    sha = hashlib.sha256(workbook.read_bytes()).hexdigest()
    grouped, links, _ = evidence(sha)
    gp = tmp_path / "groups.json"
    rp = tmp_path / "references.json"
    gp.write_text(json.dumps(grouped), encoding="utf-8")
    rp.write_text(json.dumps(links), encoding="utf-8")
    target = tmp_path / "reconciled.json"
    monkeypatch.setattr(sys, "argv", [
        "reconcile_ddk_source_artifacts", "--workbook", str(workbook),
        "--groups-json", str(gp), "--references-json", str(rp),
        "--output", str(target),
    ])
    assert main() == 0
    assert json.loads(target.read_text())["status"] == "PARTIAL_INDEPENDENT_EXPORTS_ONLY"
    first = target.read_bytes()
    with pytest.raises(SystemExit) as err:
        main()
    assert err.value.code == 2
    assert first == target.read_bytes()
    monkeypatch.setattr(sys, "argv", [
        "reconcile_ddk_source_artifacts", "--workbook", str(workbook),
        "--groups-json", str(gp), "--references-json", str(rp),
        "--output", str(gp),
    ])
    original = gp.read_bytes()
    with pytest.raises(SystemExit) as err:
        main()
    assert err.value.code == 2
    assert original == gp.read_bytes()


def test_com_source_provenance_requires_all_literal_formula_checks():
    g, l, v3 = evidence()
    legacy = copy.deepcopy(v3)
    del legacy["header_evidence"]["id_cc_literal_formula_checks"]
    with pytest.raises(MissingPhysicalEvidence, match="formula checks"):
        reconcile(workbook_hash="b" * 64, grouped=g, links=l, v3_audit=legacy)
    changed = copy.deepcopy(v3)
    changed["header_evidence"]["id_cc_literal_formula_checks"][0]["has_formula"] = True
    with pytest.raises(MissingPhysicalEvidence, match="formula checks"):
        reconcile(workbook_hash="b" * 64, grouped=g, links=l, v3_audit=changed)
    untrusted = copy.deepcopy(v3)
    untrusted["header_evidence"]["source_reader"] = "LEGACY_FLATTENED_XLSB"
    with pytest.raises(MissingPhysicalEvidence, match="read-only Excel COM"):
        reconcile(workbook_hash="b" * 64, grouped=g, links=l, v3_audit=untrusted)
