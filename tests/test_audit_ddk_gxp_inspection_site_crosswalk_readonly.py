"""Single code-only source Case Site crosswalk never promotes NAS names to identity."""
from __future__ import annotations

from hashlib import sha256
import json
from types import SimpleNamespace as Row

import pytest

import tools.audit_ddk_gxp_inspection_site_crosswalk_readonly as owner


def _target():
    return {
        "case_id": "case-a",
        "source_site_legacy_id": 111,
        "observed_site_legacy_id_unverified": 222,
        "inspection_code": "CODE-1",
        "source_year": 2025,
    }


def _rows(*, observed=True, duplicate_code=False, same_company=False):
    source_site = Row(id="site-a", legacy_site_id=111, company_id="company-a")
    second = Row(id="site-b", legacy_site_id=222,
                 company_id="company-a" if same_company else "company-b") if observed else None
    source_case = Row(id="case-a", site_id="site-a", legacy_inspection_code="CODE-1")
    others = [Row(id="case-b", site_id="site-b",
                  legacy_inspection_code="CODE-1")] if duplicate_code else []
    anchor = Row(case_id="case-a", source_sheet="db.ktra", source_row=20,
                 source_hash="a" * 64, source_version="b" * 64)
    return source_site, second, source_case, anchor, [source_case, *others]


def test_other_imported_site_does_not_reassign_case_or_approve():
    src, observed, case, anchor, same_code = _rows()
    result = owner.evaluate_canonical_projection(
        target=_target(), source_site=src, observed_site=observed,
        source_case=case, source_anchor=anchor, same_code_cases=same_code,
    )
    assert result["observed_site_classification"] == "OBSERVED_ID_EXISTS_AS_DIFFERENT_IMPORTED_SITE"
    assert result["observed_site_same_company_as_source"] is False
    assert result["other_case_with_observed_site_and_same_code_count"] == 0
    assert result["observed_id_physically_verified_in_db_cso"] is False
    assert result["source_case_physically_reverified_in_db_ktra"] is False
    assert result["approval_status"] == "NOT_APPROVED"
    assert result["database_writes"] == result["storage_writes"] == result["canonical_links_created"] == 0
    safe = {k: v for k, v in result.items()
            if k not in {"private_identity_observations", "limitations"}}
    assert "111" not in str(safe)
    assert "222" not in str(safe)
    assert "CODE-1" not in str(safe)


def test_observed_numeric_id_absent_from_imported_site_directory():
    src, _, case, anchor, same_code = _rows(observed=False)
    result = owner.evaluate_canonical_projection(
        target=_target(), source_site=src, observed_site=None,
        source_case=case, source_anchor=anchor, same_code_cases=same_code,
    )
    assert result["observed_site_classification"] == "OBSERVED_ID_ABSENT_IN_IMPORTED_SITE_DIRECTORY"
    assert result["observed_site_same_company_as_source"] is None
    assert result["private_identity_observations"]["observed_site_canonical_id_unverified"] is None


def test_duplicate_case_code_with_other_site_is_not_binding_evidence():
    src, observed, case, anchor, cases = _rows(duplicate_code=True, same_company=True)
    report = owner.evaluate_canonical_projection(
        target=_target(), source_site=src, observed_site=observed,
        source_case=case, source_anchor=anchor, same_code_cases=cases,
    )
    assert report["matching_inspection_code_case_count"] == 2
    assert report["other_case_with_observed_site_and_same_code_count"] == 1
    assert report["observed_site_same_company_as_source"] is True
    assert report["approval_status"] == "NOT_APPROVED"


@pytest.mark.parametrize("change", ["wrong_original_site", "wrong_case_site",
                                    "wrong_case_code", "wrong_anchor", "huge_code_population"])
def test_canonical_projection_rejects_identity_drift(change):
    src, observed, case, anchor, cases = _rows()
    if change == "wrong_original_site":
        src.legacy_site_id = 999
    elif change == "wrong_case_site":
        case.site_id = "site-b"
    elif change == "wrong_case_code":
        case.legacy_inspection_code = "OTHER-CODE"
    elif change == "wrong_anchor":
        anchor.source_sheet = "db.cc"
    else:
        cases += [Row(id=f"extra-{i}", site_id="site-b", legacy_inspection_code="CODE-1")
                  for i in range(101)]
    with pytest.raises(owner.InspectionSiteCrosswalkBlocked):
        owner.evaluate_canonical_projection(
            target=_target(), source_site=src, observed_site=observed,
            source_case=case, source_anchor=anchor, same_code_cases=cases,
        )


def _source_bundle(monkeypatch):
    dossier = {"audit": "source"}
    queue = {"same": "original"}
    monkeypatch.setattr(owner, "build_review_queue", lambda _: queue)
    monkeypatch.setattr(owner, "compare_private_case_observations",
                        lambda *args: {"case_parents_compared": 6,
                                       "resolved_case_regressions": 0,
                                       "year_specific_observations_checked": 9})
    cases = [
        {"parent_id": f"case-{i}", "site_legacy_id": 111 if i == 0 else 10+i,
         "inspection_legacy_code": "CODE-1" if i == 0 else f"CODE-{i}"}
        for i in range(6)
    ]
    monkeypatch.setattr(owner, "verified_lookup_targets",
                        lambda *args: ([{} for _ in range(8)], cases))
    rows = []
    observations = []
    for i in range(6):
        years = [2025, 2026] if i == 2 else [2025]
        final = "NOT_FOUND" if i in (0,1,2) else "RESOLVED"
        rows.append({
            "originating_case_id": f"case-{i}", "final_status": final,
            "year_specific_observations": [
                {"source_year": y, "status": "not_found" if final == "NOT_FOUND" else "resolved",
                 "candidate_count": 0 if final == "NOT_FOUND" else 1}
                for y in years
            ],
        })
        if final == "NOT_FOUND":
            for y in years:
                observations.append({"originating_case_id": f"case-{i}", "source_year": y,
                                     "classification": "INSPECTION_CODE_ONLY" if i == 0
                                     else "NO_EXACT_TOKEN"})
    def data(d): return json.dumps(d, sort_keys=True).encode()
    ready_bytes = data({"source": True})
    full_bytes = data({"original": True})
    dual_bytes = data({"private_case_observations": rows})
    rh, fh, dh = [sha256(v).hexdigest() for v in (ready_bytes, full_bytes, dual_bytes)]
    prior = {
        "schema": "GXP_DDK_MISSING_CASE_YEAR_ROOT_SHAPE_READONLY_V1",
        "status": "ORIGINAL_NOT_FOUND_YEAR_ROOT_METADATA_CLASSIFIED",
        "approval_status": "NOT_APPROVED",
        "source_readiness_sha256": rh, "source_full_smb_sha256": fh,
        "source_dual_year_smb_sha256": dh, "missing_case_parents_checked": 3,
        "source_year_observations_checked": 4,
        "classification_counts": {"NO_EXACT_TOKEN": 3, "INSPECTION_CODE_ONLY": 1},
        "database_connected": False, "database_writes": 0,
        "storage_writes": 0, "canonical_links_created": 0,
        "private_case_year_metadata_observations": observations,
    }
    prior_bytes = data(prior)
    marker = {
        "schema": "GXP_DDK_CODE_ONLY_INSPECTION_SITE_MARKER_READONLY_V1",
        "status": "ONE_SOURCE_BOUND_CASE_YEAR_CODE_ONLY_METADATA_CLASSIFIED",
        "approval_status": "NOT_APPROVED",
        "source_readiness_sha256": rh, "source_full_smb_sha256": fh,
        "source_dual_year_smb_sha256": dh,
        "source_prior_metadata_sha256": sha256(prior_bytes).hexdigest(),
        "source_case_year_observations_checked": 1,
        "source_year_roots_checked": 1,
        "code_matching_directories_checked": 1,
        "classification_counts": {"OTHER_NUMERIC_ID_TOKEN": 1},
        "database_connected": False, "database_writes": 0, "storage_writes": 0,
        "canonical_links_created": 0,
        "source_case_parent_id_private": "case-0",
        "source_year_private": 2025,
        "source_site_legacy_id_private": 111,
        "private_folder_token_observations": [
            {"classification": "OTHER_NUMERIC_ID_TOKEN",
             "observed_numeric_site_ids_unverified": [222]},
        ],
    }
    return dossier, queue, ready_bytes, full_bytes, dual_bytes, prior_bytes, marker


def test_complete_source_bound_site_token_proof(monkeypatch):
    d, q, a, b, c, p, marker = _source_bundle(monkeypatch)
    result = owner.extract_source_bound_marker(d, q, a, b, c, p, json.dumps(marker).encode())
    assert result["case_id"] == "case-0"
    assert result["source_site_legacy_id"] == 111
    assert result["observed_site_legacy_id_unverified"] == 222
    assert result["source_year"] == 2025


@pytest.mark.parametrize("drift", ["observed_equals_source", "marker_sha", "source_case",
                                   "no_provenance", "extra_observed_id", "wrong_count"])
def test_source_bound_proof_fails_closed_on_private_lineage_drift(monkeypatch, drift):
    d, q, a, b, c, p, marker = _source_bundle(monkeypatch)
    if drift == "observed_equals_source":
        marker["private_folder_token_observations"][0]["observed_numeric_site_ids_unverified"] = [111]
    elif drift == "marker_sha":
        marker["source_prior_metadata_sha256"] = "0" * 64
    elif drift == "source_case":
        marker["source_case_parent_id_private"] = "case-1"
    elif drift == "no_provenance":
        marker["classification_counts"] = {"NO_ID_MARKER": 1}
    elif drift == "extra_observed_id":
        marker["private_folder_token_observations"][0]["observed_numeric_site_ids_unverified"] = [222, 333]
    else:
        marker["code_matching_directories_checked"] = 2
    with pytest.raises(owner.InspectionSiteCrosswalkBlocked):
        owner.extract_source_bound_marker(d, q, a, b, c, p, json.dumps(marker).encode())



def test_source_bound_private_excel_request_uses_one_immutable_case_row():
    src, observed, case, anchor, rows = _rows(same_company=True)
    case.legacy_inspection_id = 345
    case.legacy_inspection_code = "KT-345-GMP"
    case.gxp_type = "GMP"
    target = {**_target(), "inspection_code": "KT-345-GMP"}
    from tools.audit_ddk_inspection_physical_source_readonly import REQUEST_SCHEMA
    result = owner.prepare_physical_workbook_request(
        target=target, source_case=case, source_site=src,
        observed_site=observed, source_anchor=anchor,
        imported_company_legacy_id=19, workbook_sha256="a" * 64,
    )
    assert result["schema"] == REQUEST_SCHEMA
    assert result["legacy_inspection_id"] == 345
    assert result["source_case_row_number"] == 20
    assert result["source_site_legacy_id"] == 111
    assert result["observed_site_legacy_id_unverified"] == 222
    assert result["approval_status"] == "NOT_APPROVED"


@pytest.mark.parametrize("fault", [
    "wrong_site_owner", "same_site", "wrong_case_code", "wrong_gxp",
    "missing_original_row", "missing_legacy_inspection_id", "company_divergence",
])
def test_private_excel_request_rejects_imported_identity_drift(fault):
    src, observed, case, anchor, _ = _rows(same_company=True)
    case.legacy_inspection_id = 345
    case.legacy_inspection_code = "KT-345-GMP"
    case.gxp_type = "GMP"
    target = {**_target(), "inspection_code": "KT-345-GMP"}
    if fault == "wrong_site_owner":
        case.site_id = observed.id
    elif fault == "same_site":
        observed.id = src.id
    elif fault == "wrong_case_code":
        case.legacy_inspection_code = "KT-777-GMP"
    elif fault == "wrong_gxp":
        case.gxp_type = "GSP"
    elif fault == "missing_original_row":
        anchor.source_row = 0
    elif fault == "missing_legacy_inspection_id":
        case.legacy_inspection_id = None
    else:
        observed.company_id = "company-different"
    with pytest.raises(owner.InspectionSiteCrosswalkBlocked):
        owner.prepare_physical_workbook_request(
            target=target, source_case=case, source_site=src,
            observed_site=observed, source_anchor=anchor,
            imported_company_legacy_id=19, workbook_sha256="a" * 64,
        )
