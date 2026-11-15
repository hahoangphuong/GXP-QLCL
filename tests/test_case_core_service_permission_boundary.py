"""Case service mutations must enforce the router-equivalent edit capability.

The session sentinel deliberately has no database API. Unauthorized calls
must fail before resource lookup, row locks, DML, or audit.
"""
from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from backend.app.auth import build_authenticated_user
from backend.app.services.workflow import CaseWorkflowService


_CASE_MUTATIONS = (
    "create_initial_inspection_case",
    "create_inspection_case",
    "transition_case",
    "upsert_case_application",
    "upsert_case_assessment",
    "upsert_evaluation_scope",
)


@pytest.mark.parametrize("method_name", _CASE_MUTATIONS)
@pytest.mark.parametrize(
    ("role", "permissions"),
    [
        ("reader", frozenset({"case.view"})),
        ("manager", frozenset({"inspection.edit", "certificate.issue"})),
    ],
)
def test_case_mutation_denies_direct_calls_before_any_database_access(
    method_name: str, role: str, permissions: frozenset[str],
):
    method = getattr(CaseWorkflowService(), method_name)
    user = build_authenticated_user(
        "synthetic-unprivileged-case", role, permissions=permissions,
    )
    kwargs = {
        name: None
        for name, parameter in inspect.signature(method).parameters.items()
        if parameter.default is inspect.Parameter.empty
    }
    kwargs["session"] = object()
    kwargs["user"] = user
    with pytest.raises(HTTPException) as error:
        method(**kwargs)
    assert error.value.status_code == 403
    assert "permission" in str(error.value.detail).lower()
