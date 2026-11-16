"""Change Request action GET must not autoflush or refresh cached operator drafts.

Synthetic disposable SQLite exercises the actual CaseWorkflowService owner.
The wider nested Certificate/DDK readiness owner is tracked separately in #557.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import AuditEvent, ChangeRequest, Company, Site
from backend.app.services.workflow import CaseWorkflowService


def test_action_readiness_uses_persisted_root_without_autoflush_or_draft_refresh(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'change-action-root.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as seed:
            company = Company(legal_name="Synthetic Action Readiness")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic registered Site")
            seed.add(site)
            seed.flush()
            request = ChangeRequest(
                site_id=site.id,
                state=ChangeRequestState.RECEIVED,
                scope_label="SYNTHETIC",
                description="Persisted source description",
            )
            seed.add(request)
            seed.commit()
            request_id = request.id
            persisted_version = request.row_version

        actor = build_authenticated_user(
            "synthetic-action-readiness",
            permissions={"change_request.edit", "change_request.approve", "certificate.issue"},
        )
        with Session(engine, autoflush=True, expire_on_commit=False) as session:
            cached = session.get(ChangeRequest, request_id)
            cached.description = "Uncommitted operator draft"
            cached.state = ChangeRequestState.ACCEPTED
            assert cached in session.dirty
            operations = []

            def capture(_conn, _cursor, statement, _params, _context, _many):
                operations.append(statement.lstrip().split(None, 1)[0].upper())

            event.listen(engine, "before_cursor_execute", capture)
            try:
                actions = {
                    item["action_key"]: item
                    for item in CaseWorkflowService().get_change_request_action_readiness(
                        session, change_request_id=request_id, user=actor,
                    )
                }
            finally:
                event.remove(engine, "before_cursor_execute", capture)
            assert operations and set(operations) == {"SELECT"}
            assert actions["edit_change_request"]["available"] is True
            assert actions["edit_change_request"]["expected_version"] == persisted_version
            assert "transition_change_request:under_review" in actions
            assert cached.description == "Uncommitted operator draft"
            assert cached.state == ChangeRequestState.ACCEPTED
            assert cached in session.dirty
            session.rollback()

        with Session(engine) as verify:
            request = verify.get(ChangeRequest, request_id)
            assert request.state == ChangeRequestState.RECEIVED
            assert request.description == "Persisted source description"
            assert request.row_version == persisted_version
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()
