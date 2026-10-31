"""Disposable PostgreSQL two-session same-context GMP current promotion gate."""
from __future__ import annotations

from datetime import date
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AppUser, AuditEvent, Certificate, CertificateVersion, Company, InspectionEvent, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_same_context_certificate_promotions_serialize_before_peer_read():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only the disposable gxp_qlcl_test database is allowed.")
    schema = "cert_promotion_race_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = None
    first = second = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="GMP competing promotion " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="GMP promotion race")
            seed.add(site)
            seed.flush()
            rows = []
            for number, issued in (("CANDIDATE-1", date(2026, 8, 1)), ("CANDIDATE-2", date(2026, 9, 1))):
                cert = Certificate(
                    site_id=site.id, certificate_type="GMP", line_code="A", latest_flag=False,
                )
                seed.add(cert)
                seed.flush()
                seed.add(CertificateVersion(
                    certificate_id=cert.id, version_no=1, certificate_number=number,
                    issue_date=issued, expiry_date=date(2027, 9, 1), is_latest_version=True,
                ))
                rows.append((cert.id, cert.row_version))
            seed.add(AppUser(username="promotion-race-user", display_name="Race user", is_active=True))
            seed.commit()
            ids, tokens = [r[0] for r in rows], [r[1] for r in rows]

        service = CaseWorkflowService()
        user = build_authenticated_user("promotion-race-user", "manager")
        first = factory()
        result1 = service.promote_certificate_current(
            first, certificate_id=ids[0], expected_version=tokens[0],
            reason="First concurrent promotion", user=user,
        )
        assert result1["latest_flag"] is True

        second = factory()
        second.execute(text("SET LOCAL lock_timeout = '250ms'"))
        with pytest.raises(OperationalError, match="lock timeout"):
            service.promote_certificate_current(
                second, certificate_id=ids[1], expected_version=tokens[1],
                reason="Competing promotion", user=user,
            )
        second.rollback()
        first.commit()

        result2 = service.promote_certificate_current(
            second, certificate_id=ids[1], expected_version=tokens[1],
            reason="Retry after committed first promotion", user=user,
        )
        assert result2["latest_flag"] is True
        second.commit()

        with factory() as verify:
            rows = list(verify.scalars(select(Certificate).where(
                Certificate.id.in_(ids),
            ).order_by(Certificate.id)))
            assert len(rows) == 2
            assert [row.id for row in rows if row.latest_flag] == [ids[1]]
            assert verify.scalar(select(func.count(AuditEvent.id))) == 2
            assert verify.scalar(select(func.count(InspectionEvent.id))) == 0
    finally:
        for session in (second, first):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
