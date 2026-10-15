"""Synthetic guard regressions for db.cso-first DDK company reconciliation."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from tools import reconcile_ddk_site_owner_company_rehearsal as owner


def _fixture(monkeypatch, *, second_mismatch=False, linked=0):
    company_source = SimpleNamespace(id="company-source", legacy_company_id=101)
    company_wrong = SimpleNamespace(id="company-wrong", legacy_company_id=202)
    site = SimpleNamespace(id="site-3", legacy_site_id=3, company_id=company_source.id)
    ddk = SimpleNamespace(
        id="ddk-7", legacy_dkkd_id=7,
        site_id=site.id, company_id=company_wrong.id,
    )
    others = [
        SimpleNamespace(id=f"ddk-other-{i}", legacy_dkkd_id=1000+i,
                        site_id=site.id, company_id=company_source.id)
        for i in range(779)
    ]
    if second_mismatch:
        others[0].company_id = company_wrong.id
    review = {
        "original_company_exception_evidence": {
            "legacy_dkkd_id": 7,
            "canonical_business_eligibility_certificate_id": ddk.id,
            "ddk_site_id": site.id,
            "ddk_company_id": company_wrong.id,
            "site_owning_company_id": company_source.id,
            "site_owning_company_legacy_id": 101,
            "link_approval": "NOT_APPROVED",
            "review_status": "REQUIRES_INDEPENDENT_ADJUDICATION",
        }
    }
    queue = {
        "source_tokens_checked": 861,
        "source_exception_token_records": 8,
        "ddk_company_review_records": 1,
        "link_approval": "NOT_APPROVED",
        "ddk_company_reviews": [review],
    }
    monkeypatch.setattr(owner, "build_review_queue", lambda _: deepcopy(queue))
    class Session:
        def __init__(self):
            self.calls = 0
        def scalars(self, statement):
            self.calls += 1
            return {
                1: [ddk, *others],
                2: [site],
                3: [company_source, company_wrong],
            }[self.calls]
        def scalar(self, statement):
            self.calls += 1
            return linked if self.calls == 4 else 3120
    dossier = {"source_workbook_sha256": owner.EXPECTED_WORKBOOK_SHA256}
    return Session(), dossier, ddk, site, queue


def test_site_owner_wins_and_original_company_id_is_not_merged(monkeypatch):
    session, dossier, ddk, site, queue = _fixture(monkeypatch)
    result = owner.plan_site_owner_correction(session, dossier)
    assert result["schema"] == owner.SCHEMA
    assert result["canonical_company_mismatches"] == 1
    assert result["status"] == "NEEDS_ONE_CANONICAL_COMPANY_CORRECTION"
    assert result["private_previous_company_id"] != result["private_correct_company_id"]
    assert result["private_correct_company_id"] == site.company_id
    assert ddk.company_id == "company-wrong"
    assert result["source_workbook_changed"] is False
    assert result["case_site_changed"] is False
    assert result["certificate_site_changed"] is False
    assert result["canonical_links_created"] == 0
    assert result["approval_status_for_ddk_gxp_links"] == "NOT_APPROVED"


def test_previously_repaired_company_is_idempotently_recognized(monkeypatch):
    session, dossier, ddk, site, queue = _fixture(monkeypatch)
    ddk.company_id = site.company_id
    report = owner.plan_site_owner_correction(session, dossier)
    assert report["canonical_company_mismatches"] == 0
    assert report["status"] == "ALREADY_ALIGNED_SOURCE_CONFLICT_RETAINED"
    assert report["private_previous_company_id"] == site.company_id


def test_unapproved_extra_db_mismatch_blocks_without_changes(monkeypatch):
    session, dossier, ddk, site, queue = _fixture(
        monkeypatch, second_mismatch=True,
    )
    with pytest.raises(owner.SiteOwnerCorrectionBlocked, match="More than"):
        owner.plan_site_owner_correction(session, dossier)
    assert ddk.company_id == "company-wrong"


def test_existing_canonical_links_block_repair(monkeypatch):
    session, dossier, ddk, site, queue = _fixture(monkeypatch, linked=1)
    with pytest.raises(owner.SiteOwnerCorrectionBlocked, match="links"):
        owner.plan_site_owner_correction(session, dossier)


def test_other_site_owner_is_never_inferred_from_ddk_company(monkeypatch):
    session, dossier, ddk, site, queue = _fixture(monkeypatch)
    site.company_id = "unknown-company"
    with pytest.raises(owner.SiteOwnerCorrectionBlocked):
        owner.plan_site_owner_correction(session, dossier)


def test_wrong_physical_workbook_sha_blocks_repair(monkeypatch):
    session, dossier, ddk, site, queue = _fixture(monkeypatch)
    dossier["source_workbook_sha256"] = "0" * 64
    with pytest.raises(owner.SiteOwnerCorrectionBlocked):
        owner.plan_site_owner_correction(session, dossier)
