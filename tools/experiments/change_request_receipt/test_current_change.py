"""Observed current Change Request behavior on isolated PostgreSQL schemas."""
import os
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from backend.app.auth import build_authenticated_user, ROLE_PERMISSIONS
from backend.app.db.base import Base
from backend.app.db.models.phase1 import AuditEvent, ChangeRequest, Company, Site
from backend.app.services.workflow import CaseWorkflowService

@pytest.fixture
def system():
    url=os.environ['CODEX_PROOF_DB_URL']
    assert url.startswith('postgresql+psycopg://codex_probe:') and '@127.0.0.1:55439/gxp_qlcl_test' in url
    admin=create_engine(url); schema='codex_current_'+uuid4().hex
    with admin.begin() as c: c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine=create_engine(url,connect_args={'options':f'-csearch_path={schema}'})
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        company=Company(legal_name='Synthetic');s.add(company);s.flush()
        sites=[Site(company_id=company.id,site_name='Synthetic A'),Site(company_id=company.id,site_name='Synthetic B')];s.add_all(sites);s.commit();ids=[x.id for x in sites]
    try: yield engine,ids
    finally:
        engine.dispose()
        with admin.begin() as c: c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()

def create(s,site,actor):
    user=build_authenticated_user(actor,'admin',permissions=ROLE_PERMISSIONS['admin'])
    return CaseWorkflowService().create_change_request(s,site_id=site,scope_label='Synthetic',description=None,submitted_on=None,requester_name=None,reason=None,user=user)

def tally(s):
    return s.scalar(select(func.count(ChangeRequest.id))),s.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.action=='change_request.create'))

def test_two_competing_same_site_creates_serialize_but_both_commit(system):
    engine,(site,_)=system
    with Session(engine) as a, Session(engine) as b:
        first=create(a,site,'actor-a')
        b.execute(text("SET LOCAL lock_timeout='250ms'"))
        with pytest.raises(OperationalError) as exc: create(b,site,'actor-b')
        assert exc.value.orig.sqlstate=='55P03'
        b.rollback();a.commit()
        second=create(b,site,'actor-b');b.commit()
        assert first['change_request_id'] != second['change_request_id']
    with Session(engine) as s: assert tally(s)==(2,2)

def test_rollback_after_flushed_audit_discards_business_and_audit(system):
    engine,(site,_)=system
    with Session(engine) as s:
        create(s,site,'actor-a');assert tally(s)==(1,1);s.rollback()
    with Session(engine) as s: assert tally(s)==(0,0)

def test_same_actor_same_payload_different_sites_creates_independent_records(system):
    engine,sites=system
    with Session(engine) as s:
        for site in sites: create(s,site,'actor-a');s.commit()
    with Session(engine) as s:
        assert tally(s)==(2,2)
        assert set(s.scalars(select(ChangeRequest.site_id)))==set(sites)

def test_concurrent_two_actors_wait_then_both_create(system):
    import threading, time
    from concurrent.futures import ThreadPoolExecutor
    engine,(site,_)=system
    started=threading.Event(); holder={}
    def contender():
        with Session(engine) as session:
            holder['pid']=session.scalar(text('select pg_backend_pid()'))
            started.set()
            result=create(session,site,'actor-b')
            session.commit()
            return result['change_request_id']
    with Session(engine) as first:
        first_id=create(first,site,'actor-a')['change_request_id']
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(contender)
            try:
                assert started.wait(5)
                deadline=time.monotonic()+5
                blocked=False
                while time.monotonic()<deadline:
                    with engine.connect() as observer:
                        blocked=bool(observer.scalar(text('select cardinality(pg_blocking_pids(:pid)) > 0'),{'pid':holder['pid']}))
                    if blocked: break
                    time.sleep(.02)
                assert blocked, 'second real service call did not wait on the first transaction'
            finally:
                first.commit()
            second_id=future.result(timeout=10)
    with Session(engine) as session:
        assert first_id != second_id
        assert tally(session)==(2,2)
