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
                # The final report SELECT now carries both total_count and
                # latest-version HAVING conflict guard. Inject AFTER that
                # statement executes: its rows/count must remain the original
                # PostgreSQL statement snapshot despite a later writer commit.
                # Preserve pre-fix COUNT identification for RED reproducibility.
                final_report = "report_total_count" in sql and "from certificate" in sql
                legacy_count = "count(" in sql and "from certificate" in sql and "having" not in sql
                if not injected and (final_report or legacy_count):
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
            assert injected, "writer must commit after the report count/page statement executes"
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


def test_change_request_report_count_and_page_share_committed_postgres_snapshot():
    """An independent writer cannot split report count from page rows."""
    from sqlalchemy import event, func, select

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "change_report_snapshot_" + uuid4().hex
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
            company = Company(legal_name="CR snapshot company")
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="CR snapshot site")
            setup.add(site)
            setup.flush()
            first = ChangeRequest(
                site_id=site.id, state=ChangeRequestState.RECEIVED,
                scope_label="BEFORE-CR-SNAPSHOT",
            )
            setup.add(first)
            setup.commit()
            site_id, first_id = site.id, first.id

        injected = []
        with Session(engine) as reader:
            def writer_after_count(orm_execute_state):
                sql = str(orm_execute_state.statement).lower()
                if (not injected and "count(" in sql
                        and "from change_request" in sql
                        and "report_total_count" not in sql):
                    result = orm_execute_state.invoke_statement()
                    with Session(engine) as writer:
                        writer.add(ChangeRequest(
                            site_id=site_id, state=ChangeRequestState.UNDER_REVIEW,
                            scope_label="AFTER-CR-SNAPSHOT",
                        ))
                        writer.commit()
                    injected.append(True)
                    return result
                if not injected and "report_total_count" in sql and "change_request" in sql:
                    result = orm_execute_state.invoke_statement()
                    with Session(engine) as writer:
                        writer.add(ChangeRequest(
                            site_id=site_id, state=ChangeRequestState.UNDER_REVIEW,
                            scope_label="AFTER-CR-SNAPSHOT",
                        ))
                        writer.commit()
                    injected.append(True)
                    return result
                return orm_execute_state.invoke_statement()

            event.listen(reader, "do_orm_execute", writer_after_count, retval=True)
            try:
                report = CatalogReadService().get_change_request_report(
                    reader, state=None, q=None, export=False, offset=0, limit=20,
                )
            finally:
                event.remove(reader, "do_orm_execute", writer_after_count)
            assert injected, "writer must commit after count/page read"
            assert report["total_count"] == 1
            assert [item["change_request_id"] for item in report["items"]] == [first_id]
        with Session(engine) as verify:
            assert verify.scalar(select(func.count()).select_from(ChangeRequest)) == 2
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_facility_workspace_rejects_mixed_site_case_commits_between_statements():
    """A writer changing Site and Case atomically may not yield a mixed workspace."""
    from sqlalchemy import event, select
    from backend.app.db.enums import CaseState
    from backend.app.db.models.phase1 import Case

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "facility_workspace_race_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as seed:
            company = Company(legal_name="Consistent company")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="BEFORE-ATOMIC-COMMIT")
            seed.add(site)
            seed.flush()
            case = Case(
                site_id=site.id, gxp_type="GMP", state=CaseState.PLANNED,
                legacy_inspection_code="BEFORE-ATOMIC-CASE",
            )
            seed.add(case)
            seed.commit()
            site_id, case_id = site.id, case.id

        inserted = []
        with Session(engine) as reader:
            def commit_after_site_read(orm_execute_state):
                sql = str(orm_execute_state.statement).lower()
                # Commit after the first Site-owning SQL statement returns.
                # Old source then read Case separately; fixed source joins
                # Site, Company and Case in one statement snapshot, so its
                # already-fetched values must remain mutually consistent.
                if (
                    not inserted
                    and "from site" in sql
                    and "where site.id" in sql
                ):
                    result = orm_execute_state.invoke_statement()
                    with Session(engine) as writer:
                        writer.execute(
                            Site.__table__.update()
                            .where(Site.id == site_id)
                            .values(site_name="AFTER-ATOMIC-COMMIT")
                        )
                        writer.execute(
                            Case.__table__.update()
                            .where(Case.id == case_id)
                            .values(
                                state=CaseState.CLOSED,
                                legacy_inspection_code="AFTER-ATOMIC-CASE",
                            )
                        )
                        writer.commit()
                    inserted.append(True)
                    return result
                return orm_execute_state.invoke_statement()

            event.listen(reader, "do_orm_execute", commit_after_site_read, retval=True)
            try:
                try:
                    payload = CatalogReadService().get_facility_workspace(
                        reader, site_id=site_id, gxp_type="GMP",
                        line_code=None, production_line_id=None,
                    )
                except HTTPException as exc:
                    assert exc.status_code == 409
                else:
                    matching = next(
                        item for item in payload["history"]
                        if item["source_type"] == "case" and item["id"] == case_id
                    )
                    assert (
                        payload["summary"]["facility_name"],
                        matching["state"],
                        matching["reference_code"],
                    ) in {
                        ("BEFORE-ATOMIC-COMMIT", "planned", "BEFORE-ATOMIC-CASE"),
                        ("AFTER-ATOMIC-COMMIT", "closed", "AFTER-ATOMIC-CASE"),
                    }, "workspace projected Site and Case from different committed snapshots"
            finally:
                event.remove(reader, "do_orm_execute", commit_after_site_read)
            assert inserted, "writer never committed after the initial Site SQL"
        with Session(engine) as verify:
            assert verify.scalar(
                select(Site.site_name).where(Site.id == site_id)
            ) == "AFTER-ATOMIC-COMMIT"
            assert verify.scalar(
                select(Case.state).where(Case.id == case_id)
            ) == CaseState.CLOSED
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_facility_workspace_certificate_number_and_scope_share_pg_snapshot():
    """Atomic GCN Version + Scope edit cannot yield an impossible mixed pair."""
    from sqlalchemy import event, select
    from backend.app.db.models.phase1 import CertificateScope

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "facility_scope_race_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as seed:
            company = Company(legal_name="Scope company")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Scope site")
            seed.add(site)
            seed.flush()
            certificate = Certificate(
                site_id=site.id, certificate_type="GMP", latest_flag=True,
            )
            seed.add(certificate)
            seed.flush()
            version = CertificateVersion(
                certificate_id=certificate.id, version_no=1,
                is_latest_version=True, certificate_number="BEFORE-NUMBER",
            )
            seed.add(version)
            seed.flush()
            scope = CertificateScope(
                certificate_version_id=version.id,
                scope_key="test", scope_text="BEFORE-SCOPE",
            )
            seed.add(scope)
            # Two valid scopes fan out rows in the joined snapshot; they must
            # not be mistaken for conflicting latest CertificateVersions.
            seed.add(CertificateScope(
                certificate_version_id=version.id,
                scope_key="static", scope_text="STATIC-SCOPE", sort_order=1,
            ))
            seed.commit()
            site_id, cert_id, version_id, scope_id = (
                site.id, certificate.id, version.id, scope.id,
            )

        committed = []
        with Session(engine) as reader:
            def writer_after_version_read(orm_execute_state):
                sql = str(orm_execute_state.statement).lower()
                # Both pre-fix pair SQL and a fixed GCN/Version/Scope join
                # project cert_ and version_ column aliases. Commit *after*
                # the actual statement executes, before later scope queries.
                if (
                    not committed
                    and "from certificate join certificate_version" in sql
                    and "cert_" in sql
                    and "version_" in sql
                ):
                    result = orm_execute_state.invoke_statement()
                    with Session(engine) as writer:
                        writer.execute(
                            CertificateVersion.__table__.update()
                            .where(CertificateVersion.id == version_id)
                            .values(certificate_number="AFTER-NUMBER")
                        )
                        writer.execute(
                            CertificateScope.__table__.update()
                            .where(CertificateScope.id == scope_id)
                            .values(scope_text="AFTER-SCOPE")
                        )
                        writer.commit()
                    committed.append(True)
                    return result
                return orm_execute_state.invoke_statement()

            event.listen(reader, "do_orm_execute", writer_after_version_read, retval=True)
            try:
                try:
                    payload = CatalogReadService().get_facility_workspace(
                        reader, site_id=site_id, gxp_type="GMP",
                        line_code=None, production_line_id=None,
                    )
                except HTTPException as exc:
                    assert exc.status_code == 409
                else:
                    result = payload["summary"]
                    assert (
                        result["current_certificate_number"],
                        result["certificate_scope_summary"],
                    ) in {
                        ("BEFORE-NUMBER", "BEFORE-SCOPE\nSTATIC-SCOPE"),
                        ("AFTER-NUMBER", "AFTER-SCOPE\nSTATIC-SCOPE"),
                    }, "Workspace mixed GCN number and Scope from different commits"
            finally:
                event.remove(reader, "do_orm_execute", writer_after_version_read)
            assert committed, "atomic writer never ran after Certificate/Version SQL"

        with Session(engine) as verify:
            assert verify.scalar(
                select(CertificateVersion.certificate_number)
                .where(CertificateVersion.id == version_id)
            ) == "AFTER-NUMBER"
            assert verify.scalar(
                select(CertificateScope.scope_text)
                .where(CertificateScope.id == scope_id)
            ) == "AFTER-SCOPE"
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_facility_workspace_case_certificate_change_request_share_one_atomic_snapshot():
    """No mixed Case/GCN/CR values when writer commits all three together."""
    from sqlalchemy import event, select
    from backend.app.db.enums import CaseState
    from backend.app.db.models.phase1 import Case

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "workspace_cross_owner_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as seed:
            company = Company(legal_name="Cross-owner company")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Cross-owner site")
            seed.add(site)
            seed.flush()
            case = Case(
                site_id=site.id, gxp_type="GMP", state=CaseState.PLANNED,
                legacy_inspection_code="CROSS-CASE",
            )
            certificate = Certificate(
                site_id=site.id, certificate_type="GMP", latest_flag=True,
            )
            request = ChangeRequest(
                site_id=site.id, state=ChangeRequestState.RECEIVED,
                scope_label="BEFORE-CHANGE",
            )
            seed.add_all([case, certificate, request])
            seed.flush()
            version = CertificateVersion(
                certificate_id=certificate.id, version_no=1,
                is_latest_version=True, certificate_number="BEFORE-GCN",
            )
            seed.add(version)
            seed.commit()
            site_id, case_id, version_id, request_id = (
                site.id, case.id, version.id, request.id,
            )

        writer_commits = []
        with Session(engine) as reader:
            def atomic_writer_after_owner_statement(orm_execute_state):
                sql = str(orm_execute_state.statement).lower()
                # Interleave after the first Site+Case owner statement returns.
                # An all-owner atomic projection may include CR and GCN here.
                if (
                    not writer_commits
                    and "from site" in sql
                    and "where site.id" in sql
                    and "case_" in sql
                ):
                    result = orm_execute_state.invoke_statement()
                    with Session(engine) as writer:
                        writer.execute(
                            Case.__table__.update()
                            .where(Case.id == case_id)
                            .values(state=CaseState.CLOSED)
                        )
                        writer.execute(
                            CertificateVersion.__table__.update()
                            .where(CertificateVersion.id == version_id)
                            .values(certificate_number="AFTER-GCN")
                        )
                        writer.execute(
                            ChangeRequest.__table__.update()
                            .where(ChangeRequest.id == request_id)
                            .values(scope_label="AFTER-CHANGE")
                        )
                        writer.commit()
                    writer_commits.append(True)
                    return result
                return orm_execute_state.invoke_statement()

            event.listen(reader, "do_orm_execute", atomic_writer_after_owner_statement, retval=True)
            try:
                try:
                    payload = CatalogReadService().get_facility_workspace(
                        reader, site_id=site_id, gxp_type="GMP",
                        line_code=None, production_line_id=None,
                    )
                except HTTPException as exc:
                    assert exc.status_code == 409
                else:
                    summary = payload["summary"]
                    case_history = next(
                        item for item in payload["history"]
                        if item["source_type"] == "case" and item["id"] == case_id
                    )
                    request_history = next(
                        item for item in payload["history"]
                        if item["source_type"] == "change_request" and item["id"] == request_id
                    )
                    assert (
                        case_history["state"],
                        summary["current_certificate_number"],
                        request_history["standard"],
                    ) in {
                        ("planned", "BEFORE-GCN", "BEFORE-CHANGE"),
                        ("closed", "AFTER-GCN", "AFTER-CHANGE"),
                    }, "workspace projected Case, GCN, ChangeRequest from different commits"
            finally:
                event.remove(reader, "do_orm_execute", atomic_writer_after_owner_statement)
            assert writer_commits, "atomic writer never committed after owner SQL"

        with Session(engine) as verify:
            assert verify.scalar(select(Case.state).where(Case.id == case_id)) == CaseState.CLOSED
            assert verify.scalar(
                select(CertificateVersion.certificate_number)
                .where(CertificateVersion.id == version_id)
            ) == "AFTER-GCN"
            assert verify.scalar(
                select(ChangeRequest.scope_label).where(ChangeRequest.id == request_id)
            ) == "AFTER-CHANGE"
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.parametrize("linked_kind", ["line", "inspection_event"])
def test_facility_workspace_case_and_line_or_event_use_atomic_pg_snapshot(linked_kind):
    """Separate line/event SELECT must not split a committed Case transition."""
    from datetime import datetime, timezone
    from sqlalchemy import event, select
    from backend.app.db.enums import CaseState, InspectionEventType
    from backend.app.db.models.phase1 import Case, InspectionEvent, ProductionLine

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "workspace_linked_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as seed:
            company = Company(legal_name="Atomic companion company")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Atomic companion site")
            seed.add(site)
            seed.flush()
            line = None
            if linked_kind == "line":
                line = ProductionLine(
                    site_id=site.id, code="BEFORE-LINE", effective_from=date(2026, 1, 1),
                )
                seed.add(line)
                seed.flush()
            case = Case(
                site_id=site.id, gxp_type="GMP", state=CaseState.PLANNED,
                production_line_id=None if line is None else line.id,
                legacy_inspection_code="ATOMIC-COMPANION",
            )
            seed.add(case)
            seed.flush()
            inspection_event = None
            if linked_kind == "inspection_event":
                inspection_event = InspectionEvent(
                    case_id=case.id,
                    event_type=InspectionEventType.INSPECTION_EXECUTED,
                    occurred_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                )
                seed.add(inspection_event)
            seed.commit()
            site_id, case_id = site.id, case.id
            line_id = None if line is None else line.id
            event_id = None if inspection_event is None else inspection_event.id

        writer_commits = []
        with Session(engine) as reader:
            def atomic_writer_after_owner_statement(orm_execute_state):
                sql = str(orm_execute_state.statement).lower()
                if (
                    not writer_commits
                    and "from site" in sql
                    and "where site.id" in sql
                    and "case_" in sql
                ):
                    result = orm_execute_state.invoke_statement()
                    with Session(engine) as writer:
                        writer.execute(
                            Case.__table__.update()
                            .where(Case.id == case_id)
                            .values(state=CaseState.CLOSED)
                        )
                        if linked_kind == "line":
                            writer.execute(
                                ProductionLine.__table__.update()
                                .where(ProductionLine.id == line_id)
                                .values(code="AFTER-LINE")
                            )
                        else:
                            writer.execute(
                                InspectionEvent.__table__.update()
                                .where(InspectionEvent.id == event_id)
                                .values(occurred_at=datetime(2026, 2, 3, tzinfo=timezone.utc))
                            )
                        writer.commit()
                    writer_commits.append(True)
                    return result
                return orm_execute_state.invoke_statement()

            event.listen(reader, "do_orm_execute", atomic_writer_after_owner_statement, retval=True)
            try:
                try:
                    payload = CatalogReadService().get_facility_workspace(
                        reader, site_id=site_id, gxp_type="GMP",
                        line_code=None, production_line_id=line_id,
                    )
                except HTTPException as exc:
                    assert exc.status_code == 409
                else:
                    summary = payload["summary"]
                    history = next(
                        row for row in payload["history"]
                        if row["source_type"] == "case" and row["id"] == case_id
                    )
                    if linked_kind == "line":
                        assert (
                            history["state"], summary["selected_line_code"]
                        ) in {
                            ("planned", "BEFORE-LINE"), ("closed", "AFTER-LINE"),
                        }, "workspace combined Case before commit with line after commit"
                    else:
                        assert (
                            history["state"], history["occurred_on"]
                        ) in {
                            ("planned", date(2026, 1, 2)),
                            ("closed", date(2026, 2, 3)),
                        }, "workspace combined Case before commit with event date after commit"
            finally:
                event.remove(reader, "do_orm_execute", atomic_writer_after_owner_statement)
            assert writer_commits, "writer never committed after owner SQL"

        with Session(engine) as verify:
            assert verify.scalar(select(Case.state).where(Case.id == case_id)) == CaseState.CLOSED
            if linked_kind == "line":
                assert verify.scalar(
                    select(ProductionLine.code).where(ProductionLine.id == line_id)
                ) == "AFTER-LINE"
            else:
                assert verify.scalar(
                    select(InspectionEvent.occurred_at)
                    .where(InspectionEvent.id == event_id)
                ).date() == date(2026, 2, 3)
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.parametrize("tamper", ["site", "gxp_type"])
@pytest.mark.parametrize("surface", ["workspace", "search"])
def test_read_detects_invalid_certificate_case_link_committed_after_quarantine_preflight(tamper, surface):
    """Concurrent owner corruption cannot escape workspace or search read owners."""
    from sqlalchemy import event, select
    from backend.app.db.enums import CaseState
    from backend.app.db.models.phase1 import Case

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "workspace_late_corrupt_owner_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as seed:
            company = Company(legal_name="Owner integrity company")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Owner integrity site")
            unrelated = Site(company_id=company.id, site_name="Other site")
            seed.add_all([site, unrelated])
            seed.flush()
            case = Case(
                site_id=site.id, gxp_type="GMP", state=CaseState.CERTIFIED,
                legacy_inspection_code="INTEGRITY-CASE",
            )
            seed.add(case)
            seed.flush()
            cert = Certificate(
                site_id=site.id, case_id=case.id,
                certificate_type="GMP", latest_flag=True,
                issuance_basis="inspection_case",
            )
            seed.add(cert)
            seed.flush()
            seed.add(CertificateVersion(
                certificate_id=cert.id, version_no=1,
                certificate_number="CASE-LINK-VALID-BEFORE",
                is_latest_version=True,
            ))
            seed.commit()
            site_id, other_site_id, case_id, cert_id = (
                site.id, unrelated.id, case.id, cert.id,
            )

        committed = []
        with Session(engine) as reader:
            def mutate_after_quarantine_preflight(orm_execute_state):
                sql = str(orm_execute_state.statement).lower()
                old_preflight = (
                    "from certificate left outer join" in sql
                    and "case_legacy_id" in sql
                    and "cert_legacy_id" in sql
                )
                # SQLAlchemy binds literal("certificate_owner") as a
                # parameter, so its value is NOT text in str(statement).
                # The stable final-source subquery alias identifies the
                # combined statement without inspecting a bound value.
                final_snapshot = (
                    "facility_workspace_atomic_read" in sql
                    and "from certificate" in sql
                )
                search_snapshot = (
                    surface == "search"
                    and "from certificate left outer join" in sql
                    and "source_latest_flag" in sql
                    and "cert_legacy_id" in sql
                )
                atomic_snapshot = final_snapshot or search_snapshot
                if not committed and (old_preflight or atomic_snapshot):
                    # RED: writer after the old separate preflight.
                    # GREEN: writer before the one Certificate owner SQL.
                    result = (
                        None if atomic_snapshot
                        else orm_execute_state.invoke_statement()
                    )
                    with Session(engine) as writer:
                        values = (
                            {"site_id": other_site_id}
                            if tamper == "site"
                            else {"gxp_type": "GLP"}
                        )
                        writer.execute(
                            Case.__table__.update()
                            .where(Case.id == case_id)
                            .values(**values)
                        )
                        writer.commit()
                    committed.append(True)
                    return (
                        orm_execute_state.invoke_statement()
                        if atomic_snapshot else result
                    )
                return orm_execute_state.invoke_statement()

            event.listen(reader, "do_orm_execute", mutate_after_quarantine_preflight, retval=True)
            try:
                with pytest.raises(HTTPException) as exc:
                    if surface == "workspace":
                        CatalogReadService().get_facility_workspace(
                            reader, site_id=site_id, gxp_type="GMP",
                            line_code=None, production_line_id=None,
                        )
                    else:
                        CatalogReadService().search_facilities(
                            reader, site_id=site_id, gxp_type="GMP",
                        )
                assert exc.value.status_code == 409
                assert "linked Case" in str(exc.value.detail)
            finally:
                event.remove(reader, "do_orm_execute", mutate_after_quarantine_preflight)
            assert committed, "writer never committed at the workspace snapshot boundary"

        with Session(engine) as verify:
            assert verify.scalar(
                select(Case.site_id).where(Case.id == case_id)
            ) == (other_site_id if tamper == "site" else site_id)
            assert verify.scalar(
                select(Case.gxp_type).where(Case.id == case_id)
            ) == ("GLP" if tamper == "gxp_type" else "GMP")
            assert verify.scalar(
                select(Certificate.case_id).where(Certificate.id == cert_id)
            ) == case_id
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_search_case_and_certificate_number_share_committed_postgres_snapshot():
    """Search must not combine Case BEFORE with GCN AFTER one atomic commit."""
    from sqlalchemy import event, select
    from backend.app.db.enums import CaseState
    from backend.app.db.models.phase1 import Case

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "search_case_gcn_snapshot_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as seed:
            company = Company(legal_name="Cross-group snapshot company")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Cross-group snapshot site")
            seed.add(site)
            seed.flush()
            case = Case(
                site_id=site.id, gxp_type="GMP", state=CaseState.PLANNED,
                legacy_inspection_code="CROSS-GROUP-CASE",
            )
            seed.add(case)
            seed.flush()
            cert = Certificate(
                site_id=site.id, case_id=case.id, certificate_type="GMP",
                latest_flag=True, issuance_basis="inspection_case",
            )
            seed.add(cert)
            seed.flush()
            version = CertificateVersion(
                certificate_id=cert.id, version_no=1,
                certificate_number="BEFORE-GCN", is_latest_version=True,
            )
            seed.add(version)
            seed.commit()
            site_id, case_id, version_id = site.id, case.id, version.id

        writer_commits = []
        with Session(engine) as reader:
            def commit_after_legacy_case_select(orm_execute_state):
                sql = str(orm_execute_state.statement).lower()
                # RED owner: Case scalar SELECT precedes independent Version SELECT.
                # An atomic source owner can instead be caught before its final
                # SQL, so the writer commits before one complete read snapshot.
                legacy_case = (
                    ('from "case"' in sql or 'from case' in sql)
                    and "legacy_inspection_code" in sql
                    and "certificate_version" not in sql
                )
                atomic_source = (
                    "search_atomic_read" in sql
                    and "certificate_version" in sql
                )
                if not writer_commits and (legacy_case or atomic_source):
                    result = None if atomic_source else orm_execute_state.invoke_statement()
                    with Session(engine) as writer:
                        writer.execute(
                            Case.__table__.update()
                            .where(Case.id == case_id)
                            .values(state=CaseState.CLOSED)
                        )
                        writer.execute(
                            CertificateVersion.__table__.update()
                            .where(CertificateVersion.id == version_id)
                            .values(certificate_number="AFTER-GCN")
                        )
                        writer.commit()
                    writer_commits.append(True)
                    return (
                        orm_execute_state.invoke_statement()
                        if atomic_source else result
                    )
                return orm_execute_state.invoke_statement()

            event.listen(reader, "do_orm_execute", commit_after_legacy_case_select, retval=True)
            try:
                try:
                    payload = CatalogReadService().search_facilities(
                        reader, site_id=site_id, gxp_type="GMP",
                    )
                except HTTPException as exc:
                    assert exc.status_code == 409
                else:
                    rows = [
                        row for row in payload["items"]
                        if row["site_id"] == site_id and row["gxp_type"] == "GMP"
                    ]
                    assert len(rows) == 1
                    pair = (rows[0]["current_state"], rows[0]["current_certificate_number"])
                    assert pair in {
                        ("planned", "BEFORE-GCN"),
                        ("closed", "AFTER-GCN"),
                    }, "Search combined Case BEFORE with CertificateVersion AFTER"
            finally:
                event.remove(reader, "do_orm_execute", commit_after_legacy_case_select)
            assert writer_commits, "writer never committed at the Search read boundary"

        with Session(engine) as verify:
            assert verify.scalar(
                select(Case.state).where(Case.id == case_id)
            ) == CaseState.CLOSED
            assert verify.scalar(
                select(CertificateVersion.certificate_number)
                .where(CertificateVersion.id == version_id)
            ) == "AFTER-GCN"
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_search_certificate_number_and_scope_share_committed_postgres_snapshot():
    """Search cannot combine a GCN number and Scope from opposite sides of one commit."""
    from sqlalchemy import event, select
    from backend.app.db.models.phase1 import CertificateScope

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "search_gcn_scope_snapshot_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as seed:
            company = Company(legal_name="Scope snapshot company")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Scope snapshot site")
            seed.add(site)
            seed.flush()
            certificate = Certificate(
                site_id=site.id, certificate_type="GMP", latest_flag=True,
                issuance_basis="administrative_no_inspection",
            )
            seed.add(certificate)
            seed.flush()
            version = CertificateVersion(
                certificate_id=certificate.id, version_no=1,
                certificate_number="BEFORE-GCN", is_latest_version=True,
            )
            seed.add(version)
            seed.flush()
            scope = CertificateScope(
                certificate_version_id=version.id,
                scope_text="BEFORE-SCOPE", sort_order=0,
            )
            seed.add(scope)
            seed.commit()
            site_id, version_id, scope_id = site.id, version.id, scope.id

        commits = []
        with Session(engine) as reader:
            def commit_at_version_scope_boundary(orm_execute_state):
                sql = str(orm_execute_state.statement).lower()
                version_snapshot = (
                    "search_atomic_read" in sql
                    and "certificate_version" in sql
                )
                scope_in_same_snapshot = version_snapshot and "certificate_scope" in sql
                if not commits and version_snapshot:
                    # RED: capture old Version statement, commit, then read new
                    # Scope in the later statement. GREEN: commit before the
                    # single Version/Scope source statement executes.
                    captured = (
                        None if scope_in_same_snapshot
                        else orm_execute_state.invoke_statement()
                    )
                    with Session(engine) as writer:
                        writer.execute(
                            CertificateVersion.__table__.update()
                            .where(CertificateVersion.id == version_id)
                            .values(certificate_number="AFTER-GCN")
                        )
                        writer.execute(
                            CertificateScope.__table__.update()
                            .where(CertificateScope.id == scope_id)
                            .values(scope_text="AFTER-SCOPE")
                        )
                        writer.commit()
                    commits.append(True)
                    return (
                        orm_execute_state.invoke_statement()
                        if scope_in_same_snapshot else captured
                    )
                return orm_execute_state.invoke_statement()

            event.listen(reader, "do_orm_execute", commit_at_version_scope_boundary, retval=True)
            try:
                payload = CatalogReadService().search_facilities(
                    reader, site_id=site_id, gxp_type="GMP",
                )
                rows = [
                    row for row in payload["items"]
                    if row["site_id"] == site_id and row["gxp_type"] == "GMP"
                ]
                assert len(rows) == 1
                pair = (
                    rows[0]["current_certificate_number"],
                    rows[0]["certificate_scope_summary"],
                )
                assert pair in {
                    ("BEFORE-GCN", "BEFORE-SCOPE"),
                    ("AFTER-GCN", "AFTER-SCOPE"),
                }, "Search combined GCN BEFORE with Scope AFTER one atomic commit"
            finally:
                event.remove(reader, "do_orm_execute", commit_at_version_scope_boundary)
            assert commits, "writer never committed at the Version/Scope boundary"

        with Session(engine) as verify:
            assert verify.scalar(
                select(CertificateVersion.certificate_number)
                .where(CertificateVersion.id == version_id)
            ) == "AFTER-GCN"
            assert verify.scalar(
                select(CertificateScope.scope_text)
                .where(CertificateScope.id == scope_id)
            ) == "AFTER-SCOPE"
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_search_site_and_case_share_committed_postgres_snapshot():
    """Search must not show Site BEFORE together with Case AFTER one commit."""
    from sqlalchemy import event, select
    from backend.app.db.enums import CaseState
    from backend.app.db.models.phase1 import Case

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "search_site_case_snapshot_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as seed:
            company = Company(legal_name="Site Case snapshot company")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="BEFORE-SITE")
            seed.add(site)
            seed.flush()
            case = Case(
                site_id=site.id, gxp_type="GMP", state=CaseState.PLANNED,
                legacy_inspection_code="SITE-CASE-SNAPSHOT",
            )
            seed.add(case)
            seed.commit()
            site_id, case_id = site.id, case.id

        commits = []
        with Session(engine) as reader:
            def writer_at_site_case_boundary(orm_execute_state):
                sql = str(orm_execute_state.statement).lower()
                # Legacy Search reads Site scalars separately before its
                # Case/Version/Scope tagged statement.
                old_site = (
                    "from site" in sql
                    and "site_name" in sql
                    and "search_atomic_read" not in sql
                )
                new_atomic_source = (
                    "search_atomic_read" in sql
                    and "site_site_name" in sql
                    and "case_state" in sql
                )
                if not commits and (old_site or new_atomic_source):
                    result = (
                        None if new_atomic_source
                        else orm_execute_state.invoke_statement()
                    )
                    with Session(engine) as writer:
                        writer.execute(
                            Site.__table__.update()
                            .where(Site.id == site_id)
                            .values(site_name="AFTER-SITE")
                        )
                        writer.execute(
                            Case.__table__.update()
                            .where(Case.id == case_id)
                            .values(state=CaseState.CLOSED)
                        )
                        writer.commit()
                    commits.append(True)
                    return (
                        orm_execute_state.invoke_statement()
                        if new_atomic_source else result
                    )
                return orm_execute_state.invoke_statement()

            event.listen(reader, "do_orm_execute", writer_at_site_case_boundary, retval=True)
            try:
                payload = CatalogReadService().search_facilities(
                    reader, site_id=site_id, gxp_type="GMP",
                )
                matches = [
                    row for row in payload["items"]
                    if row["site_id"] == site_id and row["gxp_type"] == "GMP"
                ]
                assert len(matches) == 1
                pair = (matches[0]["facility_name"], matches[0]["current_state"])
                assert pair in {
                    ("BEFORE-SITE", "planned"),
                    ("AFTER-SITE", "closed"),
                }, "Search combined persisted Site BEFORE with Case AFTER"
            finally:
                event.remove(reader, "do_orm_execute", writer_at_site_case_boundary)
            assert commits, "independent writer did not commit at the Search owner boundary"

        with Session(engine) as verify:
            assert verify.scalar(select(Site.site_name).where(Site.id == site_id)) == "AFTER-SITE"
            assert verify.scalar(select(Case.state).where(Case.id == case_id)) == CaseState.CLOSED
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_search_site_and_change_request_filter_share_committed_postgres_snapshot():
    """Search may not match a post-commit Change Request on a pre-commit Site."""
    from sqlalchemy import event, select

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "search_site_change_snapshot_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as seed:
            company = Company(legal_name="Site Change snapshot company")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="BEFORE-SITE")
            seed.add(site)
            seed.flush()
            request = ChangeRequest(
                site_id=site.id, state=ChangeRequestState.RECEIVED,
                scope_label="Tracked Change",
            )
            seed.add(request)
            seed.commit()
            site_id, request_id = site.id, request.id

        commits = []
        with Session(engine) as reader:
            def writer_at_change_filter_boundary(orm_execute_state):
                sql = str(orm_execute_state.statement).lower()
                owner_snapshot = (
                    "search_atomic_read" in sql
                    and "site_site_name" in sql
                    and "case_state" in sql
                )
                change_in_snapshot = owner_snapshot and "change_state" in sql
                if not commits and owner_snapshot:
                    # RED: capture Site snapshot, then commit before the
                    # separate Change Request SELECT. GREEN: writer commits
                    # before the shared Site/Change statement executes.
                    result = (
                        None if change_in_snapshot
                        else orm_execute_state.invoke_statement()
                    )
                    with Session(engine) as writer:
                        writer.execute(
                            Site.__table__.update()
                            .where(Site.id == site_id)
                            .values(site_name="AFTER-SITE")
                        )
                        writer.execute(
                            ChangeRequest.__table__.update()
                            .where(ChangeRequest.id == request_id)
                            .values(state=ChangeRequestState.ACCEPTED)
                        )
                        writer.commit()
                    commits.append(True)
                    return (
                        orm_execute_state.invoke_statement()
                        if change_in_snapshot else result
                    )
                return orm_execute_state.invoke_statement()

            event.listen(reader, "do_orm_execute", writer_at_change_filter_boundary, retval=True)
            try:
                payload = CatalogReadService().search_facilities(
                    reader, site_id=site_id,
                    change_request_states=["accepted"],
                )
                rows = [row for row in payload["items"] if row["site_id"] == site_id]
                assert len(rows) <= 1
                assert not rows or rows[0]["facility_name"] == "AFTER-SITE", (
                    "Search matched post-commit ChangeRequest against pre-commit Site"
                )
            finally:
                event.remove(reader, "do_orm_execute", writer_at_change_filter_boundary)
            assert commits, "independent writer did not commit at Search statement boundary"

        with Session(engine) as verify:
            assert verify.scalar(select(Site.site_name).where(Site.id == site_id)) == "AFTER-SITE"
            assert verify.scalar(
                select(ChangeRequest.state).where(ChangeRequest.id == request_id)
            ) == ChangeRequestState.ACCEPTED
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_search_certificate_root_and_latest_version_share_postgres_snapshot():
    """Root line_code and latest GCN number must come from one committed state."""
    from sqlalchemy import event, select

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "search_root_version_snapshot_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as seed:
            company = Company(legal_name="Root Version snapshot company")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Root Version snapshot site")
            seed.add(site)
            seed.flush()
            cert = Certificate(
                site_id=site.id, certificate_type="GMP", latest_flag=True,
                line_code="BEFORE-LINE", issuance_basis="administrative_no_inspection",
            )
            seed.add(cert)
            seed.flush()
            version = CertificateVersion(
                certificate_id=cert.id, version_no=1,
                certificate_number="BEFORE-GCN", is_latest_version=True,
            )
            seed.add(version)
            seed.commit()
            site_id, certificate_id, version_id = site.id, cert.id, version.id

        commits = []
        with Session(engine) as reader:
            def writer_at_root_version_boundary(orm_execute_state):
                sql = str(orm_execute_state.statement).lower()
                atomic_source = (
                    "search_atomic_read" in sql
                    and "certificate_version" in sql
                )
                root_in_atomic = atomic_source and "cert_source_latest_flag" in sql
                if not commits and atomic_source:
                    # RED: Version statement completes before the writer;
                    # subsequent Certificate root SELECT sees post-commit.
                    # GREEN: writer commits BEFORE shared source statement.
                    captured = (
                        None if root_in_atomic
                        else orm_execute_state.invoke_statement()
                    )
                    with Session(engine) as writer:
                        writer.execute(
                            Certificate.__table__.update()
                            .where(Certificate.id == certificate_id)
                            .values(line_code="AFTER-LINE")
                        )
                        writer.execute(
                            CertificateVersion.__table__.update()
                            .where(CertificateVersion.id == version_id)
                            .values(certificate_number="AFTER-GCN")
                        )
                        writer.commit()
                    commits.append(True)
                    return (
                        orm_execute_state.invoke_statement()
                        if root_in_atomic else captured
                    )
                return orm_execute_state.invoke_statement()

            event.listen(reader, "do_orm_execute", writer_at_root_version_boundary, retval=True)
            try:
                payload = CatalogReadService().search_facilities(
                    reader, site_id=site_id, gxp_type="GMP",
                )
                rows = [row for row in payload["items"] if row["site_id"] == site_id]
                assert len(rows) == 1
                pair = (rows[0]["line_code"], rows[0]["current_certificate_number"])
                assert pair in {
                    ("BEFORE-LINE", "BEFORE-GCN"),
                    ("AFTER-LINE", "AFTER-GCN"),
                }, "Search combined Certificate root AFTER with latest Version BEFORE"
            finally:
                event.remove(reader, "do_orm_execute", writer_at_root_version_boundary)
            assert commits, "independent writer never committed at Search read boundary"

        with Session(engine) as verify:
            assert verify.scalar(
                select(Certificate.line_code).where(Certificate.id == certificate_id)
            ) == "AFTER-LINE"
            assert verify.scalar(
                select(CertificateVersion.certificate_number)
                .where(CertificateVersion.id == version_id)
            ) == "AFTER-GCN"
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
