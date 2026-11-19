"""Canonical report queries against an isolated disposable PostgreSQL schema."""
import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import (
    Certificate, CertificateVersion, ChangeRequest, Company, Site,
)
from backend.app.services.catalog import CatalogReadService


def test_canonical_record_reports_disposable_postgres():
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "record_report_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            company = Company(legal_name="Công ty kiểm tra")
            db.add(company)
            db.flush()
            site = Site(company_id=company.id, site_name="Cơ sở kiểm tra")
            db.add(site)
            db.flush()
            current = Certificate(site_id=site.id, certificate_type="GMP", latest_flag=True)
            replaced = Certificate(site_id=site.id, certificate_type="GMP", latest_flag=False)
            db.add_all([current, replaced])
            db.flush()
            db.add_all([
                CertificateVersion(certificate_id=current.id, version_no=1,
                    is_latest_version=True, certificate_number="GCN-PG",
                    expiry_date=date.today() + timedelta(days=25)),
                CertificateVersion(certificate_id=replaced.id, version_no=1,
                    is_latest_version=True, certificate_number="GCN-REPLACED",
                    expiry_date=date.today() + timedelta(days=15)),
                ChangeRequest(site_id=site.id, state=ChangeRequestState.RECEIVED,
                    scope_label="Đổi tên"),
                ChangeRequest(site_id=site.id, state=ChangeRequestState.UNDER_REVIEW,
                    scope_label="Đổi địa chỉ"),
            ])
            db.commit()
            service = CatalogReadService()
            certificates = service.get_certificate_report(db, gxp_type="GMP", q=None,
                expiry_days=30, export=True, offset=0, limit=100)
            assert certificates["total_count"] == 1
            assert certificates["items"][0]["certificate_id"] == current.id
            assert certificates["items"][0]["certificate_number"] == "GCN-PG"
            # GSP/GDP are read-only Certificate types, not GMP editing aliases.
            gsp = Certificate(site_id=site.id, certificate_type="GSP", latest_flag=True)
            gdp = Certificate(site_id=site.id, certificate_type="GDP", latest_flag=True)
            db.add_all([gsp, gdp])
            db.flush()
            db.add_all([
                CertificateVersion(certificate_id=gsp.id, version_no=1,
                    is_latest_version=True, certificate_number="GSP-PG"),
                CertificateVersion(certificate_id=gdp.id, version_no=1,
                    is_latest_version=True, certificate_number="GDP-PG"),
            ])
            db.flush()
            for cert_type, expected_id in (("GSP", gsp.id), ("GDP", gdp.id)):
                page = service.get_certificate_report(db, gxp_type=cert_type, q=None,
                    expiry_days=None, export=True, offset=0, limit=100)
                assert page["total_count"] == 1
                assert page["items"][0]["certificate_id"] == expected_id
                assert page["items"][0]["gxp_type"] == cert_type
                assert page["items"][0]["site_id"] == site.id
            changes = service.get_change_request_report(db, state=None, q="kiểm tra",
                export=True, offset=0, limit=100)
            assert changes["total_count"] == 2
            assert len({x["change_request_id"] for x in changes["items"]}) == 2
            assert all("gxp_type" not in item for item in changes["items"])
            db.add(CertificateVersion(certificate_id=current.id, version_no=2,
                is_latest_version=True, certificate_number="GCN-CONFLICT",
                expiry_date=date.today() + timedelta(days=300)))
            db.flush()
            with pytest.raises(HTTPException) as conflict:
                service.get_certificate_report(db, gxp_type="GMP", q=None,
                    expiry_days=30, export=True, offset=0, limit=100)
            assert conflict.value.status_code == 409
            with pytest.raises(HTTPException) as detail_conflict:
                service.get_gxp_certificate_detail(db, certificate_id=current.id)
            assert detail_conflict.value.status_code == 409
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_certificate_report_count_and_page_share_one_postgres_statement_snapshot():
    """A concurrent committed insert may not split page rows from their count."""
    from sqlalchemy import event, func, select

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "report_snapshot_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as setup:
            company = Company(legal_name="Snapshot company")
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="Snapshot site")
            setup.add(site)
            setup.flush()
            first = Certificate(site_id=site.id, certificate_type="GMP", latest_flag=True)
            setup.add(first)
            setup.flush()
            setup.add(CertificateVersion(
                certificate_id=first.id, version_no=1, is_latest_version=True,
                certificate_number="BEFORE-SNAPSHOT",
            ))
            setup.commit()
            site_id, first_id = site.id, first.id

        injected = []
        with Session(engine) as reader:
            def insert_after_count(orm_execute_state):
                sql = str(orm_execute_state.statement).lower()
                # Skip latest-version conflict preflight, which has HAVING.
                # The legacy independent COUNT statement executes before the
                # page SELECT, while the fixed statement contains both count
                # and page and is already executing against one PG snapshot.
                if not injected and "count(" in sql and "from certificate" in sql and "having" not in sql:
                    result = orm_execute_state.invoke_statement()
                    with Session(engine) as writer:
                        second = Certificate(
                            site_id=site_id, certificate_type="GMP", latest_flag=True,
                        )
                        writer.add(second)
                        writer.flush()
                        writer.add(CertificateVersion(
                            certificate_id=second.id, version_no=1,
                            is_latest_version=True, certificate_number="AFTER-SNAPSHOT",
                        ))
                        writer.commit()
                    injected.append(True)
                    return result
                return orm_execute_state.invoke_statement()

            event.listen(reader, "do_orm_execute", insert_after_count, retval=True)
            try:
                report = CatalogReadService().get_certificate_report(
                    reader, gxp_type="GMP", q=None, expiry_days=None,
                    export=False, offset=0, limit=20,
                )
            finally:
                event.remove(reader, "do_orm_execute", insert_after_count)
            assert injected, "writer must commit immediately after the count SQL begins"
            assert report["total_count"] == 1
            assert [item["certificate_id"] for item in report["items"]] == [first_id]
        with Session(engine) as verify:
            assert verify.scalar(select(func.count()).select_from(Certificate)) == 2
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.parametrize("export,offset", [(False, 0), (False, 2), (True, 0)])
def test_certificate_report_detects_latest_conflict_committed_after_preflight(export, offset):
    """Conflicts committed between preflight and row snapshot fail closed."""
    from sqlalchemy import event, func, select

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")

    schema = "report_late_version_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as setup:
            company = Company(legal_name="Concurrent version company")
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="Concurrent version site")
            setup.add(site)
            setup.flush()
            certificate = Certificate(site_id=site.id, certificate_type="GMP", latest_flag=True)
            setup.add(certificate)
            setup.flush()
            setup.add(CertificateVersion(
                certificate_id=certificate.id, version_no=1,
                is_latest_version=True, certificate_number="BEFORE-CONFLICT",
            ))
            setup.commit()
            certificate_id = certificate.id

        injected = []
        with Session(engine) as reader:
            def insert_after_conflict_preflight(orm_execute_state):
                sql = str(orm_execute_state.statement).lower()
                if not injected and "having" in sql and "certificate_version" in sql:
                    result = orm_execute_state.invoke_statement()
                    with Session(engine) as writer:
                        writer.add(CertificateVersion(
                            certificate_id=certificate_id, version_no=2,
                            is_latest_version=True, certificate_number="LATE-CONFLICT",
                        ))
                        writer.commit()
                    injected.append(True)
                    return result
                return orm_execute_state.invoke_statement()

            event.listen(reader, "do_orm_execute", insert_after_conflict_preflight, retval=True)
            try:
                with pytest.raises(HTTPException) as exc:
                    CatalogReadService().get_certificate_report(
                        reader, gxp_type="GMP", q=None, expiry_days=None,
                        export=export, offset=offset, limit=1,
                    )
                assert exc.value.status_code == 409
                assert "latest" in str(exc.value.detail).lower()
            finally:
                event.remove(reader, "do_orm_execute", insert_after_conflict_preflight)
            assert injected, "writer must commit between conflict preflight and report rows"
        with Session(engine) as verify:
            assert verify.scalar(
                select(func.count()).select_from(CertificateVersion)
                .where(CertificateVersion.certificate_id == certificate_id)
            ) == 2
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
