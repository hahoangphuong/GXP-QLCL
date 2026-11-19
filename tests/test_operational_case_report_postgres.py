"""Exercise the report against an isolated schema in the disposable test database."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Company, Site
from backend.app.services.catalog import CatalogReadService


def test_case_report_postgres_filters_and_full_export():
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "case_report_" + uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            company = Company(legal_name="Công ty thử nghiệm")
            session.add(company)
            session.flush()
            site = Site(company_id=company.id, site_name="Cơ sở tổng hợp")
            session.add(site)
            session.flush()
            session.add_all([Case(site_id=site.id, gxp_type="GMP", state=CaseState.PLANNED, opened_year=2026),
                             Case(site_id=site.id, gxp_type="GMP", state=CaseState.CLOSED, opened_year=2026)])
            session.commit()
            result = CatalogReadService().get_case_report(session, gxp_type="GMP", state=None, q="tổng hợp",
                opened_year=2026, inspection_queue=True, export=True, offset=0, limit=100)
            assert result["total_count"] == 1
            assert result["items"][0]["state"] == "planned"
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_case_report_count_and_page_use_one_committed_postgres_statement_snapshot():
    """Concurrent committed Case cannot enter page without the matching total."""
    from sqlalchemy import event, func, select

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires disposable PostgreSQL gxp_qlcl_test")
    if make_url(url).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted")
    schema = "case_report_snapshot_" + uuid4().hex
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
            company = Company(legal_name="Case snapshot company")
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="Case snapshot site")
            setup.add(site)
            setup.flush()
            first = Case(site_id=site.id, gxp_type="GMP", state=CaseState.PLANNED, opened_year=2026)
            setup.add(first)
            setup.commit()
            site_id, first_id = site.id, first.id

        committed_after_read = []
        with Session(engine) as reader:
            def add_case_after_count_or_final_statement(orm_execute_state):
                sql = str(orm_execute_state.statement).lower()
                # Both the original separate COUNT and the fixed combined
                # count/page SELECT contain count( and the Case table. The
                # writer commits after that statement was executed, not before.
                if not committed_after_read and "count(" in sql and 'case' in sql:
                    result = orm_execute_state.invoke_statement()
                    with Session(engine) as writer:
                        writer.add(Case(
                            site_id=site_id, gxp_type="GMP",
                            state=CaseState.PLANNED, opened_year=2026,
                        ))
                        writer.commit()
                    committed_after_read.append(True)
                    return result
                return orm_execute_state.invoke_statement()

            event.listen(reader, "do_orm_execute", add_case_after_count_or_final_statement, retval=True)
            try:
                result = CatalogReadService().get_case_report(
                    reader, gxp_type="GMP", state=None, q=None, opened_year=2026,
                    inspection_queue=False, export=False, offset=0, limit=20,
                )
            finally:
                event.remove(reader, "do_orm_execute", add_case_after_count_or_final_statement)
            assert committed_after_read, "writer did not commit after report statement"
            assert result["total_count"] == 1
            assert [row["case_id"] for row in result["items"]] == [first_id]
        with Session(engine) as verify:
            assert verify.scalar(select(func.count()).select_from(Case)) == 2
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
