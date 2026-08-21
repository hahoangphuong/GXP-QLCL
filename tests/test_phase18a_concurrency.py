from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from backend.app.api.session import commit_or_409, get_session_from_request_factory
from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import CapaCycle, Case, Certificate, CertificateVersion, Company, Site
from backend.app.services.workflow import CaseWorkflowService


def _create_engine(tmp_path: Path):
    database_path = tmp_path / "phase18a-concurrency.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    return engine


def _seed_case(session: Session) -> tuple[str, str]:
    company = Company(legal_name="Concurrency Co", short_name="CC")
    session.add(company)
    session.flush()
    site = Site(company_id=company.id, site_name="Concurrency Site")
    session.add(site)
    session.flush()
    case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
    session.add(case)
    session.commit()
    return case.id, site.id


def _seed_certificate(session: Session, *, case_id: str, site_id: str) -> str:
    certificate = Certificate(
        case_id=case_id,
        site_id=site_id,
        certificate_type="GMP",
        issuance_basis="inspection_case",
        latest_flag=False,
        latest_legacy_certificate_id=None,
    )
    session.add(certificate)
    session.flush()
    session.add(
        CertificateVersion(
            certificate_id=certificate.id,
            version_no=1,
            certificate_number="CERT-001",
            issue_date=date(2026, 8, 20),
            expiry_date=date(2027, 8, 20),
            is_latest_version=True,
        )
    )
    session.commit()
    return certificate.id


def _seed_capa_cycle(session: Session, *, case_id: str) -> str:
    capa_cycle = CapaCycle(
        case_id=case_id,
        round_no=1,
        requested_on=date(2026, 8, 20),
        submitted_on=None,
        assessed_on=None,
        assessor_name=None,
        result=None,
        status="requested",
        notes="Initial CAPA",
    )
    session.add(capa_cycle)
    session.commit()
    return capa_cycle.id


async def _invoke_asgi(app, *, method: str, path: str):
    messages: list[dict[str, object]] = []
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            await asyncio.sleep(0)
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)
    return messages


def _status_from_messages(messages: list[dict[str, object]]) -> int:
    for message in messages:
        if message["type"] == "http.response.start":
            return int(message["status"])
    raise AssertionError("Missing response start")


def test_db_level_stale_commit_is_raised_for_case(tmp_path: Path):
    engine = _create_engine(tmp_path)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    with factory() as seed_session:
        case_id, _ = _seed_case(seed_session)

    session_a = factory()
    session_b = factory()
    try:
        case_a = session_a.get(Case, case_id)
        case_b = session_b.get(Case, case_id)
        assert case_a is not None and case_b is not None
        case_b.state = CaseState.AWAITING_CERTIFICATE_DECISION
        session_b.commit()
        case_a.state = CaseState.CANCELLED
        try:
            session_a.commit()
        except StaleDataError:
            pass
        else:
            raise AssertionError("Expected stale case commit to raise StaleDataError")
    finally:
        session_a.close()
        session_b.close()


def test_db_level_stale_commit_is_raised_for_certificate(tmp_path: Path):
    engine = _create_engine(tmp_path)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    with factory() as seed_session:
        case_id, site_id = _seed_case(seed_session)
        certificate_id = _seed_certificate(seed_session, case_id=case_id, site_id=site_id)

    session_a = factory()
    session_b = factory()
    try:
        certificate_a = session_a.get(Certificate, certificate_id)
        certificate_b = session_b.get(Certificate, certificate_id)
        assert certificate_a is not None and certificate_b is not None
        certificate_b.latest_flag = True
        certificate_b.latest_legacy_certificate_id = 202
        session_b.commit()
        certificate_a.latest_legacy_certificate_id = 101
        try:
            session_a.commit()
        except StaleDataError:
            pass
        else:
            raise AssertionError("Expected stale certificate commit to raise StaleDataError")
    finally:
        session_a.close()
        session_b.close()


def test_db_level_stale_commit_is_raised_for_capa_cycle(tmp_path: Path):
    engine = _create_engine(tmp_path)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    with factory() as seed_session:
        case_id, _ = _seed_case(seed_session)
        capa_cycle_id = _seed_capa_cycle(seed_session, case_id=case_id)

    session_a = factory()
    session_b = factory()
    try:
        capa_a = session_a.get(CapaCycle, capa_cycle_id)
        capa_b = session_b.get(CapaCycle, capa_cycle_id)
        assert capa_a is not None and capa_b is not None
        capa_b.status = "submitted"
        session_b.commit()
        capa_a.notes = "stale update"
        try:
            session_a.commit()
        except StaleDataError:
            pass
        else:
            raise AssertionError("Expected stale CAPA commit to raise StaleDataError")
    finally:
        session_a.close()
        session_b.close()


def test_request_boundary_maps_stale_data_error_to_http_409(tmp_path: Path):
    engine = _create_engine(tmp_path)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    with factory() as seed_session:
        case_id, _ = _seed_case(seed_session)

    stale_session = factory()
    competing_session = factory()
    try:
        stale_case = stale_session.get(Case, case_id)
        competing_case = competing_session.get(Case, case_id)
        assert stale_case is not None and competing_case is not None
        competing_case.state = CaseState.AWAITING_CERTIFICATE_DECISION
        competing_session.commit()

        app = FastAPI()
        dependency = Depends(get_session_from_request_factory(lambda: stale_session))

        def mutate_case(session: Session = dependency):
            assert session is stale_session
            stale_case.state = CaseState.CANCELLED
            commit_or_409(session)
            return {"ok": True}

        app.add_api_route("/stale-case", mutate_case, methods=["POST"])

        messages = asyncio.run(_invoke_asgi(app, method="POST", path="/stale-case"))
        assert _status_from_messages(messages) == 409
    finally:
        stale_session.close()
        competing_session.close()


def test_capa_service_uses_row_version_for_stale_update_guard(tmp_path: Path):
    engine = _create_engine(tmp_path)
    service = CaseWorkflowService()
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    with factory() as seed_session:
        case_id, _ = _seed_case(seed_session)
        capa_cycle_id = _seed_capa_cycle(seed_session, case_id=case_id)

    with factory() as session:
        row = session.get(CapaCycle, capa_cycle_id)
        assert row is not None
        current_version = row.row_version

    with factory() as session:
        row = session.get(CapaCycle, capa_cycle_id)
        assert row is not None
        row.notes = "advance version"
        session.commit()

    with factory() as session:
        try:
            service.update_capa_cycle(
                session,
                capa_cycle_id=capa_cycle_id,
                expected_version=current_version,
                requested_on=date(2026, 8, 20),
                notes="stale payload",
                reason="stale update",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "Stale capa_cycle update" in str(exc)
        else:
            raise AssertionError("Expected stale expected_version guard to reject CAPA update")
