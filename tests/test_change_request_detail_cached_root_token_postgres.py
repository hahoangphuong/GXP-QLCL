"""PostgreSQL: Change Request detail mutations must validate committed root tokens.

A holds a ChangeRequest in its ORM identity map; B commits a real header
update. A must reject a stale root token before detail/audit writes, and must
accept the committed token even though the identity remains stale.
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
    AppUser, AuditEvent, ChangeRequest, ChangeRequestDetail, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("operation", ["create_detail", "update_detail"])
@pytest.mark.parametrize("request_token", ["stale", "fresh"])
def test_change_request_detail_mutation_uses_committed_owner_token(operation, request_token):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Only disposable PostgreSQL gxp_qlcl_test is permitted.")
    schema = "change_detail_token_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = cached_session = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as seed:
            company = Company(legal_name="Synthetic Change Request detail " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic detail token Site")
            seed.add(site)
            seed.flush()
            row = ChangeRequest(
                site_id=site.id, state=ChangeRequestState.RECEIVED,
                scope_label="ORIGINAL", description="Synthetic source",
            )
            seed.add(row)
            seed.flush()
            detail = ChangeRequestDetail(
                change_request_id=row.id, classification_label="ORIGINAL_DETAIL",
                approval_status="pending", old_value="OLD", new_value="NEW",
            )
            seed.add(detail)
            seed.add(AppUser(
                username="synthetic-change-detail", display_name="Synthetic actor",
                is_active=True,
            ))
            seed.commit()
            row_id, detail_id, original_token = row.id, detail.id, row.row_version

        service = CaseWorkflowService()
        actor = build_authenticated_user(
            "synthetic-change-detail", "manager",
            permissions=["change_request.edit", "change_request.approve"],
        )

        def mutate_detail(session, token):
            params = dict(
                expected_version=token, classification_id=None,
                classification_label="SECOND_DETAIL", approval_status="pending",
                old_value="OLD", new_value="NEW_2", note="Synthetic mutation",
                reason="Synthetic detail owner concurrency", user=actor,
            )
            if operation == "create_detail":
                return service.create_change_request_detail(
                    session, change_request_id=row_id, **params,
                )
            return service.update_change_request_detail(
                session, change_detail_id=detail_id, **params,
            )

        cached_session = factory()
        cached_root = cached_session.get(ChangeRequest, row_id)
        assert cached_root.row_version == original_token
        assert cached_root.state == ChangeRequestState.RECEIVED
        if operation == "update_detail":
            cached_detail = cached_session.get(ChangeRequestDetail, detail_id)
            assert cached_detail.classification_label == "ORIGINAL_DETAIL"

        with factory() as writer:
            first = service.update_change_request(
                writer, change_request_id=row_id, expected_version=original_token,
                scope_label="FIRST_COMMITTED", description="Synthetic source",
                submitted_on=date(2026, 11, 5), requester_name="Synthetic",
                reason="Committed root version from peer Session", user=actor,
            )
            writer.commit()
        committed_token = first["row_version"]
        assert committed_token != original_token
        assert cached_root.row_version == original_token, "Precondition: cached root is stale"

        if request_token == "stale":
            with pytest.raises(HTTPException) as denied:
                mutate_detail(cached_session, original_token)
            assert denied.value.status_code == 409
            assert "Stale change_request update" in str(denied.value.detail)
            cached_session.rollback()
        else:
            second = mutate_detail(cached_session, committed_token)
            cached_session.commit()
            assert second["row_version"] != committed_token

        with factory() as verify:
            persisted = verify.get(ChangeRequest, row_id)
            assert persisted.scope_label == "FIRST_COMMITTED"
            expected_token = committed_token if request_token == "stale" else second["row_version"]
            assert persisted.row_version == expected_token
            detail_rows = list(verify.scalars(
                select(ChangeRequestDetail).where(ChangeRequestDetail.change_request_id == row_id)
            ))
            if operation == "create_detail":
                assert len(detail_rows) == (1 if request_token == "stale" else 2)
                labels = {d.classification_label for d in detail_rows}
                assert labels == ({"ORIGINAL_DETAIL"} if request_token == "stale"
                                  else {"ORIGINAL_DETAIL", "SECOND_DETAIL"})
            else:
                assert len(detail_rows) == 1
                assert detail_rows[0].classification_label == (
                    "ORIGINAL_DETAIL" if request_token == "stale" else "SECOND_DETAIL"
                )
            action = ("change_request_detail.create" if operation == "create_detail"
                      else "change_request_detail.update")
            assert verify.scalar(select(func.count(AuditEvent.id)).where(
                AuditEvent.action == "change_request.update",
            )) == 1
            assert verify.scalar(select(func.count(AuditEvent.id)).where(
                AuditEvent.action == action,
            )) == (0 if request_token == "stale" else 1)
    finally:
        if cached_session is not None:
            cached_session.rollback()
            cached_session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
