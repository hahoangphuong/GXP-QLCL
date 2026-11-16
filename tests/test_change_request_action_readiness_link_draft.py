"""Persisted Change Request link actions must not overwrite dirty ORM links.

Disposable SQLite exercises real readiness owner with a pending affected-artifact
draft. Committed link remains the readiness source and no DML/audit occurs.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import (
    AuditEvent, Certificate, ChangeRequest, ChangeRequestAffectedArtifact,
    Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


def test_action_readiness_preserves_dirty_affected_artifact_link(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'affected-link-readiness.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as seed:
            company = Company(legal_name="Synthetic affected link readiness")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic Site")
            seed.add(site)
            seed.flush()
            request = ChangeRequest(
                site_id=site.id,
                state=ChangeRequestState.RECEIVED,
                scope_label="SYNTHETIC",
                description="Synthetic affected link",
            )
            certificate = Certificate(
                site_id=site.id, certificate_type="GLP",
                issuance_basis="administrative_no_inspection", latest_flag=False,
            )
            seed.add_all([request, certificate])
            seed.flush()
            link = ChangeRequestAffectedArtifact(
                change_request_id=request.id, certificate_id=certificate.id,
            )
            seed.add(link)
            seed.commit()
            ids = dict(
                request=request.id, certificate=certificate.id, link=link.id,
                token=request.row_version,
            )

        actor = build_authenticated_user(
            "synthetic-affected-link-readiness",
            permissions={"change_request.edit", "change_request.approve", "certificate.issue"},
        )
        with Session(engine, autoflush=True, expire_on_commit=False) as session:
            cached_link = session.get(ChangeRequestAffectedArtifact, ids["link"])
            cached_link.certificate_id = None  # uncommitted operator edit
            assert cached_link in session.dirty
            operations = []

            def capture(_conn, _cursor, statement, _params, _context, _many):
                operations.append(statement.lstrip().split(None, 1)[0].upper())

            event.listen(engine, "before_cursor_execute", capture)
            try:
                actions = {
                    item["action_key"]: item
                    for item in CaseWorkflowService().get_change_request_action_readiness(
                        session, change_request_id=ids["request"], user=actor,
                    )
                }
            finally:
                event.remove(engine, "before_cursor_execute", capture)

            key = f"issue_certificate_successor:{ids['link']}"
            assert key in actions
            assert actions[key]["available"] is False
            assert actions[key]["reason_code"] == "source_version_missing"
            assert actions[key]["expected_version"] == ids["token"]
            assert operations and set(operations) == {"SELECT"}
            assert cached_link.certificate_id is None
            assert cached_link in session.dirty
            session.rollback()

        with Session(engine) as verify:
            persisted = verify.get(ChangeRequestAffectedArtifact, ids["link"])
            assert persisted.certificate_id == ids["certificate"]
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()
