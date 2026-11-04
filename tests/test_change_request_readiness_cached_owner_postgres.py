"""PostgreSQL: Change Request readiness must use a committed parent state/token.

Session A caches RECEIVED, Session B transitions via the actual workflow
service and commits UNDER_REVIEW. Readiness from A must not offer obsolete
actions/tokens. Disposable database and isolated synthetic schema only.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import AppUser, AuditEvent, ChangeRequest, Company, Site
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_change_request_readiness_refreshes_cached_owner_after_real_transition():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted.")
    schema = "change_readiness_owner_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = cached = None
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
            company = Company(legal_name="Synthetic readiness " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic readiness Site")
            seed.add(site)
            seed.flush()
            row = ChangeRequest(
                site_id=site.id, state=ChangeRequestState.RECEIVED,
                scope_label="SYNTHETIC", description="Synthetic source",
            )
            seed.add(row)
            seed.add(AppUser(
                username="synthetic-readiness", display_name="Synthetic actor",
                is_active=True,
            ))
            seed.commit()
            row_id, original_token = row.id, row.row_version

        service = CaseWorkflowService()
        actor = build_authenticated_user(
            "synthetic-readiness", "manager",
            permissions=["change_request.edit", "change_request.approve", "certificate.issue"],
        )
        cached = factory()
        cached_root = cached.get(ChangeRequest, row_id)
        baseline = {
            item["action_key"]: item
            for item in service.get_change_request_action_readiness(
                cached, change_request_id=row_id, user=actor,
            )
        }
        assert not baseline["edit_change_approval"]["available"]
        assert baseline["edit_change_request"]["expected_version"] == original_token
        assert "transition_change_request:under_review" in baseline

        with factory() as writer:
            committed = service.transition_change_request(
                writer, change_request_id=row_id, target_state="under_review",
                expected_version=original_token, reason="Committed synthetic transition",
                user=actor,
            )
            writer.commit()
        committed_token = committed["row_version"]
        assert committed_token != original_token
        assert cached_root.row_version == original_token
        assert cached_root.state == ChangeRequestState.RECEIVED

        current_actions = {
            item["action_key"]: item
            for item in service.get_change_request_action_readiness(
                cached, change_request_id=row_id, user=actor,
            )
        }
        assert current_actions["edit_change_approval"]["available"] is True
        assert current_actions["edit_change_request"]["expected_version"] == committed_token
        assert "transition_change_request:under_review" not in current_actions
        assert "transition_change_request:accepted" in current_actions
        assert current_actions["transition_change_request:accepted"]["expected_version"] == committed_token

        with factory() as verify:
            persisted = verify.get(ChangeRequest, row_id)
            assert persisted.state == ChangeRequestState.UNDER_REVIEW
            assert persisted.row_version == committed_token
            assert verify.scalar(select(func.count(AuditEvent.id)).where(
                AuditEvent.action == "change_request.transition"
            )) == 1
    finally:
        if cached is not None:
            cached.rollback()
            cached.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
