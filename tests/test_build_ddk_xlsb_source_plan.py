"""Linux read-only XLSB physical DDK field reconstruction; no Excel or DB."""
from __future__ import annotations
import json
from hashlib import sha256

import pytest
from tools.audit_ddk_idcc_physical import MissingPhysicalEvidence
from tools.build_ddk_xlsb_source_plan import original_ddk_physical_evidence, create_sealed_xlsb_plan
from tools.plan_ddk_gxp_provenance_load import build_source_provenance_dry_run


SHA = "a" * 64
GROUPS = [("GMP", 15), ("GLP", 19), ("GSP", 23), ("GDP", 27)]
FIELDS = ["ID CC", "PHẠM VI CHỨNG NHẬN", "TIÊU CHUẨN ÁP DỤNG", "HOẠT ĐỘNG KINH DOANH"]


def physical_rows():
    labels = [None] * 30
    heads = [None] * 30
    for role, ordinal in GROUPS:
        labels[ordinal - 1] = role
        for offset, field in enumerate(FIELDS):
            heads[ordinal - 1 + offset] = field
    heads[0] = "ID"
    def row(id, gmp="", gdp="", scope=""):
        values = [None] * 30
        values[0] = id
        values[14] = gmp
        values[15] = scope
        values[29] = gdp
        return values
    return [
        (3, labels), (4, heads),
        (5, row(400.0, "200; 201", " GDP activity only ", " Sterile\n")),
        (6, row(401.0)),
    ]


def exclusions():
    return {
        "confirmation_source": "user_review_of_anomaly_report",
        "by_sheet": {"db.dkkd": {
            "row_count": 1, "source_row_keys": ["401"], "legacy_row_ids": ["401"],
        }},
        "rows": [{
            "source_sheet": "db.dkkd", "source_row_key": "401",
            "source_row_number": 6, "legacy_row_id": "401",
            "classification": "confirmed_blanked_row",
            "migration_action": "exclude_from_business_import",
            "confirmation_source": "user_review_of_anomaly_report",
        }],
    }


def test_grouped_columns_and_idcc_tokens_are_distinct():
    grouped, refs = original_ddk_physical_evidence(physical_rows(), SHA)
    assert grouped["ddk_rows"] == 2
    assert [x["group"] for x in grouped["header_evidence"]] == [
        "GMP", "GLP", "GSP", "GDP"
    ]
    assert [(x["physical_col"], x["source_role"], x["token"]) for x in refs["candidates"]] == [
        (15, "GMP", "200"), (15, "GMP", "201"),
    ]
    plan = build_source_provenance_dry_run(
        grouped, refs, exclusions(),
        accepted_workbook_sha256=SHA, expected_ddk_rows=2,
        expected_excluded_ddk_rows=1, expected_reference_tokens=2,
    )
    assert plan["counts"]["group_rows"] == 4
    assert plan["counts"]["reference_tokens"] == 2
    assert plan["counts"]["gdp_business_activity_without_id_cc"] == 1
    groups = {p["values"]["source_group"]: p["values"] for p in plan["payload"]["source_groups"]}
    assert groups["GMP"]["certificate_scope_raw"] == " Sterile\n"
    assert groups["GDP"]["business_activity_raw"] == " GDP activity only "
    assert plan["target"]["canonical_link_changes"] == 0


def test_rejects_missing_group_label_or_column():
    rows = physical_rows()
    rows[0][1][18] = None
    with pytest.raises(MissingPhysicalEvidence):
        original_ddk_physical_evidence(rows, SHA)
    rows = physical_rows()
    rows[2][1].pop()
    with pytest.raises(MissingPhysicalEvidence):
        original_ddk_physical_evidence(rows, SHA)


def test_rejects_malformed_cell_and_duplicate_rows():
    rows = physical_rows()
    rows[2][1][14] = "200; ;201"
    with pytest.raises(MissingPhysicalEvidence):
        original_ddk_physical_evidence(rows, SHA)
    rows = physical_rows()
    rows.append(rows[2])
    with pytest.raises(MissingPhysicalEvidence):
        original_ddk_physical_evidence(rows, SHA)


def test_sealed_real_workbook_pin_required_and_preserved(tmp_path):
    workbook = tmp_path / "original.xlsb"
    workbook.write_bytes(b"synthetic-test-binary")
    actual = sha256(workbook.read_bytes()).hexdigest()
    exclusions_file = tmp_path / "exclusions.json"
    exclusions_file.write_text(json.dumps(exclusions()), encoding="utf-8")
    rows = physical_rows()
    plan = create_sealed_xlsb_plan(
        workbook, exclusions_file, expected_sha256=actual,
        expected_rows=2, expected_excluded_rows=1,
        expected_reference_tokens=2, row_loader=lambda _: rows,
    )
    assert plan["physical_source_reader"]["reader"] == "PYXLSB_CACHED_CELLS_SINGLE_READER"
    assert plan["physical_source_reader"]["excel_com_formula_status"] == "WAIVED_NOT_CHECKED"
    assert plan["physical_source_reader"]["independent_reader_verification"] is False
    assert plan["source_workbook_sha256"] == actual
    with pytest.raises(MissingPhysicalEvidence, match="SHA-256 mismatch"):
        create_sealed_xlsb_plan(
            workbook, exclusions_file, expected_sha256="f" * 64,
            expected_rows=2, expected_excluded_rows=1,
            expected_reference_tokens=2, row_loader=lambda _: rows,
        )
