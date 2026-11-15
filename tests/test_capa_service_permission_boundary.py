from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from backend.app.auth import build_authenticated_user
from backend.app.services.workflow import CaseWorkflowService


@pytest.mark.parametrize(
    ("method_name", "required_permission"),
    [
        ("create_capa_cycle", "capa.edit"),
        ("update_capa_cycle", "capa.edit"),
        ("submit_capa_cycle", "capa.edit"),
        ("assess_capa_cycle", "capa.assess"),
    ],
)
def test_capa_mutation_denies_direct_service_call_before_database_access(
    method_name: str, required_permission: str
):
    service = CaseWorkflowService()
    method = getattr(service, method_name)
    actor = build_authenticated_user(
        "synthetic-unauthorized-capa-caller",
        "manager",
        permissions=({"capa.edit", "capa.assess"} - {required_permission}),
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
