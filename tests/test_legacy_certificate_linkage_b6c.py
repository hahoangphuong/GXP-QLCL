from __future__ import annotations

from backend.app.domain.legacy_certificate_linkage import (
    build_canonical_certificate_linkage_comparison,
    build_certificate_linkage_source_plan,
    parse_legacy_certificate_reference,
)


def _snapshot(ktra_rows, cc_rows):
    def row(number, cells):
        return {"source_row_number": number, "cells": [{"column_ordinal": key, "raw_value": value} for key, value in cells.items()]}
    return {"sheets": [
        {"sheet_name": "db.ktra", "raw_rows": [row(4, {1: "ID", 2: "ID CƠ SỞ", 3: "LOẠI KT", 4: "ID CC GPs"}), *[row(index + 5, values) for index, values in enumerate(ktra_rows)]]},
        {"sheet_name": "db.cc", "raw_rows": [row(4, {1: "ID", 2: "ID ĐỢT KTRA", 3: "ID CƠ SỞ", 4: "LOẠI CC", 5: "Mã số CC"}), *[row(index + 5, values) for index, values in enumerate(cc_rows)]]},
    ]}


def test_parser_is_literal_and_fails_closed_for_composite_or_decimal_text():
    assert parse_legacy_certificate_reference(12.0)["legacy_certificate_id"] == 12
    assert parse_legacy_certificate_reference(" 12 ")["legacy_certificate_id"] == 12
    assert parse_legacy_certificate_reference("12;13")["state"] == "SOURCE_MULTI_ID"
    assert parse_legacy_certificate_reference("12.0")["state"] == "SOURCE_UNRESOLVED"
    assert parse_legacy_certificate_reference("-")["state"] == "SOURCE_MISSING"


def test_source_plan_distinguishes_exact_context_incomplete_and_duplicate_reference_evidence():
    snapshot = _snapshot(
        [{1: 10.0, 2: 7.0, 3: "GMP", 4: 20.0}, {1: 11.0, 2: 7.0, 3: "GLP", 4: 20.0}, {1: 12.0, 2: 7.0, 3: "GMP", 4: "12;13"}],
        [{1: 20.0, 2: 10.0, 3: 7.0, 4: "GMP", 5: "CERT"}],
    )
    plan = build_certificate_linkage_source_plan(snapshot, snapshot_sha256="snapshot")
    assert plan["source_morphology"]["observed_cardinality"] == "0..N_PROVEN"
    assert plan["cross_source_classification_counts"] == {"EXACT_SOURCE_MATCH": 1, "SOURCE_MULTI_ID": 1, "SOURCE_TYPE_MISMATCH": 1}
    assert plan["mismatch_dimension_counts"] == {"GXP_TYPE": 1, "INSPECTION_OWNER": 1}
    assert plan["records"][0]["duplicate_source_certificate_reference"] is True


def test_source_plan_keeps_zero_to_one_cardinality_when_no_multiple_source_cell_exists():
    snapshot = _snapshot([{1: 10.0, 2: 7.0, 3: "GMP", 4: 20.0}], [{1: 20.0, 2: 10.0, 3: 7.0, 4: "GMP", 5: "CERT"}])
    plan = build_certificate_linkage_source_plan(snapshot, snapshot_sha256="snapshot")
    assert plan["source_morphology"]["observed_cardinality"] == "0..1_OBSERVED"


def test_source_plan_prioritizes_incomplete_certificate_context_over_type_mismatch():
    snapshot = _snapshot([{1: 10.0, 2: 7.0, 3: "GMP", 4: 20.0}], [{1: 20.0, 2: None, 3: None, 4: None, 5: "CERT"}])
    plan = build_certificate_linkage_source_plan(snapshot, snapshot_sha256="snapshot")
    assert plan["cross_source_classification_counts"] == {"SOURCE_CERTIFICATE_CONTEXT_INCOMPLETE": 1}
    assert plan["records"][0]["source_mismatch_fields"] == ["INSPECTION_OWNER", "SITE", "GXP_TYPE", "CERTIFICATE_CONTEXT_INCOMPLETE"]
    assert plan["mismatch_dimension_counts"] == {"CERTIFICATE_CONTEXT_INCOMPLETE": 1, "GXP_TYPE": 1, "INSPECTION_OWNER": 1, "SITE": 1}


def test_canonical_comparison_only_marks_unlinked_exact_owner_as_future_candidate():
    snapshot = _snapshot([{1: 10.0, 2: 7.0, 3: "GMP", 4: 20.0}], [{1: 20.0, 2: 10.0, 3: 7.0, 4: "GMP", 5: "CERT"}])
    source = build_certificate_linkage_source_plan(snapshot, snapshot_sha256="snapshot")
    cases = [{"id": "case-10", "legacy_inspection_id": 10, "site_id": "site-7", "gxp_type": "GMP"}]
    sites = [{"id": "site-7", "legacy_site_id": 7}]
    missing_link = build_canonical_certificate_linkage_comparison(source, cases=cases, sites=sites, certificates=[{"id": "cert-20", "legacy_certificate_id": 20, "case_id": None, "site_id": "site-7", "certificate_type": "GMP"}])
    assert missing_link["classification_counts"] == {"MISSING_CASE_LINK": 1}
    assert missing_link["writability_counts"]["SAFE_LINK_CANDIDATE"] == 1
    assert missing_link["records"][0]["resolved_canonical_site_id"] == "site-7"
    wrong_link = build_canonical_certificate_linkage_comparison(source, cases=cases, sites=sites, certificates=[{"id": "cert-20", "legacy_certificate_id": 20, "case_id": "other", "site_id": "site-7", "certificate_type": "GMP"}])
    assert wrong_link["classification_counts"] == {"WRONG_CASE_LINK": 1}
    assert wrong_link["writability_counts"]["SAFE_LINK_CANDIDATE"] == 0


def test_canonical_comparison_requires_source_site_lineage_not_just_matching_case_and_certificate_sites():
    snapshot = _snapshot([{1: 10.0, 2: 7.0, 3: "GMP", 4: 20.0}], [{1: 20.0, 2: 10.0, 3: 7.0, 4: "GMP", 5: "CERT"}])
    source = build_certificate_linkage_source_plan(snapshot, snapshot_sha256="snapshot")
    cases = [{"id": "case-10", "legacy_inspection_id": 10, "site_id": "site-7", "gxp_type": "GMP"}]
    certificates = [{"id": "cert-20", "legacy_certificate_id": 20, "case_id": None, "site_id": "site-7", "certificate_type": "GMP"}]
    missing_site = build_canonical_certificate_linkage_comparison(source, cases=cases, sites=[], certificates=certificates)
    assert missing_site["classification_counts"] == {"SOURCE_SITE_CANONICAL_NOT_FOUND": 1}
    duplicate_site = build_canonical_certificate_linkage_comparison(source, cases=cases, sites=[{"id": "site-7a", "legacy_site_id": 7}, {"id": "site-7b", "legacy_site_id": 7}], certificates=certificates)
    assert duplicate_site["classification_counts"] == {"SOURCE_SITE_CANONICAL_DUPLICATE": 1}
    case_site_conflict = build_canonical_certificate_linkage_comparison(source, cases=[{**cases[0], "site_id": "other"}], sites=[{"id": "site-7", "legacy_site_id": 7}], certificates=certificates)
    assert case_site_conflict["classification_counts"] == {"CASE_SITE_CONFLICT": 1}
    certificate_site_conflict = build_canonical_certificate_linkage_comparison(source, cases=cases, sites=[{"id": "site-7", "legacy_site_id": 7}], certificates=[{**certificates[0], "site_id": "other"}])
    assert certificate_site_conflict["classification_counts"] == {"CERTIFICATE_SITE_CONFLICT": 1}


def test_canonical_comparison_never_rescues_a_nonexact_source_record():
    snapshot = _snapshot([{1: 10.0, 2: 7.0, 3: "GMP", 4: 20.0}], [{1: 20.0, 2: 11.0, 3: 7.0, 4: "GMP", 5: "CERT"}])
    source = build_certificate_linkage_source_plan(snapshot, snapshot_sha256="snapshot")
    comparison = build_canonical_certificate_linkage_comparison(
        source,
        cases=[{"id": "case-10", "legacy_inspection_id": 10, "site_id": "site-7", "gxp_type": "GMP"}],
        sites=[{"id": "site-7", "legacy_site_id": 7}],
        certificates=[{"id": "cert-20", "legacy_certificate_id": 20, "case_id": None, "site_id": "site-7", "certificate_type": "GMP"}],
    )
    assert comparison["classification_counts"] == {"SOURCE_UNRESOLVED": 1}
    assert comparison["writability_counts"]["SAFE_LINK_CANDIDATE"] == 0
