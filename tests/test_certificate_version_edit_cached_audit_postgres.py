"""PostgreSQL regression: latest-version edit audit must use committed prior state.

A long-lived Session caches the version; another Session commits an edit, then
the caller submits a new edit with the now-current root concurrency token.
The audit's old-values must not come from the Session's stale version identity.
"""
from __future__ import annotations

from datetime import date
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import (
    AppUser, AuditEvent, BusinessEligibilityCertificate,
    BusinessEligibilityVersion, Certificate, CertificateVersion,
    Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("kind", ["gxp", "business_eligibility"])
def test_latest_version_edit_audit_reads_committed_state_not_stale_identity(kind):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable gxp_qlcl_test is permitted.")
    schema = "latest_edit_audit_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = stale = editor = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic latest-edit audit " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic latest-edit audit")
            seed.add(site)
            seed.flush()
            if kind == "gxp":
                aggregate = Certificate(
                    site_id=site.id, certificate_type="GLP", latest_flag=False,
                )
                seed.add(aggregate)
                seed.flush()
                version = CertificateVersion(
                    certificate_id=aggregate.id, version_no=1,
                    certificate_number="ORIGINAL",
                    issue_date=date(2026, 8, 1), expiry_date=date(2027, 8, 1),
                    is_latest_version=True,
                )
            else:
                aggregate = BusinessEligibilityCertificate(
                    company_id=company.id, site_id=site.id, latest_flag=False,
                )
                seed.add(aggregate)
                seed.flush()
                version = BusinessEligibilityVersion(
                    business_eligibility_certificate_id=aggregate.id,
                    version_no=1, certificate_number="ORIGINAL",
                    issued_on=date(2026, 8, 1),
                )
            seed.add(version)
            seed.add(AppUser(username="synthetic-edit-audit", display_name="Synthetic audit actor", is_active=True))
            seed.commit()
            aggregate_id, version_id, original_token = aggregate.id, version.id, aggregate.row_version

        service = CaseWorkflowService()
        actor = build_authenticated_user("synthetic-edit-audit", "manager")
        stale = factory()
        cached = stale.get(CertificateVersion if kind == "gxp" else BusinessEligibilityVersion, version_id)
        assert cached.certificate_number == "ORIGINAL"

        def edit(session, token, number):
            if kind == "gxp":
                return service.upsert_certificate_latest_version(
                    session, certificate_id=aggregate_id, expected_version=token,
                    certificate_number=number,
                    issue_date=date(2026, 8, 1), expiry_date=date(2027, 8, 1),
                    scopes=[], reason="synthetic audit regression", user=actor,
                )
            return service.upsert_business_eligibility_latest_version(
                session, business_eligibility_certificate_id=aggregate_id,
                expected_version=token, certificate_number=number,
                issued_on=date(2026, 8, 1), expires_on=None,
                professional_responsible_person_name=None, notes=None,
                linked_certificates=[], reason="synthetic audit regression",
                user=actor,
            )

        editor = factory()
        first = edit(editor, original_token, "FIRST_COMMITTED")
        editor.commit()
        assert first["row_version"] != original_token
        assert cached.certificate_number == "ORIGINAL"

        second = edit(stale, first["row_version"], "SECOND_COMMITTED")
        stale.commit()
        assert second["row_version"] != first["row_version"]

        with factory() as verify:
            stored = verify.get(CertificateVersion if kind == "gxp" else BusinessEligibilityVersion, version_id)
            assert stored.certificate_number == "SECOND_COMMITTED"
            action = "certificate.latest_version.upsert" if kind == "gxp" else "business_eligibility.latest_version.upsert"
            audits = list(verify.scalars(select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.created_at, AuditEvent.id)))
            assert len(audits) == 2
            second_audit = next(a for a in audits if json.loads(a.new_values_json)["certificate_number"] == "SECOND_COMMITTED")
            before = json.loads(second_audit.old_values_json)
            assert before["certificate_number"] == "FIRST_COMMITTED", (
                f"Audit misstates previously committed {kind} certificate number: {before['certificate_number']!r}"
            )
    finally:
        for session in (stale, editor):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
