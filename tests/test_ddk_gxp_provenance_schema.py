"""Additive DDK group source-provenance contract, not canonical links."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, insert
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from backend.app.db.models import Base
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate,
    BusinessEligibilityCertificateLink,
    BusinessEligibilityGxpSourceGroup,
    BusinessEligibilityGxpReferenceEvidence,
    BusinessEligibilityVersion,
)


MIGRATION = Path("migrations/versions/20261012_0023_ddk_gxp_source_provenance.py")


def _source_row(*, group="GDP", row_number=7, col=27):
    return {
        "id": str(uuid4()),
        "source_workbook_sha256": "a" * 64,
        "source_sheet_name": "db.dkkd",
        "source_row_number": row_number,
        "legacy_dkkd_id": 400,
        "source_group": group,
        "id_cc_excel_column": col,
        "certificate_scope_excel_column": col + 1,
        "applicable_standard_excel_column": col + 2,
        "business_activity_excel_column": col + 3,
        "id_cc_raw": "",
        "certificate_scope_raw": "",
        "applicable_standard_raw": "",
        "business_activity_raw": " Bán buôn thuốc\n",
        "source_values_sha256": "b" * 64,
    }


def _migration():
    spec = importlib.util.spec_from_file_location("ddk_0023", MIGRATION)
    assert spec and spec.loader
    import sys
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _tables():
    return (BusinessEligibilityGxpSourceGroup.__table__,
            BusinessEligibilityGxpReferenceEvidence.__table__)


def test_additive_tables_leave_canonical_eligibility_model_untouched():
    group, refs = _tables()
    assert {group.name, refs.name}.issubset(Base.metadata.tables)
    assert {"source_workbook_sha256", "source_sheet_name", "source_row_number",
            "legacy_dkkd_id", "source_group", "id_cc_excel_column",
            "certificate_scope_excel_column", "applicable_standard_excel_column",
            "business_activity_excel_column", "id_cc_raw", "certificate_scope_raw",
            "applicable_standard_raw", "business_activity_raw",
            "source_values_sha256"} <= set(group.c.keys())
    assert all(not group.c[name].nullable for name in (
        "id_cc_raw", "certificate_scope_raw", "applicable_standard_raw",
        "business_activity_raw"))
    assert {"source_group_id", "token_index", "raw_token",
            "parsed_legacy_certificate_id"} <= set(refs.c.keys())
    assert refs.c.parsed_legacy_certificate_id.nullable
    assert refs.c.raw_token.nullable is False

    # Source tables must not assert a canonical GxP or DDK version link.
    group_fks = {fk.target_fullname for fk in group.foreign_keys}
    ref_fks = {fk.target_fullname for fk in refs.foreign_keys}
    assert group_fks == set()
    assert ref_fks == {f"{group.name}.id"}
    for forbidden in ("certificate_id", "certificate_version_id",
                      "business_eligibility_version_id", "site_id", "company_id",
                      "approval_status", "link_role"):
        assert forbidden not in group.c
        assert forbidden not in refs.c
    assert "business_activity_text" in BusinessEligibilityVersion.__table__.c
    assert "legacy_dkkd_id" in BusinessEligibilityCertificate.__table__.c
    assert "certificate_id" in BusinessEligibilityCertificateLink.__table__.c

    for table in (group, refs):
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert "CREATE TABLE" in ddl
        assert "CHECK" in ddl


def test_source_tables_preserve_companions_without_id_cc_and_token_identity():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    group, refs = _tables()
    Base.metadata.create_all(engine, tables=[group, refs])
    with engine.begin() as conn:
        src = _source_row()
        conn.execute(insert(group).values(**src))
        assert conn.execute(group.select()).mappings().one()["business_activity_raw"] == " Bán buôn thuốc\n"
        # Multiple independent source tokens, without a canonical Certificate FK.
        conn.execute(insert(refs).values(
            id=str(uuid4()), source_group_id=src["id"], token_index=1,
            raw_token="200", parsed_legacy_certificate_id=200,
        ))
        conn.execute(insert(refs).values(
            id=str(uuid4()), source_group_id=src["id"], token_index=2,
            raw_token="", parsed_legacy_certificate_id=None,
        ))
    with engine.connect() as conn:
        rows = conn.execute(refs.select().order_by(refs.c.token_index)).mappings().all()
        assert [(r["token_index"], r["raw_token"]) for r in rows] == [(1, "200"), (2, "")]

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(insert(refs).values(
                id=str(uuid4()), source_group_id=src["id"], token_index=1,
                raw_token="duplicate", parsed_legacy_certificate_id=201,
            ))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(insert(group).values(**{
                **_source_row(row_number=8), "id_cc_excel_column": 27,
                "certificate_scope_excel_column": 29,
            }))


def test_same_workbook_row_role_is_unique_but_different_roles_and_rows_survive():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    group, refs = _tables()
    Base.metadata.create_all(engine, tables=[group, refs])
    with engine.begin() as conn:
        conn.execute(insert(group).values(**_source_row(group="GMP", col=15)))
        conn.execute(insert(group).values(**_source_row(group="GLP", col=19)))
        conn.execute(insert(group).values(**_source_row(group="GMP", row_number=8, col=15)))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(insert(group).values(**_source_row(group="GMP", col=15)))


def test_0023_upgrade_is_empty_and_downgrade_refuses_source_data():
    migration = _migration()
    assert migration.revision == "20261012_0023"
    assert migration.down_revision == "20261008_0022"
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        inspector = inspect(conn)
        assert {
            "business_eligibility_gxp_source_group",
            "business_eligibility_gxp_reference_evidence",
        } <= set(inspector.get_table_names())
        group = BusinessEligibilityGxpSourceGroup.__table__
        conn.execute(insert(group).values(**_source_row()))
        with pytest.raises(RuntimeError, match="contains 1 evidence rows"):
            migration.downgrade()
        assert group.name in inspect(conn).get_table_names()
        conn.execute(group.delete())
        migration.downgrade()
        tables = set(inspect(conn).get_table_names())
        assert group.name not in tables
        assert BusinessEligibilityGxpReferenceEvidence.__tablename__ not in tables
