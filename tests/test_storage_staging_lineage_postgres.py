"""Opt-in integration coverage against the disposable CI PostgreSQL service.

The gate intentionally fails closed unless the DB name and loopback host
match the dedicated test environment. It never uses a VM or production DB.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.storage.staging import StagingAudit, StagingCandidate
from backend.app.storage.staging_lineage import reconcile_staging_lineage
from tools.reconcile_storage_staging_lineage import _read_only_reconcile


if os.environ.get("GXP_STAGING_LINEAGE_POSTGRES_INTEGRATION") != "1":
    pytest.skip("Opt-in disposable PostgreSQL staging-lineage gate only.", allow_module_level=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
EXPECTED_DATABASE = os.environ.get("GXP_STAGING_LINEAGE_DISPOSABLE_DATABASE", "")
url = make_url(DATABASE_URL) if DATABASE_URL else None
if (
    url is None
    or url.get_backend_name() != "postgresql"
    or not EXPECTED_DATABASE
    or not EXPECTED_DATABASE.startswith("gxp_qlcl_test")
    or url.database != EXPECTED_DATABASE
    or url.host not in {"127.0.0.1", "localhost"}
):
    raise RuntimeError("Staging lineage PostgreSQL gate requires the disposable CI database on loopback.")


def _inventory(*keys: tuple[str, str]) -> StagingAudit:
    return StagingAudit(
        candidates=tuple(StagingCandidate(root=root, relative_path=path,
                                          category="managed_candidate", size=10)
                         for root, path in keys),
        scanned_directories=1, scanned_entries=len(keys),
        truncated=False, incomplete_reason=None,
    )


def test_postgres_exact_lineage_lookups_use_real_uuid_and_read_only_transaction():
    engine = create_engine(DATABASE_URL, future=True)
    dv_id, template_id, binding_id = (str(uuid4()) for _ in range(3))
    try:
        with engine.connect() as conn:
            # PostgreSQL session-local shadow tables prevent any INSERT into
            # application tables; the DB itself is a throwaway CI service.
            conn.exec_driver_sql(
                "CREATE TEMP TABLE document_version "
                "(id uuid, storage_root text, storage_relative_path text) "
                "ON COMMIT PRESERVE ROWS"
            )
            conn.exec_driver_sql(
                "CREATE TEMP TABLE template_definition "
                "(id uuid, template_storage_root text, template_storage_relative_path text) "
                "ON COMMIT PRESERVE ROWS"
            )
            conn.exec_driver_sql(
                "CREATE TEMP TABLE storage_binding "
                "(id uuid, relative_path text) ON COMMIT PRESERVE ROWS"
            )
            conn.exec_driver_sql(
                "INSERT INTO document_version (id, storage_root, storage_relative_path) "
                "(VALUES (%s, %s, %s))",
                (dv_id, "inspection", "2026/site/.gxp-stage-abc123.tmp"),
            )
            conn.exec_driver_sql(
                "INSERT INTO template_definition "
                "(id, template_storage_root, template_storage_relative_path) "
                "(VALUES (%s, %s, %s))",
                (template_id, "template", "word/.gxp-stage-abc123.tmp"),
            )
            conn.exec_driver_sql(
                "INSERT INTO storage_binding (id, relative_path) "
                "(VALUES (%s, %s))",
                (binding_id, "2026/site"),
            )
            conn.commit()
            transaction = conn.begin()
            try:
                conn.exec_driver_sql("SET TRANSACTION READ ONLY")
                assert conn.exec_driver_sql("SHOW transaction_read_only").scalar_one() == "on"
                with Session(bind=conn, autoflush=False) as session:
                    report = reconcile_staging_lineage(
                        session,
                        _inventory(
                            ("inspection", "2026/site/.gxp-stage-abc123.tmp"),
                            ("template", "word/.gxp-stage-abc123.tmp"),
                            ("dkkd", "2026/site/.gxp-stage-abc123.tmp"),
                        ),
                    )
                indexed = {(item.root, item.relative_path): item for item in report.items}
                inspection = indexed[("inspection", "2026/site/.gxp-stage-abc123.tmp")]
                assert inspection.document_version_ids == (dv_id,)
                assert inspection.enclosing_inspection_binding_ids == (binding_id,)
                assert inspection.evidence == "registered_exact_locator"
                template = indexed[("template", "word/.gxp-stage-abc123.tmp")]
                assert template.template_definition_ids == (template_id,)
                assert template.evidence == "registered_exact_locator"
                dkkd = indexed[("dkkd", "2026/site/.gxp-stage-abc123.tmp")]
                assert dkkd.evidence == "no_exact_locator_evidence"
                assert dkkd.enclosing_inspection_binding_ids == ()
                assert report.status == "review_only"
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def test_postgres_read_only_cli_path_against_real_disposable_database():
    # This queries only non-existent locators in the migrated disposable DB.
    # A transaction-level read-only assertion occurs before the three SELECTs.
    report = _read_only_reconcile(
        DATABASE_URL,
        _inventory(
            ("inspection", "not-a-real-folder/.gxp-stage-feed1234.tmp"),
            ("dkkd", "also-not-real/.gxp-stage-cafe1234.tmp"),
        ),
    )
    assert report.status == "review_only"
    assert report.inspected_candidates == 2
    assert all(item.evidence == "no_exact_locator_evidence" for item in report.items)


def test_postgres_lineage_query_batches_large_inventory_without_mutation():
    engine = create_engine(DATABASE_URL, future=True)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                conn.exec_driver_sql("SET TRANSACTION READ ONLY")
                inventory = _inventory(*((
                    "inspection", f"unregistered-2026/a-{index}/.gxp-stage-abcdef12.tmp"
                ) for index in range(205)))
                with Session(bind=conn, autoflush=False) as session:
                    report = reconcile_staging_lineage(session, inventory)
                assert report.inspected_candidates == 205
                assert report.status == "review_only"
            finally:
                tx.rollback()
    finally:
        engine.dispose()
