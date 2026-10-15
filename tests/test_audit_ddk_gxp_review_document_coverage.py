"""DDK flagged review parent-doc metadata: observed != verified evidence."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState, DocumentVariantType
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate, Case, Certificate, Company, Document,
    DocumentVariant, DocumentVersion, Site,
)
from tools.audit_ddk_gxp_review_document_coverage import (
    DocumentCoverageBlocked, scan_document_metadata,
)


def _seed(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "coverage.db").as_posix())
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        c = Company(legal_name="A")
        original_ddk_company = Company(legal_name="Legacy source Company ID")
        session.add_all([c, original_ddk_company]); session.flush()
        s = Site(company_id=c.id, site_name="A1")
        session.add(s); session.flush()
        ddk = BusinessEligibilityCertificate(site_id=s.id, company_id=original_ddk_company.id, legacy_dkkd_id=50)
        case = Case(site_id=s.id, gxp_type="GMP", state=CaseState.DRAFT)
        session.add_all([ddk, case]); session.flush()
        cert = Certificate(site_id=s.id, certificate_type="GMP", case_id=case.id,
                           legacy_certificate_id=80)
        session.add(cert); session.flush()
        source_doc = Document(certificate_id=cert.id, family_code="SOURCE",
                              document_type_code="CERTIFICATE_ORIGINAL")
        meta_only = Document(case_id=case.id, family_code="CASE",
                             document_type_code="INSPECTION_REPORT")
        session.add_all([source_doc, meta_only]); session.flush()
        variant = DocumentVariant(document_id=source_doc.id,
                                  variant_type=DocumentVariantType.SCANNED_PDF,
                                  language_code="vi")
        session.add(variant); session.flush()
        session.add(DocumentVersion(
            document_variant_id=variant.id, version_no=1, storage_root="legacy",
            storage_relative_path="case/fake.pdf", checksum_sha256="a" * 64,
        ))
        result = engine, ddk.id, cert.id, cert.site_id, case.id, case.site_id, original_ddk_company.id, c.id
        session.commit()
        return result


def _queue(ddk_id, cert_id, cert_site_id, case_id, case_site_id, company_id, site_owner_company_id):
    return {
        "schema": "GXP_DDK_EXCEPTION_MANUAL_REVIEW_QUEUE_V1",
        "link_approval": "NOT_APPROVED",
        "manual_review_status": "PENDING_INDEPENDENT_EVIDENCE",
        "database_writes": 0, "canonical_links_created": 0,
        "source_exception_token_records": 1,
        "ddk_company_review_records": 1,
        "source_token_reviews": [{
            "review_key": "SOURCE_TOKEN:1",
            "original_exception_evidence": {
                "legacy_dkkd_id": 50, "observed_certificate_id": cert_id,
                "parsed_legacy_certificate_id": 80, "certificate_site_id": cert_site_id,
                "certificate_case_id": case_id, "case_site_id": case_site_id,
                "ddk_site_id": cert_site_id, "ddk_company_id": company_id,
            },
        }],
        "ddk_company_reviews": [{
            "review_key": "DDK_COMPANY:50",
            "original_company_exception_evidence": {
                "legacy_dkkd_id": 50,
                "canonical_business_eligibility_certificate_id": ddk_id,
                "ddk_site_id": cert_site_id, "ddk_company_id": company_id,
                "site_owning_company_id": site_owner_company_id,
                "link_approval": "NOT_APPROVED",
            },
        }],
    }


def test_per_parent_metadata_and_binary_uncertainty(tmp_path):
    engine, ddk, cert, site, case, case_site, company, site_owner = _seed(tmp_path)
    with Session(engine) as session:
        report = scan_document_metadata(session, _queue(ddk, cert, site, case, case_site, company, site_owner))
    assert report["source_token_review_records"] == 1
    assert report["ddk_company_review_records"] == 1
    assert report["unique_parent_counts"] == {
        "DDK": 1, "CERTIFICATE": 1, "ORIGINATING_CASE": 1,
    }
    assert report["parent_review_classification_counts"] == {
        "CERTIFICATE_STORAGE_LOCATOR_RECORDED_UNVERIFIED": 1,
        "DDK_COMPANY_SOURCE_DISCREPANCY_CANONICAL_NOT_YET_ALIGNED": 2,
        "DDK_NO_DOCUMENT_METADATA": 2,
        "ORIGINATING_CASE_DOCUMENT_METADATA_WITHOUT_STORAGE_LOCATOR": 1,
        "ORIGINATING_CASE_not_linked": 1,
        "CERTIFICATE_not_linked": 1,
    }
    assert report["binary_content_verified"] is False
    assert report["storage_paths_probed"] is False
    assert report["canonical_links_created"] == report["database_writes"] == 0
    data = report["private_review_document_metadata"][0]
    cert_target = next(x for x in data["targets"] if x["role"] == "CERTIFICATE")
    assert cert_target["metadata_classification"] == "STORAGE_LOCATOR_RECORDED_UNVERIFIED"
    assert cert_target["documents"][0]["variants"][0]["stored_version_metadata"][0][
        "checksum_metadata_present"
    ]
    engine.dispose()


def test_source_identity_drift_and_missing_queue_gate_fail_closed(tmp_path):
    engine, ddk, cert, site, case, case_site, company, site_owner = _seed(tmp_path)
    q = _queue(ddk, cert, site, case, case_site, company, site_owner)
    with Session(engine) as session:
        q["link_approval"] = "APPROVED"
        try:
            scan_document_metadata(session, q)
            assert False, "Expected failed gate"
        except DocumentCoverageBlocked:
            pass
        q["link_approval"] = "NOT_APPROVED"
        q["source_token_reviews"][0]["original_exception_evidence"][
            "parsed_legacy_certificate_id"
        ] = 81
        try:
            scan_document_metadata(session, q)
            assert False, "Expected identity contradiction"
        except DocumentCoverageBlocked:
            pass
    engine.dispose()
