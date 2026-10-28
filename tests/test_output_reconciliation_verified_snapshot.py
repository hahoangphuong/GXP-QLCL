"""Verified-snapshot output report: PostgreSQL and fail-closed tests."""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from backend.app.document.output_reconciliation import OutputLocator
from backend.app.document.output_reconciliation_snapshot import (
    reconcile_output_locators_verified_snapshot,
)


def test_verified_snapshot_rejects_other_database_engines_before_query():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with pytest.raises(ValueError, match="require PostgreSQL"):
            reconcile_output_locators_verified_snapshot(
                engine, [OutputLocator("inspection", "x.docx")]
            )
    finally:
        engine.dispose()


DATABASE_URL = os.environ.get("DATABASE_URL", "")


@pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="requires PostgreSQL test database",
)
def test_verified_snapshot_sets_read_only_repeatable_read_and_retains_no_transaction():
    engine = create_engine(DATABASE_URL, future=True)
    try:
        report = reconcile_output_locators_verified_snapshot(
            engine, [OutputLocator("inspection", "never-registered/unknown.docx")]
        )
        assert report.db_snapshot_consistency == (
            "postgresql_repeatable_read_read_only_verified"
        )
        assert report.deletion_authorized is False
        assert report.status == "review_only"
        assert report.items[0].review_flags == ("no_exact_db_reference",)

        # A failed locator validation must not leak a transaction.
        with pytest.raises(ValueError, match="Unsafe"):
            reconcile_output_locators_verified_snapshot(
                engine, [OutputLocator("inspection", "../unsafe.docx")]
            )
        with engine.connect() as connection:
            read_only, isolation = connection.execute(text(
                "SELECT current_setting('transaction_read_only'), "
                "current_setting('transaction_isolation')"
            )).one()
            # SET TRANSACTION must not modify connection defaults.
            assert read_only == "off"
            assert isolation == "read committed"
            connection.rollback()
    finally:
        engine.dispose()
