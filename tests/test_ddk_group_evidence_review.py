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
from tools.ddk_group_evidence_review import build_group_review_manifest, main


def fixture():
    fields = ["ID CC", "PHẠM VI CHỨNG NHẬN", "TIÊU CHUẨN ÁP DỤNG", "HOẠT ĐỘNG KINH DOANH"]
    headers = ["ID", "ID CƠ SỞ", "ID CTY"] + fields * 4
    group_header = [""] * len(headers)
    for start, label in [(4, "GMP"), (8, "GLP"), (12, "GSP"), (16, "GDP")]:
        group_header[start - 1] = label
    plans = discover_ddk_group_layout(headers, group_header)
    rows = [
        _core_source_row(headers, [
            "400", "10", "1",
            "200; 201", "Sterile and nonsterile", "WHO-GMP", "Manufacture",
            "", "Independent laboratory scope", "GLP", "",
            "", "", "", "",
            "", "", "", "GDP distribution only",
        ], 7),
        _core_source_row(headers, [
            "401", "", "",
            "", "", "", "",
            "", "", "", "",
            "", "", "", "",
            "", "", "", "",
        ], 8),
    ]
    snapshot = {
        "db.dkkd": rows,
        "db.cty": [{"ID": "1"}],
        "db.cso": [{"ID": "10", "ID CTY": "1"}],
        "db.cc": [
            {"ID": "200", "ID CƠ SỞ": "10", "ID CTY": "1", "LOẠI CC": "GMP", "ID DDK": "400"},
            {"ID": "201", "ID CƠ SỞ": "10", "ID CTY": "1", "LOẠI CC": "GMP", "ID DDK": "400"},
        ],
    }
    result = audit(
        snapshot,
        source_sha256="a" * 64,
        header_evidence={"id_cc_columns": plans},
    )
    return result


def contract():
    return {
        "confirmation_source": "user_review_of_anomaly_report",
        "by_sheet": {"db.dkkd": {"row_count": 1}},
        "rows": [{
            "source_sheet": "db.dkkd", "source_row_key": "401",
            "source_row_number": 8, "legacy_row_id": "401",
            "classification": "confirmed_blanked_row",
            "migration_action": "exclude_from_business_import",
            "confirmation_source": "user_review_of_anomaly_report",
        }],
    }


def test_complete_source_manifest_preserves_group_without_certificate():
    out = build_group_review_manifest(fixture(), approved_exclusions=contract())
    assert out["approval_status"] == "SOURCE_REVIEW_ONLY_NOT_APPROVED"
    assert out["approved_exclusion_reconciliation"] == "EXACT_BY_PHYSICAL_ROW_AND_DDK_ID"
    assert out["excluded_source_rows"] == 1
    assert len(out["records"]) == 8
    assert out["metrics"]["source_cell_count"] == 32
    assert out["metrics"]["candidate_token_count"] == 2
    role = {(r["source_row_number"], r["source_group"]): r for r in out["records"]}
    gmp = role[(7, "GMP")]
    assert [c["legacy_certificate_id"] for c in gmp["reference_evidence"]] == [200, 201]
    assert gmp["status"] == "SOURCE_OBSERVED_NOT_APPROVED"
    assert len(gmp["source_values_sha256"]) == 64
    glp = role[(7, "GLP")]
    assert glp["has_companion_without_id_cc"]
    assert glp["status"] == "SOURCE_REVIEW_REQUIRED"
    assert glp["review_flags"] == ["COMPANION_WITHOUT_ID_CC"]
    gdp = role[(7, "GDP")]
    assert gdp["has_companion_without_id_cc"] and not gdp["reference_evidence"]
    assert role[(8, "GMP")]["status"] == "CONFIRMED_BLANKED_SOURCE_ROW"
    assert all(r["approval_status"] == "NOT_APPROVED" for r in out["records"])
    assert all("business_eligibility_version_id" not in r for r in out["records"])


def test_missing_approval_contract_never_claims_effective_source_population():
    out = build_group_review_manifest(fixture())
    assert out["approved_exclusion_reconciliation"] == "NOT_CHECKED"
    assert out["excluded_source_rows"] is None
    assert out["metrics"]["group_count"] == 8


def test_exact_token_content_and_indices_are_integrity_gates():
    original = fixture()
    tampered = copy.deepcopy(original)
    tampered["candidates"][0]["raw_fk_token"] = "999"
    with pytest.raises(MissingPhysicalEvidence, match="lost or reinterpreted"):
        build_group_review_manifest(tampered)
    tampered = copy.deepcopy(original)
    tampered["candidates"][0]["source_token_index"] = 2
    with pytest.raises(MissingPhysicalEvidence, match="Duplicate or absent physical token"):
        build_group_review_manifest(tampered)
    tampered = copy.deepcopy(original)
    tampered["candidates"].pop()
    tampered["candidate_count"] -= 1
    with pytest.raises(MissingPhysicalEvidence, match="token count"):
        build_group_review_manifest(tampered)


def test_source_group_field_mutation_or_unverified_header_blocks():
    original = fixture()
    tampered = copy.deepcopy(original)
    tampered["grouped_source_rows"][0]["groups"][3]["fields"]["business_activity"]["excel_column"] = 20
    with pytest.raises(MissingPhysicalEvidence, match="cell identity"):
        build_group_review_manifest(tampered)
    tampered = copy.deepcopy(original)
    tampered["header_evidence"]["id_cc_columns"][0]["observed_group_header"] = "GDP"
    with pytest.raises(MissingPhysicalEvidence, match="Duplicate or invalid"):
        build_group_review_manifest(tampered)
    tampered = copy.deepcopy(original)
    tampered["grouped_source_status"] = "UNAVAILABLE_REQUIRES_PHYSICAL_HEADER_BAND"
    with pytest.raises(MissingPhysicalEvidence, match="not physically verified"):
        build_group_review_manifest(tampered)


def test_exclusion_contract_cannot_mask_populated_group_or_stale_identity():
    data = fixture()
    evidence = copy.deepcopy(data)
    evidence["grouped_source_rows"][1]["groups"][0]["fields"]["certificate_scope"]["raw_value"] = "unsafe restored"
    with pytest.raises(MissingPhysicalEvidence, match="live grouped source data"):
        build_group_review_manifest(evidence, approved_exclusions=contract())
    stale = contract()
    stale["rows"][0]["legacy_row_id"] = "999"
    with pytest.raises(MissingPhysicalEvidence, match="Malformed"):
        build_group_review_manifest(data, approved_exclusions=stale)
    stale = contract()
    stale["rows"][0]["source_row_number"] = 99
    with pytest.raises(MissingPhysicalEvidence, match="absent physical"):
        build_group_review_manifest(data, approved_exclusions=stale)


def test_audited_cross_site_and_company_conflict_become_flags_not_corrections():
    data = fixture()
    damaged = copy.deepcopy(data)
    damaged["candidates"][0]["classification"] = "CROSS_SITE"
    damaged["candidates"][0]["ddk_company_vs_site"] = "MISMATCH"
    damaged["candidates"][0]["reverse_relation"] = "REVERSE_CONFLICTS"
    record = next(r for r in build_group_review_manifest(damaged)["records"]
                  if r["source_row_number"] == 7 and r["source_group"] == "GMP")
    assert record["status"] == "SOURCE_REVIEW_REQUIRED"
    assert "SITE_OR_REFERENCE_REVIEW" in record["review_flags"]
    assert "COMPANY_OWNER_REVIEW" in record["review_flags"]
    assert "REVERSE_EVIDENCE_REVIEW" in record["review_flags"]
    assert "canonical_link" not in record


def test_source_reference_cannot_claim_another_ddk_row_or_unproven_group():
    data = fixture()
    tampered = copy.deepcopy(data)
    tampered["candidates"][0]["ddk_legacy_id"] = 777
    with pytest.raises(MissingPhysicalEvidence, match="Candidate DDK identity"):
        build_group_review_manifest(tampered)
    tampered = copy.deepcopy(data)
    tampered["candidates"][0]["observed_group_header"] = None
    with pytest.raises(MissingPhysicalEvidence, match="Candidate GxP heading"):
        build_group_review_manifest(tampered)


def test_review_manifest_preserves_raw_scope_standard_activity_and_individual_hashes():
    report = fixture()
    group = report["grouped_source_rows"][0]["groups"][0]
    group["fields"]["certificate_scope"]["raw_value"] = "Sterile; thuốc tiêm\nSản xuất (β-lactam)"
    group["fields"]["applicable_standard"]["raw_value"] = "WHO-GMP 2026"
    group["fields"]["business_activity"]["raw_value"] = "Sản xuất; đóng gói thuốc"
    records = build_group_review_manifest(report)["records"]
    gmp = next(r for r in records if r["source_row_number"] == 7 and r["source_group"] == "GMP")
    for name, expected in (
        ("id_cc", "200; 201"),
        ("certificate_scope", "Sterile; thuốc tiêm\nSản xuất (β-lactam)"),
        ("applicable_standard", "WHO-GMP 2026"),
        ("business_activity", "Sản xuất; đóng gói thuốc"),
    ):
        field = gmp["source_fields"][name]
        assert field["raw_value"] == expected
        assert field["raw_value_sha256"] == hashlib.sha256(expected.encode("utf-8")).hexdigest()
    glp = next(r for r in records if r["source_row_number"] == 7 and r["source_group"] == "GLP")
    assert glp["source_fields"]["id_cc"]["raw_value"] == ""
    assert glp["source_fields"]["certificate_scope"]["raw_value"] == "Independent laboratory scope"
    assert all("source_fields" in r for r in records)


def test_missing_reference_type_or_company_reviewed_not_claimed_resolved():
    data = fixture()
    data["candidates"][0]["certificate_type_vs_source_header"] = "UNVERIFIED"
    data["candidates"][0]["certificate_company_vs_ddk"] = "UNRESOLVED"
    manifest = build_group_review_manifest(data)
    gmp = next(r for r in manifest["records"] if r["source_row_number"] == 7 and r["source_group"] == "GMP")
    assert gmp["status"] == "SOURCE_REVIEW_REQUIRED"
    assert "CERTIFICATE_TYPE_REVIEW" in gmp["review_flags"]
    assert "COMPANY_OWNER_REVIEW" in gmp["review_flags"]

    data = fixture()
    data["candidates"][0]["classification"] = "UNSUPPORTED"
    with pytest.raises(MissingPhysicalEvidence, match="Unknown source reference classification"):
        build_group_review_manifest(data)


def test_malformed_input_evidence_is_rejected_with_source_error():
    data = fixture()
    for bad in (None, [], "invalid"):
        malformed = copy.deepcopy(data)
        malformed["header_evidence"] = bad
        with pytest.raises(MissingPhysicalEvidence, match="Missing original physical header"):
            build_group_review_manifest(malformed)
    malformed = copy.deepcopy(data)
    malformed["candidates"][0] = None
    with pytest.raises(MissingPhysicalEvidence, match="Malformed source candidate"):
        build_group_review_manifest(malformed)
    malformed = copy.deepcopy(data)
    malformed["grouped_source_rows"][0] = None
    with pytest.raises(MissingPhysicalEvidence, match="Malformed physical source row"):
        build_group_review_manifest(malformed)


def test_cli_never_overwrites_input_or_preexisting_review(tmp_path, monkeypatch):
    source = tmp_path / "physical_source.json"
    source.write_text(json.dumps(fixture()), encoding="utf-8")
    out = tmp_path / "review.json"
    monkeypatch.setattr(sys, "argv", [
        "ddk_group_evidence_review", "--audit-json", str(source), "--output", str(out),
    ])
    assert main() == 0
    first_bytes = out.read_bytes()
    assert first_bytes and json.loads(first_bytes)["approval_status"] == "SOURCE_REVIEW_ONLY_NOT_APPROVED"
    with pytest.raises(SystemExit) as err:
        main()
    assert err.value.code == 2
    assert out.read_bytes() == first_bytes
    monkeypatch.setattr(sys, "argv", [
        "ddk_group_evidence_review", "--audit-json", str(source), "--output", str(source),
    ])
    original_bytes = source.read_bytes()
    with pytest.raises(SystemExit) as err:
        main()
    assert err.value.code == 2
    assert source.read_bytes() == original_bytes


def test_cli_cannot_overwrite_exclusion_contract(tmp_path, monkeypatch):
    source = tmp_path / "physical_source.json"
    approved = tmp_path / "approved_exclusions.json"
    source.write_text(json.dumps(fixture()), encoding="utf-8")
    approved.write_text(json.dumps(contract()), encoding="utf-8")
    original_bytes = approved.read_bytes()
    monkeypatch.setattr(sys, "argv", [
        "ddk_group_evidence_review", "--audit-json", str(source),
        "--approved-exclusions-json", str(approved), "--output", str(approved),
    ])
    with pytest.raises(SystemExit) as err:
        main()
    assert err.value.code == 2
    assert approved.read_bytes() == original_bytes
