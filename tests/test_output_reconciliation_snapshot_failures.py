"""Failure injection: a verified report must not escape an incomplete transaction.

All cases use bounded fake connections; no live database or storage touched.
"""
from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

import backend.app.document.output_reconciliation_snapshot as snapshot
from backend.app.document.output_reconciliation import (
    OutputLocator, OutputReconciliationReport,
)


class _Transaction:
    def __init__(self, *, fail_rollback=False):
        self.rollback_calls = 0
        self.fail_rollback = fail_rollback

    def rollback(self):
        self.rollback_calls += 1
        if self.fail_rollback:
            raise OSError("rollback failed")


class _Connection:
    def __init__(self, *, fail_on=None, settings=("repeatable read", "on"), fail_rollback=False):
        self.fail_on = fail_on
        self.settings = settings
        self.transaction = _Transaction(fail_rollback=fail_rollback)
        self.execute_calls = 0
        self.begin_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def begin(self):
        self.begin_calls += 1
        return self.transaction

    def execute(self, statement):
        self.execute_calls += 1
        if self.fail_on == self.execute_calls:
            raise RuntimeError("database query failed")
        return SimpleNamespace(one=lambda: self.settings)


class _Engine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, connection):
        self.connection = connection
        self.connect_calls = 0

    def connect(self):
        self.connect_calls += 1
        return self.connection


class _Session:
    def __init__(self, *, bind, **_):
        self.connection = bind

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.mark.parametrize(
    ("fail_on", "settings", "fail_report"),
    [
        (1, ("repeatable read", "on"), False),
        (2, ("repeatable read", "on"), False),
        (None, ("read committed", "on"), False),
        (None, ("repeatable read", "off"), False),
        (None, ("repeatable read", "on"), True),
    ],
)
def test_snapshot_rollback_once_on_all_failures(
    monkeypatch, fail_on, settings, fail_report,
):
    connection = _Connection(fail_on=fail_on, settings=settings)
    monkeypatch.setattr(snapshot, "Session", _Session)

    def inspect(*_, **__):
        if fail_report:
            raise RuntimeError("reconciliation failed")
        return OutputReconciliationReport(items=())

    monkeypatch.setattr(snapshot, "reconcile_output_locators", inspect)
    with pytest.raises(RuntimeError):
        snapshot.reconcile_output_locators_verified_snapshot(
            _Engine(connection), [OutputLocator("inspection", "case/file.docx")],
        )
    assert connection.begin_calls == 1
    assert connection.transaction.rollback_calls == 1


def test_snapshot_rollback_failure_cannot_claim_verified(monkeypatch):
    connection = _Connection(fail_rollback=True)
    monkeypatch.setattr(snapshot, "Session", _Session)
    monkeypatch.setattr(
        snapshot, "reconcile_output_locators",
        lambda *_, **__: OutputReconciliationReport(items=()),
    )
    with pytest.raises(OSError, match="rollback failed"):
        snapshot.reconcile_output_locators_verified_snapshot(
            _Engine(connection), [OutputLocator("inspection", "case/file.docx")],
        )
    assert connection.transaction.rollback_calls == 1


def test_snapshot_success_requires_finished_rollback(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(snapshot, "Session", _Session)
    monkeypatch.setattr(
        snapshot, "reconcile_output_locators",
        lambda *_, **__: OutputReconciliationReport(items=()),
    )
    report = snapshot.reconcile_output_locators_verified_snapshot(
        _Engine(connection), [OutputLocator("inspection", "case/file.docx")],
    )
    assert connection.transaction.rollback_calls == 1
    assert report.db_snapshot_consistency == (
        "postgresql_repeatable_read_read_only_verified"
    )
    assert report.deletion_authorized is False
