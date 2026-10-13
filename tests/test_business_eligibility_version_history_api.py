"""ĐĐK Version API: persistent version history, version-owned recorded links only."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user, get_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate, BusinessEligibilityCertificateLink,
    BusinessEligibilityVersion, Certificate, Company, Site,
)
from backend.app.main import create_app
from backend.app.read_models import BusinessEligibilityVersionHistoryRead
from backend.app.services.catalog import CatalogReadService


def _seed(tmp_path):
    url = f"sqlite:///{(tmp_path / 'ddk-version-history.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Version history test company")
        session.add(company); session.flush()
        site = Site(company_id=company.id, site_name="DDK version test site")
        session.add(site); session.flush()
        cert = BusinessEligibilityCertificate(
            company_id=company.id, site_id=site.id,
            legacy_dkkd_id=100, latest_flag=True,
        )
        empty = BusinessEligibilityCertificate(
            company_id=company.id, site_id=site.id, legacy_dkkd_id=101,
        )
        other = BusinessEligibilityCertificate(
            company_id=company.id, site_id=site.id, legacy_dkkd_id=102,
        )
        gmp = Certificate(site_id=site.id, certificate_type="GMP")
        glp = Certificate(site_id=site.id, certificate_type="GLP")
        session.add_all((cert, empty, other, gmp, glp)); session.flush()
        v1 = BusinessEligibilityVersion(
            business_eligibility_certificate_id=cert.id, version_no=1,
            certificate_number="DDK-OLD", issued_on=date(2020, 1, 15),
            issuance_history_text="Issued 2018; amended 2019",
            current_status_text="Historical source notes only",
            business_activity_text="Storage",
            professional_responsible_person_name="Historic owner",
        )
        v2 = BusinessEligibilityVersion(
            business_eligibility_certificate_id=cert.id, version_no=2,
            certificate_number="DDK-NEW", issued_on=date(2026, 9, 10),
            issuance_history_text=None,
            business_activity_text="Manufacturing",
            notes="Current version note",
        )
        foreign_v = BusinessEligibilityVersion(
            business_eligibility_certificate_id=other.id, version_no=1,
            certificate_number="OTHER-DDK",
        )
        session.add_all((v1, v2, foreign_v));session.flush()
        session.add_all((
            BusinessEligibilityCertificateLink(
                business_eligibility_version_id=v1.id,
                certificate_id=glp.id, link_role="source_certificate",
            ),
            BusinessEligibilityCertificateLink(
                business_eligibility_version_id=v2.id,
                certificate_id=gmp.id, link_role="replacement_certificate",
            ),
        ))
        session.commit()
        return engine, url, cert.id, empty.id, other.id, v1.id, v2.id, glp.id, gmp.id


def _history(session, id):
    return CatalogReadService().get_business_eligibility_version_history(
        session, business_eligibility_certificate_id=id,
    )


def test_versions_and_fk_records_remain_owned_by_exact_ddk_version(tmp_path):
    engine, url, cert, _, _, old_id, new_id, glp_id, gmp_id = _seed(tmp_path)
    app = create_app(url)
    route = next(
        r for r in app.routes
        if getattr(r, "path", "") ==
        "/business-eligibility-certificates/{business_eligibility_certificate_id}/versions"
    )
    with Session(engine) as session:
        before = session.scalar(select(func.count()).select_from(BusinessEligibilityCertificateLink))
        response = route.endpoint(
            business_eligibility_certificate_id=cert,
            session=session, user=build_authenticated_user("reader01", "reader"),
        )
        after = session.scalar(select(func.count()).select_from(BusinessEligibilityCertificateLink))
    data = BusinessEligibilityVersionHistoryRead.model_validate(response).model_dump(mode="json")
    assert before == after == 2
    assert data["business_eligibility_certificate_id"] == cert
    assert data["aggregate_latest_flag"] is True
    assert data["latest_version_id"] == new_id
    assert data["latest_selection_method"] == "max_persisted_version_no"
    assert data["gxp_source_tokens_included"] is False
    assert data["canonical_link_status"] == "stored_fk_only_not_validated"
    assert [v["version_no"] for v in data["versions"]] == [2, 1]
    assert [v["business_eligibility_version_id"] for v in data["versions"]] == [new_id, old_id]
    assert [v["certificate_number"] for v in data["versions"]] == ["DDK-NEW", "DDK-OLD"]
    assert data["versions"][0]["notes"] == "Current version note"
    assert data["versions"][0]["business_activity_text"] == "Manufacturing"
    assert data["versions"][1]["professional_responsible_person_name"] == "Historic owner"
    assert data["versions"][1]["issuance_history_text"] == "Issued 2018; amended 2019"
    assert len(data["versions"]) == 2  # no fabricated 2018/2019 versions
    assert data["versions"][0]["stored_link_records"][0]["certificate_id"] == gmp_id
    assert data["versions"][0]["stored_link_records"][0]["link_role"] == "replacement_certificate"
    assert data["versions"][1]["stored_link_records"][0]["certificate_id"] == glp_id
    assert data["versions"][1]["stored_link_records"][0]["link_role"] == "source_certificate"
    assert data["versions"][0]["stored_link_records"][0]["link_id"] != (
        data["versions"][1]["stored_link_records"][0]["link_id"]
    )
    engine.dispose()


def test_missing_id_and_stored_empty_history(tmp_path):
    engine, _, _, empty, _, _, _, _, _ = _seed(tmp_path)
    with Session(engine) as session:
        data = _history(session, empty)
        assert data["versions"] == []
        assert data["latest_version_id"] is None
        assert data["legacy_dkkd_id"] == 101
        with pytest.raises(HTTPException) as missing:
            _history(session, str(uuid4()))
        assert missing.value.status_code == 404
    engine.dispose()


def test_reader_role_gate_fails_closed_without_auth_header_stub(tmp_path):
    engine, url, cert, _, _, _, _, _, _ = _seed(tmp_path)
    app = create_app(url)
    route = next(
        r for r in app.routes
        if getattr(r, "path", "") ==
        "/business-eligibility-certificates/{business_eligibility_certificate_id}/versions"
    )
    with pytest.raises(HTTPException) as unauth:
        get_authenticated_user(SimpleNamespace(app=app, headers={}))
    assert unauth.value.status_code == 401
    with Session(engine) as session:
        with pytest.raises(HTTPException) as denied:
            route.endpoint(
                business_eligibility_certificate_id=cert, session=session,
                user=build_authenticated_user("badrole", "not_a_role"),
            )
        assert denied.value.status_code == 403
        allowed = route.endpoint(
            business_eligibility_certificate_id=cert, session=session,
            user=build_authenticated_user("reader", "reader"),
        )
        assert allowed.business_eligibility_certificate_id == cert
    engine.dispose()


def test_history_does_not_rewrite_independent_current_detail(tmp_path):
    engine, _, cert, _, _, _, _, _, _ = _seed(tmp_path)
    with Session(engine) as session:
        before = CatalogReadService().get_business_eligibility_detail(
            session, business_eligibility_certificate_id=cert,
        )
        data = _history(session, cert)
        after = CatalogReadService().get_business_eligibility_detail(
            session, business_eligibility_certificate_id=cert,
        )
    assert before == after
    assert before["certificate_number"] == data["versions"][0]["certificate_number"]
    # No CertificateVersion rows were seeded for GxP, so current legacy
    # projection remains empty rather than deriving links from source tokens.
    assert before["linked_gxp_certificates"] == []
    engine.dispose()
