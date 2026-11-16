"""GxP action GET must use committed root/version/peer/Case state, not drafts.

Synthetic disposable SQLite; existing PostgreSQL regressions verify competing
promotions, edited versions, and source ownership under READ COMMITTED.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Certificate, CertificateVersion, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


def _user():
    return build_authenticated_user(
        "synthetic-gxp-action-readiness",
        permissions={"certificate.edit", "certificate.approve"},
    )


def _actions(session, certificate_id):
    return {
        item["action_key"]: item
        for item in CaseWorkflowService().get_certificate_action_readiness(
            session, certificate_id=certificate_id, user=_user(),
        )
    }


def test_gxp_readiness_preserves_cached_root_version_and_current_peer_drafts(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'gxp-readiness-peer.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as seed:
            company = Company(legal_name="Synthetic GxP current peer")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic GxP Site")
            seed.add(site)
            seed.flush()
            candidate = Certificate(
                site_id=site.id, certificate_type="GLP",
                issuance_basis="administrative_no_inspection",
                line_code="LINE-A", latest_flag=False,
            )
            peer = Certificate(
                site_id=site.id, certificate_type="GLP",
                issuance_basis="administrative_no_inspection",
                line_code="LINE-A", latest_flag=True,
            )
            seed.add_all([candidate, peer])
            seed.flush()
            version = CertificateVersion(
                certificate_id=candidate.id, version_no=1,
                certificate_number="CANDIDATE", issue_date=date(2026, 1, 1),
                expiry_date=date(2027, 1, 1), is_latest_version=True,
            )
            peer_version = CertificateVersion(
                certificate_id=peer.id, version_no=1,
                certificate_number="CURRENT", issue_date=date(2026, 6, 1),
                expiry_date=date(2027, 6, 1), is_latest_version=True,
            )
            seed.add_all([version, peer_version])
            seed.commit()
            ids = (candidate.id, version.id, peer.id, peer_version.id, candidate.row_version)

        with Session(engine, autoflush=True, expire_on_commit=False) as session:
            candidate = session.get(Certificate, ids[0])
            version = session.get(CertificateVersion, ids[1])
            peer = session.get(Certificate, ids[2])
            peer_version = session.get(CertificateVersion, ids[3])
            candidate.latest_flag = True
            version.issue_date = date(2027, 1, 1)
            peer.latest_flag = False
            peer_version.issue_date = date(2025, 1, 1)
            statements = []

            def capture(_conn, _cursor, sql, _params, _ctx, _many):
                statements.append(sql.lstrip().split(None, 1)[0].upper())

            event.listen(engine, "before_cursor_execute", capture)
            try:
                actions = _actions(session, ids[0])
            finally:
                event.remove(engine, "before_cursor_execute", capture)

            assert actions["promote_current"]["available"] is False
            assert actions["promote_current"]["reason_code"] == "candidate_issue_date_precedes_current"
            assert actions["edit_latest_version"]["expected_version"] == ids[4]
            assert statements and set(statements) == {"SELECT"}
            assert candidate.latest_flag is True
            assert version.issue_date == date(2027, 1, 1)
            assert peer.latest_flag is False
            assert peer_version.issue_date == date(2025, 1, 1)
            assert all(x in session.dirty for x in (candidate, version, peer, peer_version))
            session.rollback()

        with Session(engine) as verify:
            assert verify.get(Certificate, ids[0]).latest_flag is False
            assert verify.get(CertificateVersion, ids[1]).issue_date == date(2026, 1, 1)
            assert verify.get(Certificate, ids[2]).latest_flag is True
            assert verify.get(CertificateVersion, ids[3]).issue_date == date(2026, 6, 1)
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()


def test_gxp_readiness_preserves_linked_case_draft_and_uses_committed_state(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'gxp-readiness-case.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as seed:
            company = Company(legal_name="Synthetic GxP case owner")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic Case Site")
            seed.add(site)
            seed.flush()
            case = Case(
                site_id=site.id, gxp_type="GMP",
                state=CaseState.AWAITING_CERTIFICATE_DECISION,
            )
            seed.add(case)
            seed.flush()
            certificate = Certificate(
                site_id=site.id, case_id=case.id,
                certificate_type="GMP", issuance_basis="inspection_case",
                latest_flag=False,
            )
            seed.add(certificate)
            seed.flush()
            version = CertificateVersion(
                certificate_id=certificate.id, version_no=1,
                certificate_number="GMP-SYNTHETIC",
                issue_date=date(2026, 10, 1),
                expiry_date=date(2027, 10, 1),
                is_latest_version=True,
            )
            seed.add(version)
            seed.commit()
            case_id, certificate_id = case.id, certificate.id

        with Session(engine, autoflush=True, expire_on_commit=False) as reader:
            cached_case = reader.get(Case, case_id)
            cached_case.state = CaseState.CANCELLED
            assert cached_case in reader.dirty
            actions = _actions(reader, certificate_id)
            assert actions["promote_current"]["available"] is True
            assert actions["promote_current"]["reason_code"] is None
            assert cached_case.state == CaseState.CANCELLED
            assert cached_case in reader.dirty
            reader.rollback()
        with Session(engine) as verify:
            assert verify.get(Case, case_id).state == CaseState.AWAITING_CERTIFICATE_DECISION
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()
