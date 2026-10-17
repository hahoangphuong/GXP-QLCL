"""Physical Excel witness: strict ID/FK assertions, without live Excel/VM."""
import pytest

from tools.audit_ddk_inspection_physical_source_readonly import (
    REQUEST_SCHEMA, PhysicalSourceBlocked, _column, evaluate_physical_rows,
)


def request():
    return {
        "schema": REQUEST_SCHEMA,
        "approval_status": "NOT_APPROVED",
        "source_workbook_sha256": "a" * 64,
        "source_site_legacy_id": 110,
        "observed_site_legacy_id_unverified": 111,
        "legacy_inspection_id": 300,
        "source_case_row_number": 28,
        "source_company_legacy_id": 15,
        "inspection_code": "KT-300-GMP",
    }


def rows():
    return ({
        110: {"ID": "110", "company_legacy_id_ref": "15", "excel_row": 3},
        111: {"ID": "111", "company_legacy_id_ref": "15", "excel_row": 4},
    }, {
        300: {"ID": "300", "site_legacy_id_ref": "110",
              "inspection_gxp_type": "GMP", "excel_row": 28},
    })


def test_exact_physical_source_case_site_and_both_sites_same_company_is_unapproved():
    sites, cases = rows()
    report = evaluate_physical_rows(request(), sites, cases)
    assert report["status"] == "SOURCE_ROW_AND_SITE_MATCH_IMPORTED_CASE"
    assert report["source_case_site_fk_matches_imported"] is True
    assert report["source_case_inspection_code_matches_imported"] is True
    assert report["physical_both_sites_same_company"] is True
    assert report["observed_nas_site_id_approved_as_case_owner"] is False
    assert report["approval_status"] == "NOT_APPROVED"
    assert report["database_writes"] == report["storage_writes"] == report["canonical_links_created"] == 0
    assert "110" not in str(report) and "111" not in str(report)
    assert "300" not in str(report)


@pytest.mark.parametrize("change,field", [
    ("case_site", "source_case_site_fk_matches_imported"),
    ("case_code", "source_case_inspection_code_matches_imported"),
    ("source_row", "source_case_excel_row_matches_anchor"),
    ("company_split", "physical_both_sites_same_company"),
    ("company_drift", "physical_site_company_matches_imported"),
])
def test_physical_source_discrepancy_never_becomes_approval(change, field):
    sites, cases = rows()
    if change == "case_site":
        cases[300]["site_legacy_id_ref"] = "111"
    elif change == "case_code":
        cases[300]["inspection_gxp_type"] = "GLP"
    elif change == "source_row":
        cases[300]["excel_row"] = 29
    elif change == "company_split":
        sites[111]["company_legacy_id_ref"] = "17"
    else:
        sites[110]["company_legacy_id_ref"] = "19"
    report = evaluate_physical_rows(request(), sites, cases)
    assert report["status"] == "SOURCE_WORKBOOK_CONFLICT_REQUIRES_OWNER_AUDIT"
    assert report[field] is False
    assert report["approval_status"] == "NOT_APPROVED"


@pytest.mark.parametrize("change", ["same_site", "unapproved", "missing_case", "missing_site",
                                    "bad_request", "ambiguous_case_population", "wrong_id_cell"])
def test_incomplete_source_identity_blocks(change):
    req = request()
    sites, cases = rows()
    if change == "same_site":
        req["observed_site_legacy_id_unverified"] = 110
    elif change == "unapproved":
        req["approval_status"] = "APPROVED"
    elif change == "missing_case":
        cases = {}
    elif change == "missing_site":
        sites.pop(111)
    elif change == "bad_request":
        req["source_workbook_sha256"] = "not a hash"
    elif change == "ambiguous_case_population":
        cases[301] = dict(cases[300])
    else:
        cases[300]["ID"] = "999"
    with pytest.raises(PhysicalSourceBlocked):
        evaluate_physical_rows(req, sites, cases)


def test_physical_column_binding_fails_on_duplicate_and_absent_headers():
    assert _column(["ID", "ID CƠ SỞ", "LOẠI KT"], "site_legacy_id_ref") == 2
    with pytest.raises(PhysicalSourceBlocked):
        _column(["ID", "ID CƠ SỞ", "ID CƠ SỞ"], "site_legacy_id_ref")
    with pytest.raises(PhysicalSourceBlocked):
        _column(["ID", "UNKNOWN"], "site_legacy_id_ref")
