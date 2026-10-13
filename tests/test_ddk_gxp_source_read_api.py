"""Read-only DDK source provenance API: preserve physical groups, never link."""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate, BusinessEligibilityCertificateLink,
    BusinessEligibilityGxpReferenceEvidence, BusinessEligibilityGxpSourceGroup,
    Company, Site,
)
from backend.app.main import create_app
from backend.app.read_models import BusinessEligibilityGxpSourceEvidenceRead
from backend.app.services.catalog import CatalogReadService


WORKBOOK = "a" * 64
LAYOUT = [("GMP", 15), ("GLP", 19), ("GSP", 23), ("GDP", 27)]


def seeded(tmp_path):
    url = "sqlite:///" + (tmp_path / "source-api.sqlite").as_posix()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Sample org")
        session.add(company); session.flush()
        site = Site(company_id=company.id, site_name="Site A")
        session.add(site); session.flush()
        record = BusinessEligibilityCertificate(
            site_id=site.id, company_id=company.id, legacy_dkkd_id=400,
        )
        missing = BusinessEligibilityCertificate(
            site_id=site.id, company_id=company.id, legacy_dkkd_id=401,
        )
        no_identity = BusinessEligibilityCertificate(
            site_id=site.id, company_id=company.id, legacy_dkkd_id=None,
        )
        session.add_all([record, missing, no_identity]);session.flush()
        ids = (record.id, missing.id, no_identity.id)
        for role, col in LAYOUT:
            entry = BusinessEligibilityGxpSourceGroup(
                source_workbook_sha256=WORKBOOK,
                source_sheet_name="db.dkkd",
                source_row_number=7,
                legacy_dkkd_id=400,
                source_group=role,
                id_cc_excel_column=col,
                certificate_scope_excel_column=col + 1,
                applicable_standard_excel_column=col + 2,
                business_activity_excel_column=col + 3,
                id_cc_raw="200; 200" if role == "GMP" else "",
                certificate_scope_raw=" Sterile\n" if role == "GMP" else "",
                applicable_standard_raw=" WHO-GMP " if role == "GMP" else "",
                business_activity_raw=" GDP activity no ID " if role == "GDP" else "",
                source_values_sha256="b" * 64,
            )
            session.add(entry);session.flush()
            if role == "GMP":
                session.add_all([
                    BusinessEligibilityGxpReferenceEvidence(
                        source_group_id=entry.id, token_index=pos,
                        raw_token="200", parsed_legacy_certificate_id=200,
                    )
                    for pos in (1, 2)
                ])
        session.commit()
    return engine, url, ids


def _query(session, certificate_id):
    return CatalogReadService().get_business_eligibility_gxp_source_evidence(
        session, business_eligibility_certificate_id=certificate_id,
    )


def test_api_exact_four_source_groups_token_ordinals_and_raw_cells(tmp_path):
    engine, url, (record, _, _) = seeded(tmp_path)
    app = create_app(url)
    path = "/business-eligibility-certificates/{business_eligibility_certificate_id}/gxp-source-evidence"
    route = next(r for r in app.routes if getattr(r, "path", "") == path)
    with Session(engine) as session:
        before = session.scalar(select(func.count()).select_from(BusinessEligibilityCertificateLink))
        result = route.endpoint(
            business_eligibility_certificate_id=record,
            session=session, user=build_authenticated_user("reader", "reader"),
        )
        response = BusinessEligibilityGxpSourceEvidenceRead.model_validate(result).model_dump(mode="json")
        after = session.scalar(select(func.count()).select_from(BusinessEligibilityCertificateLink))
    assert before == after == 0
    assert response["business_eligibility_certificate_id"] == record
    assert response["legacy_dkkd_id"] == 400
    assert response["source_status"] == "available"
    assert response["source_workbook_sha256"] == WORKBOOK
    assert response["source_row_number"] == 7
    assert response["canonical_links_included"] is False
    assert [r["source_group"] for r in response["groups"]] == ["GMP", "GLP", "GSP", "GDP"]
    assert [r["id_cc_excel_column"] for r in response["groups"]] == [15, 19, 23, 27]
    assert response["groups"][0]["certificate_scope_raw"] == " Sterile\n"
    assert response["groups"][0]["applicable_standard_raw"] == " WHO-GMP "
    assert response["groups"][3]["id_cc_raw"] == ""
    assert response["groups"][3]["business_activity_raw"] == " GDP activity no ID "
    assert [r["token_index"] for r in response["groups"][0]["reference_tokens"]] == [1, 2]
    assert [r["parsed_legacy_certificate_id"] for r in response["groups"][0]["reference_tokens"]] == [200, 200]
    assert response["groups"][1]["reference_tokens"] == []
    assert all(len(row["source_group_id"]) == 36 for row in response["groups"])
    engine.dispose()


def test_api_returns_explicit_missing_status_without_inventing_links(tmp_path):
    engine, _, (_, missing, no_identity) = seeded(tmp_path)
    with Session(engine) as session:
        result = _query(session, missing)
        assert result["source_status"] == "not_in_imported_source"
        assert result["groups"] == []
        assert result["source_row_number"] is None
        result = _query(session, no_identity)
        assert result["source_status"] == "legacy_identity_missing"
        assert result["groups"] == []
        with pytest.raises(HTTPException) as err:
            _query(session, str(uuid4()))
        assert err.value.status_code == 404
    engine.dispose()


def test_api_refuses_partial_and_ambiguous_source_workbook(tmp_path):
    engine, _, (record, _, _) = seeded(tmp_path)
    with Session(engine) as session:
        source = session.scalar(select(BusinessEligibilityGxpSourceGroup).where(
            BusinessEligibilityGxpSourceGroup.source_group == "GDP",
        ))
        session.delete(source);session.commit()
        with pytest.raises(HTTPException) as err:
            _query(session, record)
        assert err.value.status_code == 409
    with Session(engine) as session:
        session.add(BusinessEligibilityGxpSourceGroup(
            source_workbook_sha256="c" * 64,
            source_sheet_name="db.dkkd",
            source_row_number=9,
            legacy_dkkd_id=400,
            source_group="GDP",
            id_cc_excel_column=27,
            certificate_scope_excel_column=28,
            applicable_standard_excel_column=29,
            business_activity_excel_column=30,
            id_cc_raw="",certificate_scope_raw="",applicable_standard_raw="",
            business_activity_raw="",source_values_sha256="d" * 64,
        ))
        session.commit()
        with pytest.raises(HTTPException) as err:
            _query(session, record)
        assert err.value.status_code == 409
    engine.dispose()


def test_route_reuses_catalog_auth_401_403_and_does_not_change_canonical_detail(tmp_path):
    engine, url, (record, _, _) = seeded(tmp_path)
    app = create_app(url)
    with TestClient(app) as client:
        path = f"/business-eligibility-certificates/{record}/gxp-source-evidence"
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-Auth-User": "n", "X-Auth-Role": "unexpected"}).status_code == 403
        result = client.get(path, headers={"X-Auth-User": "reader01", "X-Auth-Role": "reader"})
        assert result.status_code == 200
        assert result.json()["source_status"] == "available"
        assert result.json()["canonical_links_included"] is False
        canonical = client.get(
            f"/business-eligibility-certificates/{record}",
            headers={"X-Auth-User": "reader01", "X-Auth-Role": "reader"},
        )
        # Seed has no BusinessEligibilityVersion: existing canonical detail
        # retains its established 404, without a source-driven rescue.
        assert canonical.status_code == 404
    engine.dispose()
