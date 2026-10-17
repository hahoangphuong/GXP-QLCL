"""Storage lookup readiness is evidence-only and preserves owner identity."""
from __future__ import annotations

from hashlib import sha256
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate, Certificate, Case, Company, Site,
    LegacyInspectionStorageAnchor, StorageBinding,
)
from tools.audit_ddk_gxp_storage_identity_readiness import (
    StorageReadinessBlocked, classify_anchor, profile_storage_lookup_inputs,
)


def _seed(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "storage-readiness.db").as_posix())
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        company=Company(legal_name="Test company")
        s.add(company);s.flush()
        ddk_site=Site(company_id=company.id,site_name="DDK Site",legacy_site_id=10)
        case_site=Site(company_id=company.id,site_name="Case Site",legacy_site_id=11)
        s.add_all([ddk_site,case_site]);s.flush()
        ddk=BusinessEligibilityCertificate(site_id=ddk_site.id,
                                           company_id=company.id,legacy_dkkd_id=50)
        case=Case(site_id=case_site.id,gxp_type="GMP",legacy_inspection_code="2026-B",
                  legacy_inspection_id=900,state=CaseState.DRAFT)
        s.add_all([ddk,case]);s.flush()
        cert=Certificate(site_id=ddk_site.id,certificate_type="GMP",
                         legacy_certificate_id=70,case_id=case.id)
        s.add(cert);s.flush()
        s.add(LegacyInspectionStorageAnchor(
            case_id=case.id,source_sheet="db.ktra",source_row=12,
            registration_submission_raw="2026",
            registration_submission_status="usable",registration_submission_year=2026,
            inspection_date_raw="",inspection_year_status="unavailable",
            inspection_year=None,source_hash="a"*64,source_version="b"*64,
        ))
        s.commit()
        return engine, dict(ddk_id=ddk.id,site_id=ddk_site.id,company_id=company.id,
                            case_id=case.id,case_site_id=case_site.id,cert_id=cert.id)


def _queue(ids):
    return {
        "schema":"GXP_DDK_EXCEPTION_MANUAL_REVIEW_QUEUE_V1",
        "status":"PRIVATE_REVIEW_ONLY_NOT_APPROVED",
        "link_approval":"NOT_APPROVED",
        "manual_review_status":"PENDING_INDEPENDENT_EVIDENCE",
        "database_writes":0,"canonical_links_created":0,
        "source_exception_token_records":1,"ddk_company_review_records":0,
        "source_token_reviews":[{
            "review_key":"SOURCE_TOKEN:1","review_status":"PENDING_INDEPENDENT_EVIDENCE",
            "link_approval":"NOT_APPROVED",
            "original_exception_evidence":{
                "legacy_dkkd_id":50,"ddk_site_id":ids["site_id"],
                "ddk_company_id":ids["company_id"],"observed_certificate_id":ids["cert_id"],
                "parsed_legacy_certificate_id":70,
                "certificate_site_id":ids["site_id"],"certificate_case_id":ids["case_id"],
                "certificate_type":"GMP","case_site_id":ids["case_site_id"],
                "case_gxp_type":"GMP",
            },
        }],
        "ddk_company_reviews":[],
    }


def test_ready_inputs_do_not_claim_storage_was_resolved(tmp_path):
    engine,ids=_seed(tmp_path)
    with Session(engine) as s:
        report=profile_storage_lookup_inputs(s,_queue(ids))
    assert report["review_records"] == 1
    assert report["lookup_input_classification_counts"] == {
        "DDK_SITE_IDENTITY_INPUT_AVAILABLE_UNPROBED":1,
        "DDK_COMPANY_SOURCE_AND_CANONICAL_SITE_OWNER_AGREE":1,
        "CERTIFICATE_SITE_ID_AVAILABLE_REFERENCE_ONLY":1,
        "CASE_LOOKUP_INPUT_AVAILABLE_UNPROBED":1,
        "CASE_ANCHOR_REGISTRATION_SOURCE_YEAR_USABLE":1,
        "CASE_BINDING_ROWS_ABSENT":1,
    }
    assert report["unique_ddk_count"] == 1
    assert report["unique_certificate_count"] == 1
    assert report["unique_originating_case_count"] == 1
    row=report["private_lookup_input_evidence"][0]
    assert row["originating_case_reference"]["case_site_legacy_id"] == 11
    assert row["originating_case_reference"]["source_year_observed"] == 2026
    assert row["ddk"]["site_legacy_id"] == 10
    assert report["storage_roots_accessed"] is False
    assert report["storage_folders_enumerated"] is False
    assert report["storage_binaries_verified"] is False
    assert report["canonical_links_created"] == 0
    engine.dispose()


def test_changed_certificate_case_site_or_approval_blocks(tmp_path):
    engine,ids=_seed(tmp_path)
    with Session(engine) as s:
        q=_queue(ids);q["link_approval"]="APPROVED"
        with pytest.raises(StorageReadinessBlocked):
            profile_storage_lookup_inputs(s,q)
        q=_queue(ids);q["source_token_reviews"][0]["original_exception_evidence"]["case_site_id"]=ids["site_id"]
        with pytest.raises(StorageReadinessBlocked):
            profile_storage_lookup_inputs(s,q)
        q=_queue(ids);q["source_token_reviews"][0]["original_exception_evidence"]["certificate_case_id"]=None
        with pytest.raises(StorageReadinessBlocked):
            profile_storage_lookup_inputs(s,q)
    engine.dispose()


def test_year_conflict_is_not_replaced_by_inspection_fallback(tmp_path):
    engine,ids=_seed(tmp_path)
    with Session(engine) as s:
        a=s.query(LegacyInspectionStorageAnchor).one()
        a.registration_submission_status="conflict"
        a.registration_submission_year=None
        a.inspection_year_status="usable"
        a.inspection_year=2026
        s.flush()
        status,year=classify_anchor(a)
        assert status=="REGISTRATION_SOURCE_YEAR_CONFLICT_NOT_RESOLVED"
        assert year is None
        report=profile_storage_lookup_inputs(s,_queue(ids))
        assert report["lookup_input_classification_counts"]["CASE_LOOKUP_INPUT_INCOMPLETE"] == 1
    engine.dispose()


def test_missing_anchor_and_case_missing_legacy_code_are_visible(tmp_path):
    engine,ids=_seed(tmp_path)
    with Session(engine) as s:
        a=s.query(LegacyInspectionStorageAnchor).one()
        s.delete(a)
        case=s.get(Case,ids["case_id"])
        case.legacy_inspection_code=None
        s.flush()
        report=profile_storage_lookup_inputs(s,_queue(ids))
        assert report["lookup_input_classification_counts"]["CASE_ANCHOR_CASE_ANCHOR_METADATA_MISSING"] == 1
        assert report["lookup_input_classification_counts"]["CASE_LOOKUP_INPUT_INCOMPLETE"] == 1
    engine.dispose()
