"""Real PostgreSQL multi-batch snapshot error regression.

A DB execution failure after a successful first locator batch must never
produce a verified (or partial) reconciliation report.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import backend.app.document.output_reconciliation_snapshot as snapshot
from backend.app.document.output_reconciliation import OutputLocator


DATABASE_URL = os.environ.get("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="requires PostgreSQL test database",
)


class _InjectFailureSession:
    """Delegate actual ORM SQL to PostgreSQL, fail on the second SELECT."""

    def __init__(self, *, bind, **kwargs):
        self._session = Session(bind=bind, **kwargs)
        self.no_autoflush = self._session.no_autoflush
        self._select_count = 0

    def __enter__(self):
        self._session.__enter__()
        return self

    def __exit__(self, *args):
        return self._session.__exit__(*args)

    def execute(self, statement, *args, **kwargs):
        self._select_count += 1
        if self._select_count == 2:
            # A real database error marks PostgreSQL's transaction aborted.
            self._session.execute(text("SELECT 1 / 0"))
            raise AssertionError("expected PostgreSQL division error")
        return self._session.execute(statement, *args, **kwargs)


def test_mid_batch_postgres_failure_is_rolled_back_without_verified_report(monkeypatch):
    engine = create_engine(DATABASE_URL, future=True, pool_size=1, max_overflow=0)
    original_session = snapshot.Session
    monkeypatch.setattr(snapshot, "Session", _InjectFailureSession)
    # 201 distinct validated locators force two real SELECT batches.
    locators = [
        OutputLocator("inspection", f"snapshot-error-probe/nonexistent-{i:03}.docx")
        for i in range(201)
    ]
    try:
        with pytest.raises(Exception) as exc:
            snapshot.reconcile_output_locators_verified_snapshot(engine, locators)
        assert "division by zero" in str(exc.value).lower()
        # Check out the same pooled connection after rollback. Transaction
        # must not be left aborted or read-only on the next borrower.
        with engine.connect() as connection:
            state = connection.execute(text(
                "SELECT current_setting('transaction_isolation'), "
                "current_setting('transaction_read_only')"
            )).one()
            assert state == ("read committed", "off")
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
            connection.rollback()
    finally:
        monkeypatch.setattr(snapshot, "Session", original_session)
        engine.dispose()
