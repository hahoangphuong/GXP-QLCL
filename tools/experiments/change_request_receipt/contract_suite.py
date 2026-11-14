"""CONTRACT_PENDING_APPROVAL: reusable assertions, not collected or wired to runtime.

A future integration suite must invoke these against the real, approved adapter,
not a mock, after creating isolated synthetic fixtures and authenticated users.
"""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Observation:
    result_id: str | None
    business_count: int
    audit_count: int
    disclosed: bool = False
    rejected: bool = False
    public_code: str | None = None


class RecoveryAdapter(Protocol):
    def create(self, *, operation_id: str, actor: str, site: str, payload: dict) -> Observation: ...
    def lookup(self, *, operation_id: str, actor: str, site: str) -> Observation: ...


def assert_same_intent_replay(adapter: RecoveryAdapter) -> None:
    first = adapter.create(operation_id='synthetic-op', actor='actor-a', site='site-a', payload={'scope': 'synthetic'})
    second = adapter.create(operation_id='synthetic-op', actor='actor-a', site='site-a', payload={'scope': 'synthetic'})
    assert first.result_id is not None and second.result_id == first.result_id
    assert second.business_count == first.business_count == 1
    assert second.audit_count == first.audit_count == 1


def assert_unauthorized_lookup(adapter: RecoveryAdapter) -> None:
    adapter.create(operation_id='synthetic-private', actor='actor-a', site='site-a', payload={'scope': 'synthetic'})
    result = adapter.lookup(operation_id='synthetic-private', actor='actor-b', site='site-a')
    assert not result.disclosed and result.result_id is None


def assert_cross_site_lookup(adapter: RecoveryAdapter) -> None:
    adapter.create(operation_id='synthetic-site', actor='actor-a', site='site-a', payload={'scope': 'synthetic'})
    result = adapter.lookup(operation_id='synthetic-site', actor='actor-a', site='site-b')
    assert not result.disclosed and result.result_id is None


def assert_same_id_different_payload_rejected(adapter: RecoveryAdapter) -> None:
    first = adapter.create(operation_id='synthetic-conflict', actor='actor-a', site='site-a', payload={'scope': 'one'})
    second = adapter.create(operation_id='synthetic-conflict', actor='actor-a', site='site-a', payload={'scope': 'two'})
    assert first.result_id is not None and second.rejected
    assert second.business_count == first.business_count == 1
    assert second.audit_count == first.audit_count == 1


def assert_same_id_different_actor_rejected(adapter: RecoveryAdapter) -> None:
    adapter.create(operation_id='synthetic-owner', actor='actor-a', site='site-a', payload={})
    result = adapter.create(operation_id='synthetic-owner', actor='actor-b', site='site-a', payload={})
    assert result.rejected and not result.disclosed and result.result_id is None
    assert result.business_count == result.audit_count == 1


def assert_same_id_different_site_rejected(adapter: RecoveryAdapter) -> None:
    adapter.create(operation_id='synthetic-owner', actor='actor-a', site='site-a', payload={})
    result = adapter.create(operation_id='synthetic-owner', actor='actor-a', site='site-b', payload={})
    assert result.rejected and not result.disclosed and result.result_id is None
    assert result.business_count == result.audit_count == 1


def assert_omitted_and_null_remain_distinct(adapter: RecoveryAdapter) -> None:
    """Use only when the approved command defines these field states differently."""
    adapter.create(operation_id='synthetic-field', actor='actor-a', site='site-a', payload={})
    result = adapter.create(operation_id='synthetic-field', actor='actor-a', site='site-a', payload={'scope': None})
    assert result.rejected and result.business_count == result.audit_count == 1


def assert_lookup_does_not_reveal_existence(adapter: RecoveryAdapter) -> None:
    adapter.create(operation_id='synthetic-secret', actor='actor-a', site='site-a', payload={})
    denied = adapter.lookup(operation_id='synthetic-secret', actor='actor-b', site='site-a')
    absent = adapter.lookup(operation_id='synthetic-absent', actor='actor-b', site='site-a')
    assert not denied.disclosed and not absent.disclosed
    assert denied.public_code is not None and denied.public_code == absent.public_code
