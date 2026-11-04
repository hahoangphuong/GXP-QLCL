"""PostgreSQL regression: existing Change Request edits validate committed root tokens.

Scope is header update and state transition on an already-persisted record,
NOT Change Request create/durable mutation recovery (separate decision gate).
Session A caches ChangeRequest; Session B commits a write and increments token.
A must reject the old token with HTTP 409 before writes, and accept the new
committed token even though its identity map still holds the old root.
"""
from __future__ import annotations

from datetime import date
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import (
    AppUser, AuditEvent, ChangeRequest, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("operation", ["update_header", "transition"])
@pytest.mark.parametrize("request_token", ["stale", "fresh"])
def test_existing_change_request_uses_committed_root_token(operation, request_token):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted.")
    schema = "change_existing_token_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = stale_session = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False, future=True,
        )
        with factory() as seed:
            company = Company(legal_name="Synthetic existing CR root " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic CR token site")
            seed.add(site)
            seed.flush()
            row = ChangeRequest(
                site_id=site.id, scope_label="ORIGINAL", description="Synthetic root",
                state=ChangeRequestState.RECEIVED,
            )
            seed.add(row)
            seed.add(AppUser(
                username="synthetic-cr-root", display_name="Synthetic actor",
                is_active=True,
            ))
            seed.commit()
            row_id, original_token = row.id, row.row_version

        service = CaseWorkflowService()
        actor = build_authenticated_user(
            "synthetic-cr-root", "manager",
            permissions=["change_request.edit", "change_request.approve"],
        )
        def mutate(session, token, n):
            if operation == "update_header":
                return service.update_change_request(
                    session, change_request_id=row_id, expected_version=token,
                    scope_label=n, description="Synthetic header", submitted_on=date(2026, 11, 5),
                    requester_name="Synthetic", reason="Token owner test", user=actor,
                )
            return service.transition_change_request(
                session, change_request_id=row_id, expected_version=token,
                target_state=(ChangeRequestState.UNDER_REVIEW.value if n == "FIRST"
                              else ChangeRequestState.ACCEPTED.value),
                reason="Token owner test", user=actor,
            )

        stale_session = factory()
        cached_row = stale_session.get(ChangeRequest, row_id)
        assert cached_row.row_version == original_token
        assert cached_row.state == ChangeRequestState.RECEIVED
        with factory() as writer:
            first = mutate(writer, original_token, "FIRST")
            writer.commit()
        committed_token = first["row_version"]
        assert committed_token != original_token
        assert cached_row.row_version == original_token, "Precondition: stale root cached"

        if request_token == "stale":
            with pytest.raises(HTTPException) as denied:
                mutate(stale_session, original_token, "SECOND")
            assert denied.value.status_code == 409
            stale_session.rollback()
        else:
            second = mutate(stale_session, committed_token, "SECOND")
            stale_session.commit()
            assert second["row_version"] != committed_token

        with factory() as verify:
            persisted = verify.get(ChangeRequest, row_id)
            expected_audits = 1 if request_token == "stale" else 2
            action = ("change_request.update" if operation == "update_header"
                      else "change_request.transition")
            assert verify.scalar(select(func.count(AuditEvent.id)).where(
                AuditEvent.action == action,
            )) == expected_audits
            if operation == "update_header":
                assert persisted.scope_label == (
                    "FIRST" if request_token == "stale" else "SECOND"
                )
                assert persisted.state == ChangeRequestState.RECEIVED
            else:
                assert persisted.state == (
                    ChangeRequestState.UNDER_REVIEW if request_token == "stale"
                    else ChangeRequestState.ACCEPTED
                )
            assert persisted.row_version == (
                committed_token if request_token == "stale" else second["row_version"]
            )
    finally:
        if stale_session is not None:
            stale_session.rollback()
            stale_session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
