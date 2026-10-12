"""No-write DDK group provenance load plan contract and tampering regressions."""
from __future__ import annotations

import copy
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

from tools.audit_ddk_idcc_physical import MissingPhysicalEvidence
from tools.plan_ddk_gxp_provenance_load import (
    PLAN_SCHEMA, build_source_provenance_dry_run, main,
)


SHA = "a" * 64
HEADERS = [
    ("id_cc", "ID CC"),
    ("certificate_scope", "PHẠM VI CHỨNG NHẬN"),
    ("applicable_standard", "TIÊU CHUẨN ÁP DỤNG"),
    ("business_activity", "HOẠT ĐỘNG KINH DOANH"),
]
COLUMNS = [("GMP", 15), ("GLP", 19), ("GSP", 23), ("GDP", 27)]


def fixture():
    plans = [{
        "group": role, "id_cc_column": col,
        "fields": {
            name: {"excel_column": col + offset, "source_header": label}
            for offset, (name, label) in enumerate(HEADERS)
        },
    } for role, col in COLUMNS]
    rows = []
    for row_no, ddk_id in [(5, "400"), (6, "401")]:
        groups = []
        for role, col in COLUMNS:
            raw = {
                "id_cc": "200; 201" if row_no == 5 and role == "GMP" else "",
                "certificate_scope": "  Sterile\n" if row_no == 5 and role == "GMP" else "",
                "applicable_standard": " WHO-GMP " if row_no == 5 and role == "GMP" else "",
                "business_activity": "Bán buôn thuốc" if row_no == 5 and role == "GDP" else "",
            }
            groups.append({
                "source_group": role, "id_cc_excel_column": col,
                "fields": {
                    name: {"excel_column": col + offset, "source_header": label,
                           "raw_value": raw[name]}
                    for offset, (name, label) in enumerate(HEADERS)
                },
            })
        rows.append({
            "source_row_number": row_no, "ddk_legacy_id": ddk_id, "groups": groups,
        })
    grouped = {
        "schema": "GXP_DDK_GROUPED_SOURCE_EVIDENCE_V1",
        "source_sha256": SHA, "ddk_rows": 2,
        "header_evidence": plans, "source_rows": rows,
    }
    refs = [{
        "ddk_excel_row": 5, "physical_col": 15, "ddk_id": 400,
        "source_role": "GMP", "raw_cell": "200; 201", "token": token,
        "certificate_id": int(token),
    } for token in ("200", "201")]
    references = {
        "schema": "GXP_DDK_XLSB_INDEPENDENT_SOURCE_ANALYSIS_V1",
        "source_workbook_sha256": SHA,
        "summary": {"ddk_rows": 2, "token_references": 2},
        "candidates": refs,
    }
    confirmation = {
        "confirmation_source": "user_review_of_anomaly_report",
        "by_sheet": {
            "db.dkkd": {
                "row_count": 1, "source_row_keys": ["401"],
                "legacy_row_ids": ["401"],
            },
        },
        "rows": [{
            "source_sheet": "db.dkkd", "source_row_key": "401",
            "source_row_number": 6, "legacy_row_id": "401",
            "classification": "confirmed_blanked_row",
            "migration_action": "exclude_from_business_import",
            "confirmation_source": "user_review_of_anomaly_report",
        }],
    }
    return grouped, references, confirmation


def plan(g=None, l=None, c=None, **override):
    source = fixture()
    return build_source_provenance_dry_run(
        g if g is not None else source[0],
        l if l is not None else source[1],
        c if c is not None else source[2],
        accepted_workbook_sha256=override.get("accepted_workbook_sha256", SHA),
        expected_ddk_rows=override.get("expected_ddk_rows", 2),
        expected_excluded_ddk_rows=override.get("expected_excluded_ddk_rows", 1),
        expected_reference_tokens=override.get("expected_reference_tokens", 2),
    )


def test_dry_run_conserves_source_fields_and_links_no_canonical_identity():
    result = plan()
    assert result["schema"] == PLAN_SCHEMA
    assert result["status"] == "DRY_RUN_ONLY_NOT_APPLIED"
    assert result["counts"]["original_ddk_rows"] == 2
    assert result["counts"]["excluded_ddk_rows"] == 1
    assert result["counts"]["effective_ddk_rows"] == 1
    assert result["counts"]["group_rows"] == 4
    assert result["counts"]["field_positions"] == 16
    assert result["counts"]["reference_tokens"] == 2
    assert result["counts"]["companion_without_id_cc"] == 1
    assert result["counts"]["gdp_business_activity_without_id_cc"] == 1
    assert result["target"]["database_state"] == "NOT_CONNECTED_NOT_INSPECTED"
    assert result["target"]["canonical_link_changes"] == 0
    assert result["target"]["uuid_allocation"] == "NOT_PERFORMED"
    assert result["target"]["sql_writes_executed"] == 0
    assert result["excluded_source_rows"] == [
        {"source_row_number": 6, "legacy_dkkd_id": 401},
    ]
    payload = result["payload"]
    assert len(payload["source_groups"]) == 4
    assert len(payload["reference_tokens"]) == 2
    assert payload["group_table"] == "business_eligibility_gxp_source_group"
    assert payload["token_table"] == "business_eligibility_gxp_reference_evidence"
    assert [(r["values"]["token_index"], r["values"]["parsed_legacy_certificate_id"])
            for r in payload["reference_tokens"]] == [(1, 200), (2, 201)]
    gmp = next(x["values"] for x in payload["source_groups"] if x["values"]["source_group"] == "GMP")
    assert gmp["certificate_scope_raw"] == "  Sterile\n"
    assert gmp["applicable_standard_raw"] == " WHO-GMP "
    assert gmp["id_cc_raw"] == "200; 201"
    assert len(gmp["source_values_sha256"]) == 64
    gdp = next(x["values"] for x in payload["source_groups"] if x["values"]["source_group"] == "GDP")
    assert gdp["id_cc_raw"] == ""
    assert gdp["business_activity_raw"] == "Bán buôn thuốc"
    for record in payload["source_groups"]:
        assert set(record["values"]).isdisjoint({
            "id", "certificate_id", "certificate_version_id", "business_eligibility_version_id",
        })
    assert plan()["payload_sha256"] == result["payload_sha256"]


def test_baseline_count_and_workbook_hash_are_mandatory_drift_gates():
    with pytest.raises(MissingPhysicalEvidence, match="baseline counts have drifted"):
        plan(expected_reference_tokens=3)
    with pytest.raises(MissingPhysicalEvidence, match="exclusion count"):
        plan(expected_excluded_ddk_rows=0)
    with pytest.raises(MissingPhysicalEvidence, match="fingerprints"):
        plan(accepted_workbook_sha256="f" * 64)
    with pytest.raises(MissingPhysicalEvidence, match="Malformed accepted workbook"):
        plan(accepted_workbook_sha256="z" * 64)


def test_excluded_row_must_match_physical_ddk_id_and_remain_blank():
    g, l, c = fixture()
    bad = copy.deepcopy(c)
    bad["rows"][0]["source_row_number"] = 5
    with pytest.raises(MissingPhysicalEvidence, match="exclusion disagrees"):
        plan(c=bad)
    bad = copy.deepcopy(g)
    bad["source_rows"][1]["groups"][3]["fields"]["business_activity"]["raw_value"] = "DO NOT DROP"
    with pytest.raises(MissingPhysicalEvidence, match="populated source group"):
        plan(g=bad)
    bad = copy.deepcopy(c)
    bad["by_sheet"]["db.dkkd"]["legacy_row_ids"] = ["1"]
    with pytest.raises(MissingPhysicalEvidence, match="Approved exclusions differ"):
        plan(c=bad)


def test_reconcile_token_multiset_blocks_wrong_role_even_when_id_valid():
    g, l, c = fixture()
    other = copy.deepcopy(l)
    other["candidates"][1]["source_role"] = "GLP"
    with pytest.raises(MissingPhysicalEvidence, match="wrong GxP"):
        plan(l=other)
    other = copy.deepcopy(l)
    other["candidates"][1]["token"] = "999"
    with pytest.raises(MissingPhysicalEvidence, match="references disagree"):
        plan(l=other)


def test_missing_gdp_field_or_truncated_source_refuses_dry_run():
    g, l, c = fixture()
    other = copy.deepcopy(g)
    del other["source_rows"][0]["groups"][3]["fields"]["business_activity"]
    with pytest.raises(MissingPhysicalEvidence, match="missing one of four"):
        plan(g=other)
    other = copy.deepcopy(g)
    other["source_rows"][0]["groups"].pop()
    with pytest.raises(MissingPhysicalEvidence, match="all four GxP"):
        plan(g=other)


def test_cli_does_not_overwrite_inputs_or_earlier_plan(tmp_path, monkeypatch):
    g, l, c = fixture()
    path_map = {
        "groups": tmp_path / "groups.json",
        "refs": tmp_path / "refs.json",
        "confirmed": tmp_path / "confirmed.json",
    }
    for label, data in zip(path_map, (g, l, c)):
        path_map[label].write_text(json.dumps(data), encoding="utf-8")
    output = tmp_path / "plan.json"
    def argv(out):
        return [
            "plan_ddk_gxp_provenance_load",
            "--groups-json", str(path_map["groups"]),
            "--references-json", str(path_map["refs"]),
            "--approved-exclusions-json", str(path_map["confirmed"]),
            "--expected-workbook-sha256", SHA,
            "--expected-ddk-rows", "2", "--expected-excluded-ddk-rows", "1",
            "--expected-reference-tokens", "2", "--output", str(out),
        ]
    monkeypatch.setattr(sys, "argv", argv(output))
    assert main() == 0
    raw = output.read_bytes()
    loaded = json.loads(raw)
    assert loaded["payload_sha256"] == plan()["payload_sha256"]
    assert loaded["input_artifact_sha256"]["groups_json"] == sha256(
        path_map["groups"].read_bytes()
    ).hexdigest()
    with pytest.raises(SystemExit) as err:
        main()
    assert err.value.code == 2
    assert output.read_bytes() == raw
    monkeypatch.setattr(sys, "argv", argv(path_map["groups"]))
    original = path_map["groups"].read_bytes()
    with pytest.raises(SystemExit) as err:
        main()
    assert err.value.code == 2
    assert path_map["groups"].read_bytes() == original
