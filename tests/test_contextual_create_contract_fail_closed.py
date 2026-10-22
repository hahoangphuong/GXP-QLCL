"""Blocked contextual document creates never publish a stale or unauthorized target."""
import pytest

from backend.app.document.contextual_actions import build_document_action_states


def _create(readiness, permissions):
    actions = build_document_action_states(
        open_available=False,
        history_available=False,
        create_readiness=readiness,
        permissions=frozenset(permissions),
        family_code="INSPECTION_QD_KT",
        parent_scope="case",
        parent_id="case-fixture",
        document_type_code=None,
        # Deliberately adversarial: future callers can accidentally pass a
        # previously computed target even after a Case becomes blocked.
        create_contract={
            "create_endpoint": "/cases/case-fixture/documents/inspection-ke-hoach-kt/render",
            "create_http_method": "POST",
            "create_input_readiness": "CANONICAL_INPUT_READY",
        },
    )
    return next(action for action in actions if action["action_key"] == "create")


@pytest.mark.parametrize("readiness", [
    "BUSINESS_INPUT_CONTRACT_MISSING", "BUSINESS_INPUT_NOT_READY",
    "UNSUPPORTED_GXP_TYPE", "STORAGE_WRITE_CONTRACT_MISSING",
    "READY_OPEN_HISTORY", "READY_READ_ONLY",
])
def test_blocked_create_never_advertises_endpoint_even_if_caller_passes_one(readiness):
    action = _create(readiness, {"document.read", "document.write"})
    assert action["available"] is False
    assert "create_endpoint" not in action
    assert "create_http_method" not in action
    assert action["create_input_readiness"] == "CANONICAL_INPUT_READY"


def test_permission_denied_never_advertises_unduly_computed_endpoint():
    action = _create("READY_CREATE_OPEN_HISTORY", {"document.read"})
    assert action["available"] is False
    assert action["reason_code"] == "permission_denied"
    assert "create_endpoint" not in action
    assert "create_http_method" not in action
    assert "create_input_readiness" not in action


def test_approved_create_keeps_canonical_typed_target():
    action = _create("READY_CREATE_OPEN_HISTORY", {"document.read", "document.write"})
    assert action["available"] is True
    assert action["create_endpoint"] == "/cases/case-fixture/documents/inspection-ke-hoach-kt/render"
    assert action["create_http_method"] == "POST"
    assert action["create_input_readiness"] == "CANONICAL_INPUT_READY"
