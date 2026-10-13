"""Authenticated CertificateVersion history contract: own-scope identity only."""
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
    Case, Certificate, CertificateScope, CertificateVersion, Company, Site,
)
from backend.app.db.enums import CaseState
from backend.app.main import create_app
from backend.app.read_models import GxpCertificateVersionHistoryRead
from backend.app.services.catalog import CatalogReadService


def _seed(tmp_path):
    url = f"sqlite:///{(tmp_path / 'certificate-history.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Test historical company")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="History Site")
        session.add(site)
        session.flush()
        other_site = Site(company_id=company.id, site_name="Other Site")
        session.add(other_site)
        session.flush()
        case = Case(
            site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT,
            legacy_inspection_id=701, legacy_inspection_code="KT-701",
        )
        session.add(case)
        session.flush()
        certificate = Certificate(
            site_id=site.id, case_id=case.id, certificate_type="GMP",
            latest_flag=True,
        )
        foreign = Certificate(
            site_id=other_site.id, certificate_type="GSP", latest_flag=True,
        )
        session.add_all([certificate, foreign])
        session.flush()
        old = CertificateVersion(
            certificate_id=certificate.id, version_no=1,
            certificate_number="OLD-V1", lifecycle_state=None,
            issue_date=date(2023, 2, 3), applicable_standard="Old standard",
            is_latest_version=False,
        )
        current = CertificateVersion(
            certificate_id=certificate.id, version_no=2,
            certificate_number="CURRENT-V2", lifecycle_state="GRANTED",
            issue_date=date(2026, 8, 1), expiry_date=date(2029, 8, 1),
            applicable_standard="New standard", is_latest_version=True,
        )
        foreign_version = CertificateVersion(
            certificate_id=foreign.id, version_no=1,
            certificate_number="FOREIGN", is_latest_version=True,
        )
        session.add_all([current, old, foreign_version])
        session.flush()
        versions = (old.id, current.id)
        original_certificate = certificate.id
        original_case = case.id
        for version_id, key, text, order in [
            (old.id, "old-en", " Scope A\nold line", 2),
            (old.id, "old-vi", "Scope B", 1),
            (current.id, "new-vi", " Current scope ", 1),
            (foreign_version.id, "foreign", "Must not leak", 1),
        ]:
            session.add(CertificateScope(
                certificate_version_id=version_id,
                scope_key=key, scope_text=text,
                language_code="en" if key == "old-en" else "vi",
                sort_order=order,
            ))
        session.commit()
    return engine, url, original_certificate, original_case, versions


def test_historical_versions_have_distinct_uuid_and_original_scope_snapshots(tmp_path):
    engine, url, cert_id, _, version_ids = _seed(tmp_path)
    app = create_app(url)
    history_route = next(
        route for route in app.routes
        if getattr(route, "path", "") == "/certificates/{certificate_id}/versions"
    )
    current_route = next(
        route for route in app.routes
        if getattr(route, "path", "") == "/certificates/{certificate_id}"
    )
    with Session(engine) as session:
        before = session.scalar(select(func.count()).select_from(CertificateVersion))
        projected = history_route.endpoint(
            certificate_id=cert_id,
            session=session,
            user=build_authenticated_user("reader1", "reader"),
        )
        current = current_route.endpoint(
            certificate_id=cert_id,
            session=session,
            user=build_authenticated_user("reader1", "reader"),
        )
        after = session.scalar(select(func.count()).select_from(CertificateVersion))
    data = GxpCertificateVersionHistoryRead.model_validate(projected).model_dump(mode="json")
    assert before == after == 3
    assert data["certificate_id"] == cert_id
    assert data["aggregate_latest_flag"] is True
    assert data["latest_version_id"] == version_ids[1]
    assert [v["version_no"] for v in data["versions"]] == [2, 1]
    assert [v["certificate_version_id"] for v in data["versions"]] == [
        version_ids[1], version_ids[0],
    ]
    assert all(v["row_version"] == 1 for v in data["versions"])
    assert data["versions"][1]["lifecycle_state"] is None
    assert data["versions"][0]["lifecycle_state"] == "GRANTED"
    assert data["versions"][1]["scope_summary"] is not None
    assert [s["scope_key"] for s in data["versions"][1]["scopes"]] == ["old-vi", "old-en"]
    assert data["versions"][1]["scopes"][1]["scope_text"] == " Scope A\nold line"
    assert [s["scope_key"] for s in data["versions"][0]["scopes"]] == ["new-vi"]
    assert all(
        scope["scope_key"] != "foreign"
        for version in data["versions"] for scope in version["scopes"]
    )
    assert current.certificate_number == "CURRENT-V2"
    assert [s.scope_key for s in current.scopes] == ["new-vi"]
    engine.dispose()


def test_missing_certificate_and_empty_history_are_explicit(tmp_path):
    engine, _, cert_id, _, _ = _seed(tmp_path)
    with Session(engine) as session:
        with pytest.raises(HTTPException) as missing:
            CatalogReadService().get_gxp_certificate_version_history(
                session, certificate_id=str(uuid4()),
            )
        assert missing.value.status_code == 404
        versions = list(session.scalars(select(CertificateVersion).where(
            CertificateVersion.certificate_id == cert_id,
        )))
        for v in versions:
            for scope in session.scalars(select(CertificateScope).where(
                CertificateScope.certificate_version_id == v.id,
            )):
                session.delete(scope)
            session.delete(v)
        session.commit()
        result = CatalogReadService().get_gxp_certificate_version_history(
            session, certificate_id=cert_id,
        )
        assert result["latest_version_id"] is None
        assert result["versions"] == []
    engine.dispose()


def test_ambiguous_latest_version_fails_closed_without_modifying_rows(tmp_path):
    engine, _, cert_id, _, _ = _seed(tmp_path)
    with Session(engine) as session:
        old = session.scalar(select(CertificateVersion).where(
            CertificateVersion.certificate_id == cert_id,
            CertificateVersion.version_no == 1,
        ))
        old.is_latest_version = True
        session.commit()
        with pytest.raises(HTTPException) as conflict:
            CatalogReadService().get_gxp_certificate_version_history(
                session, certificate_id=cert_id,
            )
        assert conflict.value.status_code == 409
        assert "ambiguous latest" in str(conflict.value.detail)
    engine.dispose()


def test_endpoint_uses_catalog_401_403_without_stub_bypass(tmp_path):
    engine, url, cert_id, _, _ = _seed(tmp_path)
    app = create_app(url)
    history_route = next(
        route for route in app.routes
        if getattr(route, "path", "") == "/certificates/{certificate_id}/versions"
    )
    with pytest.raises(HTTPException) as unauthorized:
        get_authenticated_user(SimpleNamespace(app=app, headers={}))
    assert unauthorized.value.status_code == 401
    with Session(engine) as session:
        with pytest.raises(HTTPException) as denied:
            history_route.endpoint(
                certificate_id=cert_id, session=session,
                user=build_authenticated_user("bad_role", "unauthorized_role"),
            )
        assert denied.value.status_code == 403
        assert history_route.endpoint(
            certificate_id=cert_id, session=session,
            user=build_authenticated_user("reader", "reader"),
        ).certificate_id == cert_id
    engine.dispose()


def test_case_site_integrity_validated_before_history_exposure(tmp_path):
    engine, _, cert_id, _, _ = _seed(tmp_path)
    with Session(engine) as session:
        cert = session.get(Certificate, cert_id)
        foreign_site = session.scalar(select(Site).where(Site.id != cert.site_id))
        linked_case = session.get(Case, cert.case_id)
        linked_case.site_id = foreign_site.id
        session.commit()
        with pytest.raises(HTTPException) as invalid:
            CatalogReadService().get_gxp_certificate_version_history(
                session, certificate_id=cert_id,
            )
        assert invalid.value.status_code == 409
    engine.dispose()
