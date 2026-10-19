"""Real PostgreSQL locking regression for prospective single-Case GMP issuance.

Runs only in GitHub Actions' disposable loopback gxp_qlcl_test database.
Two distinct SQL connections contend for one Case. Never touches a VM,
rehearsal, historical Certificate link or a real production database.
"""
from __future__ import annotations

from datetime import date
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, delete, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Certificate, CertificateScope, CertificateVersion,
    Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


def _ci_disposable_database_url() -> str | None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return None
    raw = os.environ.get("DATABASE_URL", "")
    try:
        uri = make_url(raw)
    except Exception:
        return None
    if (
        uri.get_backend_name() != "postgresql"
        or uri.database != "gxp_qlcl_test"
        or uri.username != "postgres"
        or uri.host not in {"localhost", "127.0.0.1", "::1"}
        or (uri.port or 5432) != 5432
        or bool(uri.query)
    ):
        return None
    return raw


@pytest.mark.skipif(
    _ci_disposable_database_url() is None,
    reason="GMP Case lock requires exact disposable GitHub Actions PostgreSQL",
)
def test_two_sessions_cannot_issue_two_gmp_certificates_from_one_case():
    url = _ci_disposable_database_url()
    assert url is not None
    engine = create_engine(url, future=True, pool_size=3, max_overflow=0)
    make_session = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, future=True,
    )
    token = uuid4().hex
    company_id = site_id = case_id = certificate_id = None
    blocker = contender = None
    try:
        # Only the ephemeral GitHub Actions container DB; committed seed is
        # required for the two independently connected transactions to see
        # the same canonical Case and compete on its row lock.
        with make_session() as seed:
            assert seed.execute(text("SELECT current_database()")).scalar_one() == "gxp_qlcl_test"
            co = Company(legal_name=f"Disposable issuance lock {token}")
            seed.add(co)
            seed.flush()
            company_id = co.id
            site = Site(company_id=company_id, site_name=f"Disposable GMP site {token}")
            seed.add(site)
            seed.flush()
            site_id = site.id
            case = Case(
                site_id=site_id,
                gxp_type="GMP",
                state=CaseState.AWAITING_CERTIFICATE_DECISION,
            )
            seed.add(case)
            seed.commit()
            case_id = case.id

        user = build_authenticated_user(f"disposable-gmp-issuer-{token}", "admin")
        service = CaseWorkflowService()

        def issue(session, number):
            return service.issue_certificate(
                session,
                site_id=site_id,
                case_id=case_id,
                certificate_type="GMP",
                issuance_basis="inspection_case",
                certificate_number=number,
                issue_date=date(2026, 10, 19),
                expiry_date=date(2029, 10, 19),
                scopes=[],
                reason="Synthetic concurrent issuance",
                user=user,
            )

        blocker = make_session()
        first = issue(blocker, f"CI-FIRST-{token}")
        certificate_id = first["certificate_id"]
        # First row and its Case FOR UPDATE lock remain uncommitted.
        contender = make_session()
        contender.execute(text("SET LOCAL lock_timeout = '350ms'"))
        contender_conn = contender.connection()
        contender_mutations = []
        contender_lock_queries = []

        def observe_sql(conn, _cursor, statement, _params, _context, _many):
            if conn is not contender_conn:
                return
            sql = statement.strip().upper()
            if sql.startswith(("INSERT", "UPDATE", "DELETE")):
                contender_mutations.append(sql.split(maxsplit=1)[0])
            if "FOR UPDATE" in sql:
                contender_lock_queries.append(True)

        event.listen(engine, "before_cursor_execute", observe_sql)
        try:
            # The second operation must block at Case row lock, BEFORE
            # constructing any Certificate/Version or AuditEvent.
            with pytest.raises(OperationalError, match="lock timeout"):
                issue(contender, f"CI-SECOND-{token}")
        finally:
            event.remove(engine, "before_cursor_execute", observe_sql)
            contender.rollback()

        assert contender_lock_queries
        assert contender_mutations == []
        blocker.commit()  # First issuance becomes visible to fresh READ COMMITTED statements.

        before = (
            contender.scalar(select(Certificate.id).where(Certificate.case_id == case_id)),
            list(contender.scalars(
                select(CertificateVersion.id).where(
                    CertificateVersion.certificate_id == certificate_id
                )
            )),
        )
        assert before[0] == certificate_id
        assert len(before[1]) == 1
        with pytest.raises(HTTPException) as exc:
            issue(contender, f"CI-SECOND-{token}")
        assert exc.value.status_code == 409
        assert "already issued" in str(exc.value.detail).lower()
        contender.rollback()
        with make_session() as verify:
            certs = list(verify.scalars(
                select(Certificate).where(Certificate.case_id == case_id)
            ))
            assert len(certs) == 1
            assert certs[0].id == certificate_id
            assert len(list(verify.scalars(
                select(CertificateVersion.id).where(
                    CertificateVersion.certificate_id == certificate_id
                )
            ))) == 1
            assert len(list(verify.scalars(
                select(AuditEvent.id).where(
                    AuditEvent.entity_type == "certificate",
                    AuditEvent.entity_id == certificate_id,
                    AuditEvent.action == "certificate.issue",
                )
            ))) == 1
    finally:
        if contender is not None:
            contender.rollback()
            contender.close()
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        # Clean up only exact UUIDs created by this CI test, never a
        # cross-case SQL filter. No actual user/business DB is reachable.
        if case_id is not None:
            with make_session() as cleanup:
                if certificate_id is not None:
                    cleanup.execute(delete(AuditEvent).where(
                        AuditEvent.entity_type == "certificate",
                        AuditEvent.entity_id == certificate_id,
                    ))
                    version_ids = list(cleanup.scalars(
                        select(CertificateVersion.id).where(
                            CertificateVersion.certificate_id == certificate_id
                        )
                    ))
                    if version_ids:
                        cleanup.execute(delete(CertificateScope).where(
                            CertificateScope.certificate_version_id.in_(version_ids)
                        ))
                    cleanup.execute(delete(CertificateVersion).where(
                        CertificateVersion.certificate_id == certificate_id
                    ))
                    cleanup.execute(delete(Certificate).where(
                        Certificate.id == certificate_id
                    ))
                cleanup.execute(delete(Case).where(Case.id == case_id))
                if site_id is not None:
                    cleanup.execute(delete(Site).where(Site.id == site_id))
                if company_id is not None:
                    cleanup.execute(delete(Company).where(Company.id == company_id))
                cleanup.commit()
        engine.dispose()
