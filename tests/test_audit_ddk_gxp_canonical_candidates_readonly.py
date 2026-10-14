"""Source ID CC -> canonical Certificate lookup is never automatic approval."""
from __future__ import annotations

from hashlib import sha256
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate, BusinessEligibilityGxpReferenceEvidence,
    BusinessEligibilityGxpSourceGroup, Certificate, CertificateScope,
    CertificateVersion, Case, Company, Site,
)
from tools.audit_ddk_gxp_canonical_candidates_readonly import (
    CandidateAuditBlocked, classify_candidates, ROLE_COLUMNS,
)
from tools.plan_ddk_gxp_provenance_load import _source_value_digest
from tools.ddk_gxp_exception_dossier import build_exception_dossier
from backend.app.db.enums import CaseState


SHA = "a" * 64


def _fixture(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'ddk-source-candidates.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        c1 = Company(legal_name="Company A")
        c2 = Company(legal_name="Company B")
        session.add_all((c1, c2)); session.flush()
        s1 = Site(company_id=c1.id, site_name="Site 1")
        s2 = Site(company_id=c1.id, site_name="Site 2")
        s3 = Site(company_id=c2.id, site_name="Site 3")
        session.add_all((s1, s2, s3));session.flush()
        d1 = BusinessEligibilityCertificate(
            site_id=s1.id, company_id=c1.id, legacy_dkkd_id=400,
        )
        d2 = BusinessEligibilityCertificate(
            site_id=s3.id, company_id=c1.id, legacy_dkkd_id=401,
        )
        cert_good = Certificate(
            site_id=s1.id, certificate_type="GMP", legacy_certificate_id=200,
        )
        cert_cross = Certificate(
            site_id=s2.id, certificate_type="GMP", legacy_certificate_id=201,
        )
        cert_type = Certificate(
            site_id=s1.id, certificate_type="GLP", legacy_certificate_id=202,
        )
        session.add_all((d1, d2, cert_good, cert_cross, cert_type)); session.flush()
        for ddk_id, physical_row, gmp_source in [
            (400, 7, "200; 200; 201; 202; 999"),
            (401, 8, "200"),
        ]:
            for role, col in ROLE_COLUMNS.items():
                cell = gmp_source if role == "GMP" else ""
                values = [cell, "", "", "Activity without ID" if role == "GDP" else ""]
                g = BusinessEligibilityGxpSourceGroup(
                    source_workbook_sha256=SHA,
                    source_sheet_name="db.dkkd",
                    source_row_number=physical_row,
                    legacy_dkkd_id=ddk_id,
                    source_group=role,
                    id_cc_excel_column=col,
                    certificate_scope_excel_column=col + 1,
                    applicable_standard_excel_column=col + 2,
                    business_activity_excel_column=col + 3,
                    id_cc_raw=values[0], certificate_scope_raw=values[1],
                    applicable_standard_raw=values[2], business_activity_raw=values[3],
                    source_values_sha256=_source_value_digest(values),
                )
                session.add(g);session.flush()
                if cell:
                    for i, token in enumerate(cell.split("; "), 1):
                        session.add(BusinessEligibilityGxpReferenceEvidence(
                            source_group_id=g.id,
                            token_index=i, raw_token=token,
                            parsed_legacy_certificate_id=int(token),
                        ))
        session.commit()
    return engine


def test_classifies_matches_cross_site_type_and_ddk_company_without_links(tmp_path):
    engine = _fixture(tmp_path)
    with Session(engine) as s:
        result = classify_candidates(s, expected_workbook_sha256=SHA,
                                     expected_source_groups=8, expected_tokens=6)
        counts = result["counts"]
        assert result["status"] == "SOURCE_CANDIDATE_OBSERVATIONS_ONLY_NO_LINK_APPROVAL"
        assert result["approval_status"] == "NOT_APPROVED"
        assert result["recorded_canonical_gxp_link_rows_before"] == 0
        assert result["canonical_links_created"] == 0
        assert result["source_ddk_ids"] == 2
        assert counts["candidate_certificate_found"] == 5
        assert counts["candidate_certificate_missing"] == 1
        assert counts["candidate_different_site"] == 2
        assert counts["certificate_type_different"] == 1
        assert counts["ddk_site_company_mismatch"] == 1
        assert result["repeated_candidate_id_extra_occurrences"] == 2
        groups = [row for row in result["candidate_observations"] if row["legacy_dkkd_id"] == 400]
        assert [x["token_index"] for x in groups] == [1, 2, 3, 4, 5]
        assert [x["parsed_legacy_certificate_id"] for x in groups] == [200, 200, 201, 202, 999]
        assert all(x["link_approval"] == "NOT_APPROVED" for x in groups)
        assert "SOURCE_OBSERVATION_NOT_APPROVED" in groups[0]["flags"]
        assert "CERTIFICATE_SITE_DIFFERENT" in groups[2]["flags"]
        assert "CERTIFICATE_GXP_TYPE_DIFFERENT" in groups[3]["flags"]
        assert "CERTIFICATE_CANONICAL_MISSING" in groups[4]["flags"]
    engine.dispose()


@pytest.mark.parametrize("alter", ["digest", "missing_role", "missing_token", "worksheet"])
def test_tampered_or_incomplete_source_fails_closed(tmp_path, alter):
    engine = _fixture(tmp_path)
    with Session(engine) as s:
        item = s.query(BusinessEligibilityGxpSourceGroup).first()
        if alter == "digest":
            item.source_values_sha256 = "0" * 64
        elif alter == "missing_role":
            s.delete(item)
        elif alter == "missing_token":
            t = s.query(BusinessEligibilityGxpReferenceEvidence).first()
            s.delete(t)
        else:
            item.source_workbook_sha256 = "f" * 64
        s.commit()
        with pytest.raises(CandidateAuditBlocked):
            classify_candidates(s, expected_workbook_sha256=SHA,
                                expected_source_groups=8, expected_tokens=6)
    engine.dispose()


def test_unavailable_canonical_ddk_is_flagged_not_inferred(tmp_path):
    engine = _fixture(tmp_path)
    with Session(engine) as s:
        d = s.query(BusinessEligibilityCertificate).filter_by(legacy_dkkd_id=401).one()
        s.delete(d);s.commit()
        r = classify_candidates(s, expected_workbook_sha256=SHA,
                                expected_source_groups=8, expected_tokens=6)
        assert r["counts"]["source_ddk_canonical_missing"] == 1
        assert "DDK_CANONICAL_MISSING" in r["candidate_observations"][-1]["flags"]
    engine.dispose()


def test_exception_dossier_preserves_multi_axis_flags_and_duplicate_positions(tmp_path):
    engine = _fixture(tmp_path)
    with Session(engine) as s:
        cert = s.query(Certificate).filter_by(legacy_certificate_id=200).one()
        version = CertificateVersion(
            certificate_id=cert.id, version_no=1, lifecycle_state=None,
            certificate_number="TEST", is_latest_version=True,
        )
        s.add(version)
        s.flush()
        scope = CertificateScope(
            certificate_version_id=version.id, scope_text="Sensitive scope text",
            language_code="vi", sort_order=1,
        )
        s.add(scope)
        # An unrelated Case owner may not be silently interpreted as valid
        # coverage for this certificate. It is a further review flag only.
        other_site = s.query(Site).filter_by(site_name="Site 2").one()
        case = Case(site_id=other_site.id, gxp_type="GMP",
                    state=CaseState.DRAFT)
        s.add(case);s.flush()
        cert.case_id = case.id
        s.commit()

        baseline = classify_candidates(
            s, expected_workbook_sha256=SHA,
            expected_source_groups=8, expected_tokens=6,
        )
        result = build_exception_dossier(s, baseline)
        assert result["status"] == "READ_ONLY_EXCEPTION_EVIDENCE_NOT_APPROVED"
        assert result["distinct_observed_certificate_legacy_ids"] == 4
        assert result["candidate_repeated_id_count"] == 1
        assert result["repeated_candidate_extra_occurrences"] == 2
        assert result["within_one_source_cell_repeat_extras"] == 1
        assert result["candidate_ids_observed_in_multiple_ddk"] == 1
        assert result["cross_site_occurrences"] == 2
        assert result["ddk_site_company_mismatches"] == 1
        assert result["other_case_site_or_type_observations"]["CERTIFICATE_CASE_SITE_DIFFERENT"] == 3
        assert result["database_writes"] == result["canonical_links_created"] == 0
        assert len(result["ddk_company_exception_details"]) == 1
        assert result["ddk_company_exception_details"][0]["legacy_dkkd_id"] == 401
        xs = result["exception_token_details"]
        assert any(
            row["parsed_legacy_certificate_id"] == 201
            and "CERTIFICATE_SITE_DIFFERENT" in row["flags"]
            for row in xs
        )
        assert any(
            row["parsed_legacy_certificate_id"] == 202
            and "CERTIFICATE_GXP_TYPE_DIFFERENT" in row["flags"]
            for row in xs
        )
        assert any(
            row["parsed_legacy_certificate_id"] == 999
            and "CERTIFICATE_CANONICAL_MISSING" in row["flags"]
            for row in xs
        )
        ids = [x["token_index"] for x in result["repeated_candidate_id_details"][0]["observations"]
               if x["legacy_dkkd_id"] == 400]
        assert ids == [1, 2]
        version_details = next(
            x["certificate_versions"] for x in xs
            if x["parsed_legacy_certificate_id"] == 200
        )
        assert version_details[0]["certificate_version_id"] == version.id
        assert version_details[0]["lifecycle_state"] is None
        assert version_details[0]["scope_evidence"][0]["scope_text_sha256"] == sha256(
            b"Sensitive scope text"
        ).hexdigest()
        assert "Sensitive scope text" not in json.dumps(result)
    engine.dispose()


def test_exception_dossier_rejects_forged_or_partial_audit(tmp_path):
    engine = _fixture(tmp_path)
    with Session(engine) as s:
        audit = classify_candidates(s, expected_workbook_sha256=SHA,
                                   expected_source_groups=8, expected_tokens=6)
        original = audit["candidate_observations"]
        audit["candidate_observations"] = original[:-1]
        with pytest.raises(CandidateAuditBlocked):
            build_exception_dossier(s, audit)
        audit["candidate_observations"] = original
        audit["approval_status"] = "APPROVED"
        with pytest.raises(CandidateAuditBlocked):
            build_exception_dossier(s, audit)
    engine.dispose()
