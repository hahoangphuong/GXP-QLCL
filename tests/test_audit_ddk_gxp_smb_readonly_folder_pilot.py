"""SMB pilot: original-source identity preservation and resolver-only invocation."""
from __future__ import annotations

from dataclasses import dataclass
import json
import pytest
from backend.app.db.enums import StorageResolutionStatus
from backend.app.storage.smb import SmbStorageService
from tools.audit_ddk_gxp_smb_readonly_folder_pilot import (
    SmbProbeBlocked, verified_lookup_targets, run_bounded_probes,
)


def _queue_and_readiness():
    review = {
        "review_key": "SOURCE_TOKEN:ref1",
        "original_exception_evidence": {
            "ddk_site_id": "ddk-site", "ddk_company_id": "company1",
            "observed_certificate_id": "cert1",
            "certificate_site_id": "cert-site",
            "certificate_case_id": "case1",
            "case_site_id": "case-site",
        },
    }
    company_review = {
        "review_key": "DDK_COMPANY:10",
        "original_company_exception_evidence": {
            "ddk_site_id": "ddk-site", "ddk_company_id": "company1",
            "canonical_business_eligibility_certificate_id": "ddk1",
        },
    }
    queue = {
        "status": "PRIVATE_REVIEW_ONLY_NOT_APPROVED",
        "link_approval": "NOT_APPROVED",
        "manual_review_status": "PENDING_INDEPENDENT_EVIDENCE",
        "source_token_reviews": [review],
        "ddk_company_reviews": [company_review],
    }
    ddk = {
        "canonical_id": "ddk1", "site_id": "ddk-site", "site_legacy_id": 14,
        "lookup_input_classification": "DDK_SITE_IDENTITY_INPUT_AVAILABLE_UNPROBED",
    }
    case = {
        "case_id": "case1", "case_site_id": "case-site",
        "case_site_legacy_id": 27, "source_year_observed": 2026,
        "case_legacy_inspection_code": "2026-A",
        "anchor_classification": "REGISTRATION_SOURCE_YEAR_USABLE",
        "lookup_input_classification": "CASE_LOOKUP_INPUT_AVAILABLE_UNPROBED",
    }
    readiness = {
        "schema": "GXP_DDK_EXCEPTION_STORAGE_IDENTITY_READINESS_V1",
        "status": "INPUT_IDENTITIES_ONLY_NO_STORAGE_PROBE",
        "approval_status": "NOT_APPROVED",
        "database_writes": 0, "canonical_links_created": 0,
        "storage_roots_accessed": False,
        "review_records": 2,
        "unique_ddk_count": 1, "unique_originating_case_count": 1,
        "private_lookup_input_evidence": [{
            "review_key": "SOURCE_TOKEN:ref1",
            "review_status": "PENDING_INDEPENDENT_EVIDENCE",
            "link_approval": "NOT_APPROVED", "ddk": ddk,
            "certificate_reference": {
                "certificate_id": "cert1", "certificate_site_id": "cert-site",
                "folder_resolution_contract": "NOT_ASSIGNED_TO_CERTIFICATE",
            }, "originating_case_reference": case,
        }, {
            "review_key": "DDK_COMPANY:10",
            "review_status": "PENDING_INDEPENDENT_EVIDENCE",
            "link_approval": "NOT_APPROVED", "ddk": ddk,
            "certificate_reference": None, "originating_case_reference": None,
        }],
    }
    return queue, readiness


def test_exact_source_lookup_keys_with_distinct_case_site():
    queue, readiness = _queue_and_readiness()
    ddk, cases = verified_lookup_targets(queue, readiness)
    assert ddk == [{"parent_id": "ddk1", "site_legacy_id": 14}]
    assert cases == [{"parent_id": "case1", "site_legacy_id": 27,
                      "year": 2026, "inspection_legacy_code": "2026-A"}]
    assert ddk[0]["site_legacy_id"] != cases[0]["site_legacy_id"]


@pytest.mark.parametrize("mutation", ["approval", "case_site", "source_case", "certificate_folder", "duplicate", "case_year"])
def test_fails_closed_on_mutated_review_or_readiness(mutation):
    queue, readiness = _queue_and_readiness()
    if mutation == "approval":
        readiness["approval_status"] = "APPROVED"
    elif mutation == "case_site":
        readiness["private_lookup_input_evidence"][0]["originating_case_reference"]["case_site_id"] = "wrong"
    elif mutation == "source_case":
        queue["source_token_reviews"][0]["original_exception_evidence"]["certificate_case_id"] = "wrong"
    elif mutation == "certificate_folder":
        readiness["private_lookup_input_evidence"][0]["certificate_reference"]["folder_resolution_contract"] = "DERIVED"
    elif mutation == "duplicate":
        readiness["private_lookup_input_evidence"][1]["review_key"] = "SOURCE_TOKEN:ref1"
    else:
        readiness["private_lookup_input_evidence"][0]["originating_case_reference"]["source_year_observed"] = None
    with pytest.raises(SmbProbeBlocked):
        verified_lookup_targets(queue, readiness)


def test_bounded_resolution_calls_only_two_readonly_methods(monkeypatch):
    queue, readiness = _queue_and_readiness()
    ddk, cases = verified_lookup_targets(queue, readiness)
    seen = []
    # Bypass network constructor; exercise only real SmbStorageService methods
    # by overriding the two allowed read-only resolver methods on a test instance.
    storage = object.__new__(SmbStorageService)
    def fake_ddk(*, site_legacy_id):
        seen.append(("ddk",site_legacy_id))
        return type("Resolution",(),{"status":StorageResolutionStatus.RESOLVED,
                                    "candidate_count":1,"relative_path":"PRIVATE"})()
    def fake_case(*, year, site_legacy_id, inspection_legacy_code):
        seen.append(("case",year,site_legacy_id,inspection_legacy_code))
        return type("Resolution",(),{"status":StorageResolutionStatus.NOT_FOUND,
                                    "candidate_count":0,"relative_path":None})()
    monkeypatch.setattr(storage,"resolve_dkkd_folder",fake_ddk)
    monkeypatch.setattr(storage,"resolve_inspection_folder",fake_case)
    report = run_bounded_probes(storage, ddk, cases, max_ddk=1, max_cases=1)
    assert seen == [("ddk",14),("case",2026,27,"2026-A")]
    assert report["counts"] == {"DDK_RESOLVED":1,"CASE_NOT_FOUND":1}
    assert report["database_connected"] is False
    assert report["storage_writes"] == 0
    assert report["canonical_links_created"] == 0
    assert report["private_folder_observations"][0]["relative_path_private_unverified"] == "PRIVATE"
    assert "PRIVATE" not in json.dumps({k:v for k,v in report.items() if k!="private_folder_observations"})


def test_bounded_probe_rejects_unbounded_limit():
    storage=object.__new__(SmbStorageService)
    with pytest.raises(SmbProbeBlocked):
        run_bounded_probes(storage,[],[],max_ddk=9,max_cases=0)
    with pytest.raises(SmbProbeBlocked):
        run_bounded_probes(storage,[],[],max_ddk=0,max_cases=7)
