from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.auth import ROLE_PERMISSIONS, build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import ChangeRequestState
from backend.app.db.models.phase1 import (
    AuditEvent,
    ChangeApproval,
    ChangeRequest,
    ChangeRequestDetail,
    Company,
    Site,
)
from backend.app.main import create_app
from backend.app.services import CatalogReadService, CaseWorkflowService


def _seed_site(session: Session) -> str:
    company = Company(legal_name="A5 Company", short_name="A5")
    session.add(company)
    session.flush()
    site = Site(company_id=company.id, site_name="A5 Site")
    session.add(site)
    session.commit()
    return site.id


def _editor():
    return build_authenticated_user(
        "inspector01",
        "inspector",
        permissions=ROLE_PERMISSIONS["inspector"],
    )


def _approver():
    return build_authenticated_user(
        "manager01",
        "manager",
        permissions=ROLE_PERMISSIONS["manager"],
    )


def test_a5_routes_and_bounded_context_permissions_are_registered():
    app = create_app("sqlite:///:memory:")
    routes = {(route.path, tuple(sorted(route.methods or []))) for route in app.routes if hasattr(route, "path")}
    assert ("/sites/{site_id}/change-requests", ("POST",)) in routes
    assert ("/change-requests/{change_request_id}", ("PUT",)) in routes
    assert ("/change-requests/{change_request_id}/details", ("POST",)) in routes
    assert ("/change-request-details/{change_detail_id}", ("PUT",)) in routes
    assert ("/change-requests/{change_request_id}/approval", ("PUT",)) in routes
    assert ("/change-requests/{change_request_id}/transition", ("POST",)) in routes
    assert "change_request.edit" in ROLE_PERMISSIONS["inspector"]
    assert "change_request.edit" in ROLE_PERMISSIONS["manager"]
    assert "change_request.approve" in ROLE_PERMISSIONS["manager"]
    assert "change_request.approve" not in ROLE_PERMISSIONS["inspector"]
    assert "change_request.edit" not in ROLE_PERMISSIONS["reader"]


def test_a5_create_workspace_and_readiness_are_canonical_and_permission_owned(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'a5-create.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    workflow = CaseWorkflowService()
    with Session(engine) as session:
        site_id = _seed_site(session)

    with Session(engine) as session:
        reader = build_authenticated_user("reader01", "reader", permissions=ROLE_PERMISSIONS["reader"])
        assert workflow.get_create_change_request_action_readiness(
            session, site_id=site_id, user=reader
        )["readiness_status"] == "forbidden"
        assert workflow.get_create_change_request_action_readiness(
            session, site_id=site_id, user=_editor()
        )["readiness_status"] == "available"
        created = workflow.create_change_request(
            session,
            site_id=site_id,
            scope_label="Mở rộng kho",
            description="Thay đổi điều kiện bảo quản.",
            submitted_on=date(2026, 10, 5),
            requester_name="Cơ sở A5",
            reason="Create canonical change.",
            user=_editor(),
        )
        session.commit()
        change_id = created["change_request_id"]

    with Session(engine) as session:
        workspace = CatalogReadService().get_change_request_workspace(
            session,
            change_request_id=change_id,
            user=_editor(),
        )
        assert workspace["legacy_change_request_id"] is None
        assert workspace["row_version"] == created["row_version"]
        assert workspace["state"] == "received"
        actions = {item["action_key"]: item for item in workspace["action_readiness"]}
        assert actions["edit_change_request"]["available"] is True
        assert actions["add_change_detail"]["available"] is True
        assert actions["edit_change_approval"]["available"] is False
        transition = actions["transition_change_request:under_review"]
        assert transition["available"] is True
        assert transition["expected_version"] == created["row_version"]


def test_a5_aggregate_version_serializes_header_detail_approval_and_transition(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'a5-version.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    workflow = CaseWorkflowService()
    with Session(engine) as session:
        site_id = _seed_site(session)
        created = workflow.create_change_request(
            session,
            site_id=site_id,
            scope_label="Scope A",
            description="Description A",
            submitted_on=date(2026, 10, 1),
            requester_name="Requester A",
            reason=None,
            user=_editor(),
        )
        session.commit()
        change_id = created["change_request_id"]
        v1 = created["row_version"]

    with Session(engine) as session:
        header = workflow.update_change_request(
            session,
            change_request_id=change_id,
            expected_version=v1,
            scope_label=None,
            description="Description B",
            submitted_on=None,
            requester_name=None,
            reason="Update only description.",
            user=_editor(),
            fields_set={"expected_version", "description", "reason"},
        )
        session.commit()
        assert header["row_version"] > v1
        v2 = header["row_version"]
        row = session.get(ChangeRequest, change_id)
        assert row is not None
        assert row.scope_label == "Scope A"
        assert row.description == "Description B"

    with Session(engine) as session:
        detail = workflow.create_change_request_detail(
            session,
            change_request_id=change_id,
            expected_version=v2,
            classification_id=11,
            classification_label="Kho",
            approval_status=None,
            old_value="Cũ",
            new_value="Mới",
            note=None,
            reason="Add structured detail.",
            user=_editor(),
        )
        session.commit()
        assert detail["row_version"] > v2
        v3 = detail["row_version"]
        detail_id = detail["change_detail_id"]
        persisted = session.get(ChangeRequestDetail, detail_id)
        assert persisted is not None and persisted.legacy_change_detail_id is None

    with Session(engine) as session:
        under_review = workflow.transition_change_request(
            session,
            change_request_id=change_id,
            target_state="under_review",
            expected_version=v3,
            reason="Begin review.",
            user=_editor(),
        )
        session.commit()
        assert under_review["state"] == "under_review"
        v4 = under_review["row_version"]

    with Session(engine) as session:
        approval = workflow.upsert_change_approval(
            session,
            change_request_id=change_id,
            expected_version=v4,
            handled_on=date(2026, 10, 6),
            handled_by_name="Manager A5",
            result_label="Chấp thuận",
            effective_on=None,
            approval_reference="A5-DEC-1",
            reason="Record decision metadata.",
            user=_approver(),
            fields_set={"expected_version", "handled_on", "handled_by_name", "result_label", "approval_reference", "reason"},
        )
        session.commit()
        assert approval["row_version"] > v4
        v5 = approval["row_version"]
        assert approval["change_approval_id"] is not None

    with Session(engine) as session:
        accepted = workflow.transition_change_request(
            session,
            change_request_id=change_id,
            target_state="accepted",
            expected_version=v5,
            reason="Explicit decision transition.",
            user=_approver(),
        )
        session.commit()
        assert accepted["state"] == "accepted"
        v6 = accepted["row_version"]

        approval2 = workflow.upsert_change_approval(
            session,
            change_request_id=change_id,
            expected_version=v6,
            handled_on=None,
            handled_by_name=None,
            result_label=None,
            effective_on=date(2026, 10, 7),
            approval_reference=None,
            reason="Add effective date only.",
            user=_approver(),
            fields_set={"expected_version", "effective_on", "reason"},
        )
        session.commit()
        v7 = approval2["row_version"]

        effective = workflow.transition_change_request(
            session,
            change_request_id=change_id,
            target_state="effective",
            expected_version=v7,
            reason="Make change effective.",
            user=_approver(),
        )
        session.commit()
        assert effective["state"] == "effective"

    with Session(engine) as session:
        with pytest.raises(HTTPException, match="read-only"):
            workflow.update_change_request(
                session,
                change_request_id=change_id,
                expected_version=effective["row_version"],
                scope_label="Must fail",
                description=None,
                submitted_on=None,
                requester_name=None,
                reason=None,
                user=_editor(),
                fields_set={"scope_label"},
            )


def test_a5_stale_child_write_fails_before_mutating_or_auditing(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'a5-stale.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    workflow = CaseWorkflowService()
    with Session(engine) as session:
        site_id = _seed_site(session)
        created = workflow.create_change_request(
            session,
            site_id=site_id,
            scope_label="Initial",
            description=None,
            submitted_on=None,
            requester_name=None,
            reason=None,
            user=_editor(),
        )
        session.commit()
        change_id = created["change_request_id"]
        stale_version = created["row_version"]

    with Session(engine) as session:
        latest = workflow.create_change_request_detail(
            session,
            change_request_id=change_id,
            expected_version=stale_version,
            classification_id=None,
            classification_label="First",
            approval_status=None,
            old_value=None,
            new_value="1",
            note=None,
            reason=None,
            user=_editor(),
        )
        session.commit()

    with Session(engine) as session:
        before_count = session.query(ChangeRequestDetail).count()
        before_audits = session.query(AuditEvent).count()
        with pytest.raises(HTTPException, match="version mismatch"):
            workflow.create_change_request_detail(
                session,
                change_request_id=change_id,
                expected_version=stale_version,
                classification_id=None,
                classification_label="Stale",
                approval_status=None,
                old_value=None,
                new_value="2",
                note=None,
                reason=None,
                user=_editor(),
            )
        session.rollback()
        assert session.query(ChangeRequestDetail).count() == before_count
        assert session.query(AuditEvent).count() == before_audits
        row = session.get(ChangeRequest, change_id)
        assert row is not None and row.row_version == latest["row_version"]


@pytest.mark.parametrize(
    ("initial_state", "target_state", "allowed"),
    [
        (ChangeRequestState.RECEIVED, "under_review", True),
        (ChangeRequestState.RECEIVED, "accepted", False),
        (ChangeRequestState.UNDER_REVIEW, "accepted", True),
        (ChangeRequestState.UNDER_REVIEW, "rejected", True),
        (ChangeRequestState.ACCEPTED, "effective", True),
        (ChangeRequestState.REJECTED, "under_review", False),
        (ChangeRequestState.EFFECTIVE, "superseded", False),
        (ChangeRequestState.SUPERSEDED, "received", False),
    ],
)
def test_a5_transition_graph_is_explicit_and_does_not_infer_from_approval(tmp_path, initial_state, target_state, allowed):
    engine = create_engine(f"sqlite:///{(tmp_path / f'a5-transition-{initial_state.value}-{target_state}.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    workflow = CaseWorkflowService()
    with Session(engine) as session:
        site_id = _seed_site(session)
        row = ChangeRequest(site_id=site_id, state=initial_state)
        session.add(row)
        session.flush()
        # Approval existence must not imply accepted/rejected state.
        session.add(ChangeApproval(change_request_id=row.id, result_label="Legacy/intermediate approval text"))
        session.commit()
        change_id, version = row.id, row.row_version

    with Session(engine) as session:
        if allowed:
            result = workflow.transition_change_request(
                session,
                change_request_id=change_id,
                target_state=target_state,
                expected_version=version,
                reason=None,
                user=_approver(),
            )
            session.commit()
            assert result["state"] == target_state
        else:
            with pytest.raises(HTTPException, match="not allowed"):
                workflow.transition_change_request(
                    session,
                    change_request_id=change_id,
                    target_state=target_state,
                    expected_version=version,
                    reason=None,
                    user=_approver(),
                )


def test_a5_legacy_ids_are_read_only_across_runtime_mutations(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'a5-legacy-id.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    workflow = CaseWorkflowService()
    with Session(engine) as session:
        site_id = _seed_site(session)
        row = ChangeRequest(
            legacy_change_request_id=123,
            site_id=site_id,
            scope_label="Legacy",
            state=ChangeRequestState.RECEIVED,
        )
        session.add(row)
        session.flush()
        detail = ChangeRequestDetail(
            legacy_change_detail_id=456,
            change_request_id=row.id,
            classification_label="Legacy detail",
        )
        session.add(detail)
        session.commit()
        change_id, detail_id, version = row.id, detail.id, row.row_version

    with Session(engine) as session:
        result = workflow.update_change_request_detail(
            session,
            change_detail_id=detail_id,
            expected_version=version,
            classification_id=None,
            classification_label="Updated",
            approval_status=None,
            old_value=None,
            new_value=None,
            note=None,
            reason=None,
            user=_editor(),
            fields_set={"classification_label"},
        )
        session.commit()
        row = session.get(ChangeRequest, change_id)
        detail = session.get(ChangeRequestDetail, detail_id)
        assert row is not None and row.legacy_change_request_id == 123
        assert detail is not None and detail.legacy_change_detail_id == 456
        assert result["row_version"] == row.row_version
