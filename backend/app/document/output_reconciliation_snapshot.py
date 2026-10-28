"""Verified, caller-independent PostgreSQL snapshot for output evidence.

Owns a short-lived read-only REPEATABLE READ transaction and never exposes
a cleanup authorization. It cannot establish filesystem generation identity.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.document.output_reconciliation import (
    OutputLocator, OutputReconciliationReport, reconcile_output_locators,
)


def reconcile_output_locators_verified_snapshot(
    engine: Engine,
    locators: Sequence[OutputLocator],
    *,
    max_locators: int = 1000,
) -> OutputReconciliationReport:
    """SELECT-only report from an owned PostgreSQL read-only stable snapshot.

    Do not accept caller sessions: a pre-existing transaction may already
    have chosen weaker isolation or executed a write.
    """
    if engine.dialect.name != "postgresql":
        raise ValueError("Verified output snapshots require PostgreSQL.")
    # Open a fresh connection and set the transaction guarantees before the
    # first SQL statement. SET TRANSACTION is transaction-local.
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            ))
            isolation, read_only = connection.execute(text(
                "SELECT current_setting('transaction_isolation'), "
                "current_setting('transaction_read_only')"
            )).one()
            if isolation != "repeatable read" or read_only != "on":
                raise RuntimeError("PostgreSQL read-only stable snapshot was not established.")
            with Session(bind=connection, autoflush=False, expire_on_commit=False) as session:
                report = reconcile_output_locators(
                    session, locators, max_locators=max_locators,
                )
            # No explicit commit: roll back the read-only transaction.
            connection.rollback()
    return replace(
        report, db_snapshot_consistency="postgresql_repeatable_read_read_only_verified",
    )
