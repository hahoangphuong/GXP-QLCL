"""Adversarial regressions for source-bound, read-only Certificate/Case witness."""
from copy import deepcopy
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    Case, Certificate, CertificateScope, CertificateVersion, Company, Site,
)
from backend.app.domain.legacy_certificate_case_source_audit import (
    audit_certificate_case_source_links,
)
from tools.audit_certificate_case_site_owners_rehearsal_readonly import (
    CertificateCaseWitnessBlocked, compare_source_to_rehearsal, SCHEMA,
    EXPECTED_SNAPSHOT_SHA256, main,
)


def _fixture(tmp_path, *, shared_company=False):
    engine = create_engine("sqlite:///" + str(tmp_path / "witness.sqlite"))
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        c1 = Company(legacy_company_id=57, legal_name="Case source company")
        c2 = Company(legacy_company_id=58, legal_name="Certificate source company")
        session.add_all((c1, c2));session.flush()
        s1 = Site(legacy_site_id=72, company_id=c1.id, site_name="Case site")
        s2 = Site(legacy_site_id=73, company_id=c1.id if shared_company else c2.id, site_name="Certificate site")
        session.add_all((s1, s2));session.flush()
        original = Case(
            legacy_inspection_id=378, site_id=s1.id,
            gxp_type="GMP", state=CaseState.DRAFT,
        )
        reverse = Case(
            legacy_inspection_id=380, site_id=s2.id,
            gxp_type="GMP", state=CaseState.DRAFT,
        )
        session.add_all((original, reverse));session.flush()
        cert = Certificate(
            legacy_certificate_id=376, site_id=s2.id,
            case_id=original.id, certificate_type="GMP",
            issuance_basis="inspection_case",
        )
        session.add(cert);session.flush()
        version = CertificateVersion(
            certificate_id=cert.id, version_no=1,
            issue_date=date(2018, 3, 12), certificate_number="C376",
        )
        session.add(version);session.flush()
        session.add(CertificateScope(
            certificate_version_id=version.id, scope_text="Source scope",
            language_code="vi", sort_order=0,
        ))
        session.commit()

    snapshot = {
        "db.cty": [{"ID": "57"}, {"ID": "58"}],
        "db.cso": [
            {"ID": "72", "ID Cty": "57"},
            {"ID": "73", "ID Cty": "57" if shared_company else "58"},
        ],
        "db.ktra": [
            {"ID": "378", "ID CƠ SỞ": "72", "LOẠI KT": "GMP",
             "Ngày K.tra": "01/01/2008"},
            {"ID": "380", "ID CƠ SỞ": "73", "LOẠI KT": "GMP",
             "ID CC GPs": "376", "Mã số CC": "C376",
             "PHẠM VI KIỂM TRA": "Source scope"},
        ],
        "db.cc": [{
            "ID": "376", "ID CƠ SỞ": "73", "ID ĐỢT KTRA": "378",
            "LOẠI CC": "GMP", "Mã số CC": "C376", "Ngày cấp CC": "12/03/2018",
            "PHẠM VI CHỨNG NHẬN": "Source scope",
        }],
    }
    source_report = audit_certificate_case_source_links(snapshot)
    return engine, source_report


def test_anomaly_anchor_witness_retains_original_case_and_reverse_only_candidate(tmp_path):
    engine, source = _fixture(tmp_path)
    with Session(engine) as session:
        report = compare_source_to_rehearsal(
            session, source, expected_certificate_ids={376}
        )
    assert report["schema"] == SCHEMA
    assert report["certificate_count"] == 1
    assert report["counts"]["DISTINCT_SITES_DIFFERENT_SOURCE_COMPANIES"] == 1
    assert report["reverse_case_candidate_count"] == 1
    one = report["details_private"][0]
    assert one["original_case_legacy_id"] == 378
    assert one["reverse_case_review_candidates"][0]["legacy_case_id"] == 380
    assert one["reverse_case_review_candidates"][0]["remediation_authorized"] is False
    assert one["reverse_case_review_candidates"][0]["all_three_source_signals"] is True
    assert one["reverse_case_review_candidates"][0]["source_site_gxp_correspondence"] is True
    assert one["reverse_case_review_candidates"][0]["source_certificate_number_correspondence"] is True
    assert one["reverse_case_review_candidates"][0]["source_full_scope_lexical_correspondence"] is True
    assert one["reverse_case_review_candidates"][0]["primary_signed_issuance_case_link_verified"] is False
    assert one["reverse_case_review_candidates"][0]["source_literal_correspondence_is_approval"] is False
    assert report["counts"]["reverse_case_triple_literal_corroboration_only"] == 1
    assert one["decision_gate"] == "ORIGINAL_ISSUANCE_CASE_AND_OWNER_SIGNOFF_REQUIRED"
    assert len(one["certificate_versions"]) == 1
    assert len(one["certificate_versions"][0]["scope_evidence"]) == 1
    assert one["certificate_versions"][0]["original_import_value_fidelity_verified"] is True
    assert report["counts"]["source_certificate_version_fidelity_verified"] == 1
    assert one["certificate_versions"][0]["site_specific_scope_coverage_verified"] is False
    assert report["case_rebinding_authorized"] is False
    assert report["site_specific_scope_coverage_approved"] is False
    assert report["database_writes"] == 0
    engine.dispose()


def test_same_company_different_sites_not_equated_or_approved(tmp_path):
    engine, source = _fixture(tmp_path, shared_company=True)
    with Session(engine) as session:
        report = compare_source_to_rehearsal(
            session, source, expected_certificate_ids={376}
        )
    assert report["counts"]["DISTINCT_SITES_SAME_SOURCE_COMPANY"] == 1
    one = report["details_private"][0]
    assert one["original_case_site_id"] != one["certificate_site_id"]
    assert one["decision_gate"] == "REVIEWED_CASE_AND_VERSION_SITE_COVERAGE_REQUIRED"
    assert one["legal_coverage_approved"] is False
    engine.dispose()


@pytest.mark.parametrize("mutation", [
    "source_approved", "source_missing", "source_owner_corrupted",
    "changed_cert_case", "changed_cert_site", "changed_site_owner",
    "changed_reverse_case", "changed_certificate_gxp",
    "reverse_literal_site", "reverse_literal_gxp", "reverse_literal_flag",
    "reverse_literal_missing", "reverse_owner_missing", "reverse_duplicate",
    "source_cert_number_hash", "source_cert_issue_date", "source_cert_scope_hash",
    "changed_version_number", "changed_version_issue_date", "changed_version_scope",
])
def test_any_source_or_canonical_drift_fails_closed(tmp_path, mutation):
    engine, report = _fixture(tmp_path)
    with Session(engine) as session:
        if mutation == "source_approved":
            report["effective_anomalies"][0]["remediation_authorized"] = True
        elif mutation == "source_missing":
            report["effective_anomalies"] = []
        elif mutation == "source_owner_corrupted":
            report["effective_anomalies"][0]["site_master_company_evidence"][
                "linked_case_site_owner_legacy_company_id"] = 58
        elif mutation == "changed_cert_case":
            c = session.query(Certificate).one()
            c.case_id = session.query(Case).filter_by(legacy_inspection_id=380).one().id
            session.flush()
        elif mutation == "changed_cert_site":
            c = session.query(Certificate).one()
            c.site_id = session.query(Site).filter_by(legacy_site_id=72).one().id
            session.flush()
        elif mutation == "changed_site_owner":
            c = session.query(Company).filter_by(legacy_company_id=57).one()
            s = session.query(Site).filter_by(legacy_site_id=73).one()
            s.company_id = c.id
            session.flush()
        elif mutation == "changed_reverse_case":
            c = session.query(Case).filter_by(legacy_inspection_id=380).one()
            c.site_id = session.query(Site).filter_by(legacy_site_id=72).one().id
            session.flush()
        elif mutation == "changed_certificate_gxp":
            session.query(Certificate).one().certificate_type = "GLP"
            session.flush()
        elif mutation == "reverse_literal_site":
            report["effective_anomalies"][0]["reverse_case_reference_evidence"][0]["site_legacy_id"] = 72
        elif mutation == "reverse_literal_gxp":
            report["effective_anomalies"][0]["reverse_case_reference_evidence"][0]["gxp_type"] = "GLP"
        elif mutation == "reverse_literal_flag":
            report["effective_anomalies"][0]["reverse_case_reference_evidence"][0]["same_certificate_site_and_type"] = False
        elif mutation == "reverse_literal_missing":
            report["effective_anomalies"][0]["reverse_case_reference_evidence"] = []
        elif mutation == "reverse_owner_missing":
            report["effective_anomalies"][0]["site_master_company_evidence"]["reverse_source_cases"] = []
        elif mutation == "reverse_duplicate":
            report["effective_anomalies"][0]["reverse_case_reference_evidence"].append(
                deepcopy(report["effective_anomalies"][0]["reverse_case_reference_evidence"][0])
            )
        elif mutation == "source_cert_number_hash":
            report["effective_anomalies"][0]["source_version_fidelity_evidence"][
                "certificate_number_sha256"] = "0" * 64
        elif mutation == "source_cert_issue_date":
            report["effective_anomalies"][0]["source_version_fidelity_evidence"][
                "issue_date"] = "2026-01-01"
        elif mutation == "source_cert_scope_hash":
            report["effective_anomalies"][0]["source_version_fidelity_evidence"][
                "certificate_scope_sha256"] = "0" * 64
        elif mutation == "changed_version_number":
            session.query(CertificateVersion).one().certificate_number = "Different"
            session.flush()
        elif mutation == "changed_version_issue_date":
            session.query(CertificateVersion).one().issue_date = date(2026, 1, 1)
            session.flush()
        elif mutation == "changed_version_scope":
            session.query(CertificateScope).one().scope_text = "Different"
            session.flush()
        with pytest.raises(CertificateCaseWitnessBlocked):
            compare_source_to_rehearsal(
                session, deepcopy(report), expected_certificate_ids={376}
            )
    engine.dispose()


def test_cli_rejects_modified_snapshot_before_database_connection(tmp_path, capsys):
    bad = tmp_path / "replayed-snapshot.json"
    bad.write_text("{}", encoding="utf-8")
    output = tmp_path / "should-not-exist.json"
    assert len(EXPECTED_SNAPSHOT_SHA256) == 64
    assert main(["--snapshot", str(bad), "--private-output", str(output)]) == 2
    assert not output.exists()
    captured = capsys.readouterr()
    assert "CERTIFICATE_CASE_TARGET_WITNESS_BLOCKED" in captured.err
    assert "snapshot" not in captured.err.lower()
