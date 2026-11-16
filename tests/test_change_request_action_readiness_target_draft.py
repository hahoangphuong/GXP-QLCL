"""Change Request target readiness must not overwrite cached Certificate/DDK drafts.

The projection must validate persisted Site/Company and linked identities.
SQLite is disposable; PostgreSQL concurrent-owner tests already cover rebinding.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import (
    AuditEvent, BusinessEligibilityCertificate, Certificate, ChangeRequest,
    ChangeRequestAffectedArtifact, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


@pytest.mark.parametrize("kind", ["certificate", "business_eligibility"])
def test_change_request_target_readiness_uses_persisted_ownership_without_refresh(tmp_path, kind):
    engine = create_engine(
        f"sqlite:///{(tmp_path / (kind + '.sqlite')).as_posix()}", future=True,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as seed:
            owner = Company(legal_name="Synthetic owner")
            foreign = Company(legal_name="Synthetic foreign")
            seed.add_all([owner, foreign])
            seed.flush()
            site = Site(company_id=owner.id, site_name="Synthetic owner site")
            foreign_site = Site(company_id=foreign.id, site_name="Synthetic foreign site")
            seed.add_all([site, foreign_site])
            seed.flush()
            request = ChangeRequest(
                site_id=site.id, state=ChangeRequestState.RECEIVED,
                scope_label="SYNTHETIC", description="Source",
            )
            if kind == "certificate":
                target = Certificate(
                    site_id=site.id, certificate_type="GLP",
                    issuance_basis="administrative_no_inspection", latest_flag=False,
                )
            else:
                target = BusinessEligibilityCertificate(
                    site_id=site.id, company_id=owner.id, latest_flag=False,
                )
            seed.add_all([request, target])
            seed.flush()
            link = ChangeRequestAffectedArtifact(
                change_request_id=request.id,
                certificate_id=target.id if kind == "certificate" else None,
                business_eligibility_certificate_id=target.id if kind != "certificate" else None,
            )
            seed.add(link)
            seed.commit()
            target_id, request_id, link_id = target.id, request.id, link.id
            new_owner = foreign_site.id if kind == "certificate" else foreign.id

        actor = build_authenticated_user(
            "synthetic-target-readiness", permissions={
                "change_request.edit", "change_request.approve", "certificate.issue",
            },
        )
        with Session(engine, autoflush=True, expire_on_commit=False) as session:
            model = Certificate if kind == "certificate" else BusinessEligibilityCertificate
            cached = session.get(model, target_id)
            if kind == "certificate":
                cached.site_id = new_owner
            else:
                cached.company_id = new_owner
            assert cached in session.dirty
            sql_verbs = []

            def capture(_conn, _cursor, statement, _params, _context, _many):
                sql_verbs.append(statement.lstrip().split(None, 1)[0].upper())

            event.listen(engine, "before_cursor_execute", capture)
            try:
                actions = {
                    action["action_key"]: action
                    for action in CaseWorkflowService().get_change_request_action_readiness(
                        session, change_request_id=request_id, user=actor,
                    )
                }
            finally:
                event.remove(engine, "before_cursor_execute", capture)

            action_prefix = (
                "issue_certificate_successor:" if kind == "certificate"
                else "issue_business_eligibility_successor:"
            )
            assert action_prefix + link_id in actions
            assert set(sql_verbs) == {"SELECT"}
            assert cached in session.dirty
            if kind == "certificate":
                assert cached.site_id == new_owner
            else:
                assert cached.company_id == new_owner
            session.rollback()

        with Session(engine) as verify:
            persisted = verify.get(model, target_id)
            if kind == "certificate":
                assert persisted.site_id != new_owner
            else:
                assert persisted.company_id != new_owner
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()
