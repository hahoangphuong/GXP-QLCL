"""Offline anonymized exception summary preserves observed tokens and boundaries."""
from __future__ import annotations

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate, BusinessEligibilityGxpSourceGroup,
    BusinessEligibilityGxpReferenceEvidence, Certificate, Company, Site, Case,
)
from tools.audit_ddk_gxp_canonical_candidates_readonly import classify_candidates, ROLE_COLUMNS
from tools.ddk_gxp_exception_dossier import build_exception_dossier
from tools.summarize_ddk_gxp_exception_overlap import summarize_dossier, OverlapAuditBlocked
from tools.plan_ddk_gxp_provenance_load import _source_value_digest

SHA = "a" * 64

def fixture(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "ddk-overlap.sqlite").as_posix())
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        c1, c2 = Company(legal_name="One"), Company(legal_name="Two")
        s.add_all((c1,c2));s.flush()
        a=Site(company_id=c1.id,site_name="A")
        b=Site(company_id=c1.id,site_name="B")
        x=Site(company_id=c2.id,site_name="X")
        s.add_all((a,b,x));s.flush()
        d1=BusinessEligibilityCertificate(site_id=a.id,company_id=c1.id,legacy_dkkd_id=10)
        d2=BusinessEligibilityCertificate(site_id=x.id,company_id=c1.id,legacy_dkkd_id=11)
        cert=Certificate(site_id=b.id,certificate_type="GMP",legacy_certificate_id=20)
        other=Certificate(site_id=a.id,certificate_type="GMP",legacy_certificate_id=21)
        s.add_all((d1,d2,cert,other));s.flush()
        case=Case(site_id=a.id,gxp_type="GMP",state=CaseState.DRAFT)
        s.add(case);s.flush()
        cert.case_id=case.id
        for ddk,row,raw in ((10,5,"20; 21"),(11,6,"20")):
            for group,col in ROLE_COLUMNS.items():
                value=raw if group=="GMP" else ""
                fields=[value,"","",""]
                g=BusinessEligibilityGxpSourceGroup(
                    source_workbook_sha256=SHA,source_sheet_name="db.dkkd",
                    source_row_number=row,legacy_dkkd_id=ddk,source_group=group,
                    id_cc_excel_column=col,certificate_scope_excel_column=col+1,
                    applicable_standard_excel_column=col+2,business_activity_excel_column=col+3,
                    id_cc_raw=value,certificate_scope_raw="",applicable_standard_raw="",
                    business_activity_raw="",source_values_sha256=_source_value_digest(fields),
                )
                s.add(g);s.flush()
                if group=="GMP":
                    for n,t in enumerate(raw.split("; "),1):
                        s.add(BusinessEligibilityGxpReferenceEvidence(
                            source_group_id=g.id,token_index=n,raw_token=t,
                            parsed_legacy_certificate_id=int(t),
                        ))
        s.commit()
    return engine

def report_for(tmp_path):
    engine=fixture(tmp_path)
    with Session(engine) as s:
        a=classify_candidates(s,expected_workbook_sha256=SHA,
                              expected_source_groups=8,expected_tokens=3)
        report=build_exception_dossier(s,a)
    engine.dispose()
    return report

def test_exact_reference_overlap_and_no_source_text_leak(tmp_path):
    r=summarize_dossier(report_for(tmp_path))
    assert r["source_tokens_checked"] == 3
    assert r["cross_site_occurrences"] == 2
    assert r["case_site_mismatch_occurrences"] == 2
    assert r["cross_site_and_case_site_overlap"] == 2
    assert r["cross_site_only"] == 0
    assert r["case_site_only"] == 0
    assert r["case_site_equals_ddk_site_when_case_differs_from_certificate"] == 1
    assert r["ddk_company_mismatch_count"] == 1
    assert r["company_mismatch_intersects_cross_site_ddk"] == 1
    assert r["repeated_id_count"] == 1
    assert r["repeated_extra_occurrences"] == 1
    assert r["repeated_within_one_cell_extras"] == 0
    assert r["canonical_links_created"] == r["database_writes"] == 0
    payload=json.dumps(r)
    assert "source_reference_id" not in payload
    assert "legacy_dkkd_id" not in payload
    assert "original_source" not in payload

@pytest.mark.parametrize("mutation",["approved","short","repeat","case","cross","duplicate_ref"])
def test_fails_closed_on_forged_private_dossier(tmp_path,mutation):
    d=report_for(tmp_path)
    if mutation=="approved":
        d["approval_status"]="APPROVED"
    elif mutation=="short":
        d["exception_token_details"].pop()
    elif mutation=="repeat":
        d["repeated_candidate_extra_occurrences"]+=1
    elif mutation=="case":
        d["other_case_site_or_type_observations"]["CERTIFICATE_CASE_SITE_DIFFERENT"]+=1
    elif mutation=="cross":
        d["cross_site_occurrences"]+=1
    else:
        d["exception_token_details"][1]["source_reference_id"]=(
            d["exception_token_details"][0]["source_reference_id"]
        )
    with pytest.raises(OverlapAuditBlocked):
        summarize_dossier(d)
