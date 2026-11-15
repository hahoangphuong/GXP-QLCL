"""Direct service-owner permission gates for inspection mutation entrypoints.

These probes intentionally provide a Session sentinel that cannot be used for
SQL. Denial must happen before looking up Case/Plan/Outcome/Team identities,
acquiring locks, flushing pending drafts, or writing audit events.
"""
from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from backend.app.auth import build_authenticated_user
from backend.app.services.workflow import CaseWorkflowService


@pytest.mark.parametrize(
    "method_name",
    [
        "upsert_inspection_plan",
        "upsert_inspection_outcome",
        "upsert_inspection_period_segments",
        "upsert_inspection_team",
    ],
)
def test_inspection_edit_mutations_reject_unprivileged_direct_calls_before_db(method_name: str):
    method = getattr(CaseWorkflowService(), method_name)
    actor = build_authenticated_user(
        "synthetic-inspection-outsider",
        "reader",
        permissions={"inspection.view"},
    )
    kwargs = {
        name: None
        for name, parameter in inspect.signature(method).parameters.items()
        if parameter.default is inspect.Parameter.empty
    }
    kwargs["session"] = object()
    kwargs["user"] = actor
    with pytest.raises(HTTPException) as error:
        method(**kwargs)
    assert error.value.status_code == 403
    assert "permission" in str(error.value.detail).lower()


@pytest.mark.parametrize(
    "method_name",
    [
        "upsert_inspection_plan",
        "upsert_inspection_outcome",
        "upsert_inspection_period_segments",
        "upsert_inspection_team",
    ],
)
def test_inspection_edit_mutations_require_exact_capability_not_role_name(method_name: str):
    method = getattr(CaseWorkflowService(), method_name)
    # A manager label alone carries no capability; explicit permission controls access.
    actor = build_authenticated_user(
        "synthetic-manager-no-edit",
        "manager",
        permissions={"inspection.view", "case.edit"},
    )
    kwargs = {
        name: None
        for name, parameter in inspect.signature(method).parameters.items()
        if parameter.default is inspect.Parameter.empty
    }
    kwargs["session"] = object()
    kwargs["user"] = actor
    with pytest.raises(HTTPException) as error:
        method(**kwargs)
    assert error.value.status_code == 403
