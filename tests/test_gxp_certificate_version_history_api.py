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
    Case, Certificate, CertificateScope, CertificateVersion, Company, Site, ProductionLine,
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

def test_canonical_production_line_cross_site_rejected_like_current_detail(tmp_path):
    engine, _, cert_id, _, _ = _seed(tmp_path)
    with Session(engine) as session:
        cert = session.get(Certificate, cert_id)
        foreign_site = session.scalar(select(Site).where(Site.id != cert.site_id))
        wrong_line = ProductionLine(
            site_id=foreign_site.id, code="LINE-B", effective_from=date(2020, 1, 1),
        )
        session.add(wrong_line)
        session.flush()
        cert.production_line_id = wrong_line.id
        session.commit()
        with pytest.raises(HTTPException) as invalid:
            CatalogReadService().get_gxp_certificate_version_history(
                session, certificate_id=cert_id,
            )
        assert invalid.value.status_code == 409
    engine.dispose()


def test_history_reads_committed_version_scopes_without_flushing_drafts(tmp_path):
    from sqlalchemy import event

    engine, _, cert_id, _case_id, (old_id, current_id) = _seed(tmp_path)
    try:
        with Session(engine, autoflush=True, expire_on_commit=False) as reader:
            cached_version = reader.get(CertificateVersion, current_id)
            cached_scope = reader.scalar(
                select(CertificateScope).where(
                    CertificateScope.certificate_version_id == old_id,
                    CertificateScope.scope_key == "old-vi",
                )
            )
            cached_version.certificate_number = "UNSAVED-CURRENT"
            cached_version.is_latest_version = False
            cached_scope.scope_text = "UNSAVED-SCOPE"
            pending = Company(legal_name="Unsaved operator Company")
            reader.add(pending)
            statements, flushes = [], []

            def observe(_conn, _cursor, sql, _params, _ctx, _many):
                statements.append(sql.lstrip().split(None, 1)[0].upper())

            def no_flush(*_):
                flushes.append(True)
                raise AssertionError("Read-only CertificateVersion history flushed operator drafts")

            event.listen(engine, "before_cursor_execute", observe)
            event.listen(reader, "before_flush", no_flush)
            try:
                data = CatalogReadService().get_gxp_certificate_version_history(
                    reader, certificate_id=cert_id,
                )
            finally:
                event.remove(engine, "before_cursor_execute", observe)
                event.remove(reader, "before_flush", no_flush)
            assert statements and set(statements) == {"SELECT"}
            assert not flushes
            assert data["latest_version_id"] == current_id
            assert data["versions"][0]["certificate_number"] == "CURRENT-V2"
            assert data["versions"][0]["is_latest_version"] is True
            assert data["versions"][1]["scopes"][0]["scope_text"] == "Scope B"
            assert cached_version.certificate_number == "UNSAVED-CURRENT"
            assert cached_version.is_latest_version is False
            assert cached_scope.scope_text == "UNSAVED-SCOPE"
            assert cached_version in reader.dirty and cached_scope in reader.dirty
            assert pending in reader.new
            reader.rollback()
        with Session(engine) as check:
            assert check.query(Company).count() == 1
            assert check.get(CertificateVersion, current_id).certificate_number == "CURRENT-V2"
    finally:
        engine.dispose()


def test_history_version_and_scopes_share_single_joined_snapshot(tmp_path):
    """Version fields and own scopes must not span two READ COMMITTED snapshots."""
    from sqlalchemy import event

    engine, _, cert_id, _case_id, _version_ids = _seed(tmp_path)
    try:
        with Session(engine) as reader:
            joined = []

            def observe(_conn, _cursor, sql, _params, _ctx, _many):
                normalized = str(sql).lower()
                if "certificate_version" in normalized or "certificate_scope" in normalized:
                    joined.append(normalized)

            event.listen(engine, "before_cursor_execute", observe)
            try:
                data = CatalogReadService().get_gxp_certificate_version_history(
                    reader, certificate_id=cert_id,
                )
            finally:
                event.remove(engine, "before_cursor_execute", observe)
            assert len(joined) == 1
            assert "join" in joined[0]
            assert data["versions"][0]["scopes"][0]["scope_key"] == "new-vi"
            assert [s["scope_key"] for s in data["versions"][1]["scopes"]] == ["old-vi", "old-en"]
    finally:
        engine.dispose()


def test_history_root_case_and_line_are_one_committed_snapshot_without_autoflush(tmp_path):
    """Stale/dirty Certificate, Case and ProductionLine cannot override persisted owners."""
    from sqlalchemy import event

    engine, _, cert_id, case_id, (_old_id, current_id) = _seed(tmp_path)
    try:
        with Session(engine) as seed:
            cert = seed.get(Certificate, cert_id)
            canonical_line = ProductionLine(
                site_id=cert.site_id, code="HISTORY-LINE",
                effective_from=date(2021, 1, 1),
            )
            seed.add(canonical_line)
            seed.flush()
            cert.production_line_id = canonical_line.id
            seed.commit()
            line_id = canonical_line.id

        with Session(engine, autoflush=True, expire_on_commit=False) as reader:
            cached_root = reader.get(Certificate, cert_id)
            cached_case = reader.get(Case, case_id)
            cached_line = reader.get(ProductionLine, line_id)
            cached_root.latest_flag = False
            cached_root.certificate_type = "GSP"
            cached_case.gxp_type = "GSP"
            cached_line.code = "UNSAVED-LINE"
            pending = Company(legal_name="Unrelated unsaved Company")
            reader.add(pending)
            statements, flushes = [], []

            def on_sql(_conn, _cursor, sql, _params, _context, _many):
                statements.append(sql.lstrip().split(None, 1)[0].upper())
                if len(statements) > 1:
                    raise AssertionError("Certificate history split across SQL snapshots")

            def on_flush(*_):
                flushes.append(True)
                raise AssertionError("Certificate history flushed operator drafts")

            event.listen(engine, "before_cursor_execute", on_sql)
            event.listen(reader, "before_flush", on_flush)
            try:
                history = CatalogReadService().get_gxp_certificate_version_history(
                    reader, certificate_id=cert_id,
                )
            finally:
                event.remove(engine, "before_cursor_execute", on_sql)
                event.remove(reader, "before_flush", on_flush)

            assert statements == ["SELECT"]
            assert flushes == []
            assert history["certificate_type"] == "GMP"
            assert history["aggregate_latest_flag"] is True
            assert history["case_id"] == case_id
            assert history["latest_version_id"] == current_id
            assert cached_root.certificate_type == "GSP"
            assert cached_root.latest_flag is False
            assert cached_case.gxp_type == "GSP"
            assert cached_line.code == "UNSAVED-LINE"
            assert cached_root in reader.dirty
            assert cached_case in reader.dirty
            assert cached_line in reader.dirty
            assert pending in reader.new
            reader.rollback()
        with Session(engine) as verify:
            assert verify.get(Certificate, cert_id).certificate_type == "GMP"
            assert verify.get(Certificate, cert_id).latest_flag is True
            assert verify.get(Case, case_id).gxp_type == "GMP"
    finally:
        engine.dispose()


@pytest.mark.parametrize("corruption", ["case_site", "case_type", "line_site"])
def test_history_fails_closed_on_committed_root_link_corruption_with_cached_owner(
    tmp_path, corruption,
):
    from sqlalchemy import update

    engine, _, cert_id, case_id, _versions = _seed(tmp_path)
    try:
        with Session(engine) as seed:
            cert = seed.get(Certificate, cert_id)
            foreign_site = seed.scalar(select(Site).where(Site.id != cert.site_id))
            if corruption == "line_site":
                line = ProductionLine(
                    site_id=cert.site_id, code="VALID-FIRST",
                    effective_from=date(2021, 1, 1),
                )
                seed.add(line)
                seed.flush()
                cert.production_line_id = line.id
                line_id = line.id
            else:
                line_id = None
            seed.commit()
        with Session(engine, autoflush=False, expire_on_commit=False) as reader:
            cached_cert = reader.get(Certificate, cert_id)
            cached_case = reader.get(Case, case_id)
            cached_line = reader.get(ProductionLine, line_id) if line_id else None
            with Session(engine) as writer:
                if corruption == "case_site":
                    writer.execute(
                        update(Case).where(Case.id == case_id).values(site_id=foreign_site.id)
                    )
                elif corruption == "case_type":
                    writer.execute(
                        update(Case).where(Case.id == case_id).values(gxp_type="GLP")
                    )
                else:
                    writer.execute(
                        update(ProductionLine).where(ProductionLine.id == line_id)
                        .values(site_id=foreign_site.id)
                    )
                writer.commit()

            with pytest.raises(HTTPException) as denied:
                CatalogReadService().get_gxp_certificate_version_history(
                    reader, certificate_id=cert_id,
                )
            assert denied.value.status_code == 409
            assert cached_cert.id == cert_id
            assert cached_case.site_id != foreign_site.id if corruption == "case_site" else True
            assert cached_line.site_id != foreign_site.id if corruption == "line_site" else True
            assert not reader.new and not reader.dirty
            reader.rollback()
    finally:
        engine.dispose()
