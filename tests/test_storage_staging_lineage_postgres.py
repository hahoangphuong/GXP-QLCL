"""Opt-in integration coverage against the disposable CI PostgreSQL service.

The gate intentionally fails closed unless the DB name and loopback host
match the dedicated test environment. It never uses a VM or production DB.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.db.enums import CaseState, DocumentVariantType
from backend.app.db.models.phase1 import (
    Case, Company, Document, DocumentVariant, DocumentVersion,
    Site, StorageBinding, TemplateDefinition,
)
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


@pytest.fixture
def disposable_reader_url():
    # An isolated, temporary login with only the minimum three SELECT
    # grants. Provisioning and cleanup occur exclusively in the named
    # disposable CI database; the module-level gate forbids a VM target.
    role = "gxp_stage_reader_" + uuid4().hex[:12]
    password = uuid4().hex
    admin = create_engine(DATABASE_URL, future=True, isolation_level="AUTOCOMMIT")
    created = False
    try:
        with admin.connect() as conn:
            conn.exec_driver_sql(f"CREATE ROLE {role} LOGIN PASSWORD '{password}'")
            created = True
            conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {role}")
            conn.exec_driver_sql(
                f"GRANT SELECT ON TABLE public.document_version, "
                f"public.template_definition, public.storage_binding TO {role}"
            )
        yield make_url(DATABASE_URL).set(username=role, password=password)
    finally:
        try:
            if created:
                with admin.connect() as conn:
                    conn.exec_driver_sql(
                        f"REVOKE SELECT ON TABLE public.document_version, "
                        f"public.template_definition, public.storage_binding FROM {role}"
                    )
                    conn.exec_driver_sql(f"REVOKE USAGE ON SCHEMA public FROM {role}")
                    conn.exec_driver_sql(f"DROP ROLE {role}")
        finally:
            admin.dispose()


def test_postgres_exact_lineage_lookups_use_real_migrated_tables(disposable_reader_url):
    # Seed real migrated tables in the disposable CI database, not shadow
    # tables. This proves both FK-backed document lineage and actual schema
    # lookup. All seeded rows are cleaned up in reverse dependency order.
    engine = create_engine(DATABASE_URL, future=True)
    ids = {name: str(uuid4()) for name in (
        "company", "site", "case", "document", "variant", "version",
        "template", "binding",
    )}
    suffix = uuid4().hex[:10]
    folder = f"2026/ci-stage-{suffix}"
    inspection_path = folder + "/.gxp-stage-abc123.tmp"
    template_path = f"word/ci-stage-{suffix}/.gxp-stage-abc123.tmp"
    seeded = False
    try:
        with Session(engine) as seed:
            seed.add(Company(id=ids["company"], legal_name="Disposable CI staging lineage"))
            seed.flush()
            seed.add(Site(id=ids["site"], company_id=ids["company"], site_name="CI site"))
            seed.flush()
            seed.add(Case(id=ids["case"], site_id=ids["site"], gxp_type="GMP", state=CaseState.DRAFT))
            seed.flush()
            seed.add(Document(
                id=ids["document"], family_code="STAGING_AUDIT",
                document_type_code="CI_DOCUMENT", case_id=ids["case"],
            ))
            seed.flush()
            seed.add(DocumentVariant(
                id=ids["variant"], document_id=ids["document"],
                variant_type=DocumentVariantType.EDITABLE_DOCX,
            ))
            seed.flush()
            seed.add(DocumentVersion(
                id=ids["version"], document_variant_id=ids["variant"],
                version_no=1, storage_root="inspection",
                storage_relative_path=inspection_path,
            ))
            seed.add(TemplateDefinition(
                id=ids["template"], family_code="STAGING_AUDIT",
                document_type_code="CI_TEMPLATE", source_application="word",
                storage_scope="inspection_folder",
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                template_name=f"CI {suffix}", template_storage_root="template",
                template_storage_relative_path=template_path,
            ))
            seed.add(StorageBinding(
                id=ids["binding"], year=2026,
                site_legacy_id=int(uuid4().hex[:7], 16),
                inspection_legacy_code=f"CI-{suffix}",
                relative_path=folder, storage_class="synology_legacy",
            ))
            seed.commit()
            seeded = True

        inventory = _inventory(
            ("inspection", inspection_path),
            ("template", template_path),
            ("dkkd", inspection_path),
        )
        # Deliberately shadow public table names with incomplete temp tables,
        # then pin pg_temp LAST. The audit must still return real public UUIDs.
        with engine.connect() as conn:
            for table in ("document_version", "template_definition", "storage_binding"):
                conn.exec_driver_sql(f"CREATE TEMP TABLE {table} (bogus text)")
            conn.commit()
            tx = conn.begin()
            try:
                conn.exec_driver_sql("SET TRANSACTION READ ONLY")
                conn.exec_driver_sql("SET LOCAL search_path = pg_catalog, public, pg_temp")
                assert conn.exec_driver_sql("SHOW transaction_read_only").scalar_one() == "on"
                with Session(bind=conn, autoflush=False) as readonly:
                    report = reconcile_staging_lineage(readonly, inventory)
            finally:
                tx.rollback()
            conn.exec_driver_sql(
                "DROP TABLE pg_temp.document_version, "
                "pg_temp.template_definition, pg_temp.storage_binding"
            )
            conn.commit()

        indexed = {(item.root, item.relative_path): item for item in report.items}
        inspection = indexed[("inspection", inspection_path)]
        assert inspection.document_version_ids == (ids["version"],)
        assert inspection.enclosing_inspection_binding_ids == (ids["binding"],)
        assert inspection.evidence == "registered_exact_locator"
        template = indexed[("template", template_path)]
        assert template.template_definition_ids == (ids["template"],)
        assert template.evidence == "registered_exact_locator"
        dkkd = indexed[("dkkd", inspection_path)]
        assert dkkd.evidence == "no_exact_locator_evidence"
        assert dkkd.enclosing_inspection_binding_ids == ()
        assert report.status == "review_only"

        # Exercise the full optional CLI owner with a truly SELECT-only login
        # and the same committed real-table locators.
        guarded = _read_only_reconcile(disposable_reader_url, inventory)
        assert guarded.items == report.items
        assert guarded.status == "review_only"
    finally:
        if seeded:
            with Session(engine) as cleanup:
                for cls, name in (
                    (DocumentVersion, "version"),
                    (DocumentVariant, "variant"),
                    (Document, "document"),
                    (StorageBinding, "binding"),
                    (TemplateDefinition, "template"),
                    (Case, "case"),
                    (Site, "site"),
                    (Company, "company"),
                ):
                    cleanup.execute(delete(cls).where(cls.id == ids[name]))
                cleanup.commit()
        engine.dispose()


def test_postgres_read_only_cli_path_against_real_disposable_database(disposable_reader_url):
    # This queries only non-existent locators in the migrated disposable DB.
    # A separate SELECT-only login and transaction read-only are both checked
    # before the lineage queries execute.
    report = _read_only_reconcile(
        disposable_reader_url,
        _inventory(
            ("inspection", "not-a-real-folder/.gxp-stage-feed1234.tmp"),
            ("dkkd", "also-not-real/.gxp-stage-cafe1234.tmp"),
        ),
    )
    assert report.status == "review_only"
    assert report.inspected_candidates == 2
    assert all(item.evidence == "no_exact_locator_evidence" for item in report.items)


def test_postgres_lineage_cli_rejects_admin_role_on_disposable_database():
    with pytest.raises(RuntimeError, match="dedicated metadata SELECT-only"):
        _read_only_reconcile(DATABASE_URL, _inventory(
            ("inspection", "nonexistent/.gxp-stage-fedcba.tmp")
        ))


def test_postgres_dedicated_reader_cannot_update_lineage_tables(disposable_reader_url):
    # A server-side permission rejection, not merely a client-side promise.
    engine = create_engine(disposable_reader_url, future=True)
    try:
        with engine.connect() as conn:
            assert conn.exec_driver_sql(
                "SELECT has_table_privilege(current_user, 'document_version', 'SELECT')"
            ).scalar_one()
            assert not conn.exec_driver_sql(
                "SELECT has_table_privilege(current_user, 'document_version', 'INSERT, UPDATE, DELETE')"
            ).scalar_one()
            with pytest.raises(DBAPIError):
                conn.exec_driver_sql(
                    "UPDATE document_version SET storage_relative_path = storage_relative_path WHERE FALSE"
                )
            conn.rollback()
    finally:
        engine.dispose()


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
