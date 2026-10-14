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
    BusinessEligibilityGxpSourceGroup, Certificate, Company, Site,
)
from tools.audit_ddk_gxp_canonical_candidates_readonly import (
    CandidateAuditBlocked, classify_candidates, ROLE_COLUMNS,
)
from tools.plan_ddk_gxp_provenance_load import _source_value_digest


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
