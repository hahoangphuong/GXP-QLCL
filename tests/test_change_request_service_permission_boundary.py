from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from backend.app.auth import build_authenticated_user
from backend.app.services.workflow import CaseWorkflowService


# The actor must be denied before any resource identity lookup, locking, audit,
# autoflush or mutation. A direct service call cannot rely on HTTP router RBAC.
@pytest.mark.parametrize(
    ("method_name", "target_state", "missing_permission"),
    [
        ("create_change_request", None, "change_request.edit"),
        ("issue_change_request_certificate_successor", None, "certificate.issue"),
        ("issue_change_request_business_eligibility_successor", None, "certificate.issue"),
        ("update_change_request", None, "change_request.edit"),
        ("create_change_request_detail", None, "change_request.edit"),
        ("update_change_request_detail", None, "change_request.edit"),
        ("upsert_change_approval", None, "change_request.approve"),
        ("transition_change_request", "under_review", "change_request.edit"),
        ("transition_change_request", "accepted", "change_request.approve"),
    ],
)
def test_change_request_service_denies_before_database_access(
    method_name: str, target_state: str | None, missing_permission: str
):
    service = CaseWorkflowService()
    method = getattr(service, method_name)
    all_permissions = {
        "change_request.edit",
        "change_request.approve",
        "certificate.issue",
    }
    actor = build_authenticated_user(
        "unauthorized-direct-caller",
        "admin",
        permissions=all_permissions - {missing_permission},
    )
    arguments = {
        name: None
        for name, parameter in inspect.signature(method).parameters.items()
        if parameter.default is inspect.Parameter.empty
    }
    arguments["session"] = object()  # Any DB access would fail this test.
    arguments["user"] = actor
    if target_state is not None:
        arguments["target_state"] = target_state

    with pytest.raises(HTTPException) as error:
        method(**arguments)
    assert error.value.status_code == 403


def test_change_request_service_rejects_invalid_transition_without_database_access():
    service = CaseWorkflowService()
    actor = build_authenticated_user(
        "invalid-target-actor",
        "manager",
        permissions={"change_request.edit", "change_request.approve"},
    )
    with pytest.raises(HTTPException) as error:
        service.transition_change_request(
            object(), change_request_id="not-a-real-uuid",
            target_state="unknown_state", expected_version=1,
            reason=None, user=actor,
        )
    assert error.value.status_code == 422
