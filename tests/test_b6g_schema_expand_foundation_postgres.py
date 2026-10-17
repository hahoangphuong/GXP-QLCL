"""Opt-in disposable PostgreSQL coverage for the B6G expand migration.

The companion shell tool creates and drops a disposable database.  This module
never falls back to SQLite because partial indexes and PostgreSQL constraints
are the contract under test.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AppUser,
    Case,
    CaseScopePhase,
    CaseScopeRevision,
    Certificate,
    CertificateRelationship,
    Company,
    ProductionLine,
    ProductionLineTransformation,
    ProductionLineTransformationMember,
    Site,
)


if os.environ.get("B6G_POSTGRES_INTEGRATION") != "1":
    pytest.skip("set B6G_POSTGRES_INTEGRATION=1 to run disposable PostgreSQL coverage", allow_module_level=True)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith("postgresql"):
    raise RuntimeError("B6G PostgreSQL integration requires an explicit PostgreSQL DATABASE_URL")
if not (make_url(DATABASE_URL).database or "").startswith("gxp_b6g_test_"):
    raise RuntimeError("B6G PostgreSQL integration requires a disposable gxp_b6g_test_ database")

def _alembic(*args: str) -> None:
    environment = {**os.environ, "DATABASE_URL": DATABASE_URL}
    subprocess.run([sys.executable, "-m", "alembic", *args], check=True, env=environment)


@pytest.fixture()
def postgres_engine():
    engine = create_engine(DATABASE_URL, future=True)
    try:
        with engine.connect() as connection:
            assert connection.dialect.name == "postgresql"
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260915_0016"
        yield engine
    finally:
        engine.dispose()


def test_b6g_upgrade_constraints_downgrade_and_second_upgrade(postgres_engine):
    _alembic("upgrade", "20260929_0017")
    with postgres_engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260929_0017"
        index_names = set(
            connection.scalars(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = current_schema() AND tablename = 'case_scope_revision'"
                )
            )
        )
        assert {"uq_case_scope_revision_one_draft", "uq_case_scope_revision_one_current_established"} <= index_names
        member_unique_constraints = {
            name: tuple(columns)
            for name, columns in connection.execute(
                text(
                    "SELECT constraint_name, array_agg(column_name ORDER BY ordinal_position) "
                    "FROM ("
                    "  SELECT con.conname AS constraint_name, att.attname AS column_name, ord.ordinality AS ordinal_position "
                    "  FROM pg_constraint con "
                    "  JOIN pg_class table_class ON table_class.oid = con.conrelid "
                    "  JOIN unnest(con.conkey) WITH ORDINALITY AS ord(attnum, ordinality) ON TRUE "
                    "  JOIN pg_attribute att ON att.attrelid = table_class.oid AND att.attnum = ord.attnum "
                    "  WHERE table_class.relname = 'production_line_transformation_member' "
                    "    AND con.contype = 'u'"
                    ") columns "
                    "GROUP BY constraint_name"
                )
            )
        }
        assert member_unique_constraints == {
            "uq_production_line_transformation_member_line": (
                "transformation_id",
                "production_line_id",
            ),
            "uq_production_line_transformation_member_role_ordinal": (
                "transformation_id",
                "member_role",
                "ordinal",
            ),
        }

    with Session(postgres_engine) as session:
        company = Company(legal_name="B6G disposable company")
        user = AppUser(username="b6g-disposable-admin")
        session.add_all((company, user))
        session.flush()
        site = Site(company_id=company.id, site_name="B6G disposable site")
        session.add(site)
        session.flush()
        line_a = ProductionLine(site_id=site.id, code="A", effective_from=date(2026, 1, 1))
        line_c = ProductionLine(site_id=site.id, code="C", effective_from=date(2026, 1, 1))
        line_ac = ProductionLine(site_id=site.id, code="AC", effective_from=date(2026, 1, 1))
        line_d = ProductionLine(site_id=site.id, code="D", effective_from=date(2026, 1, 1))
        session.add_all((line_a, line_c, line_ac, line_d))
        session.flush()
        transformation = ProductionLineTransformation(
            site_id=site.id,
            transformation_type="MERGE",
            effective_on=date(2026, 1, 2),
            reason="approved B6G disposable merge",
            created_by_user_id=user.id,
        )
        session.add(transformation)
        session.flush()
        session.add_all(
            (
                ProductionLineTransformationMember(
                    transformation_id=transformation.id,
                    production_line_id=line_a.id,
                    member_role="INPUT",
                    ordinal=1,
                ),
                ProductionLineTransformationMember(
                    transformation_id=transformation.id,
                    production_line_id=line_c.id,
                    member_role="INPUT",
                    ordinal=2,
                ),
                ProductionLineTransformationMember(
                    transformation_id=transformation.id,
                    production_line_id=line_ac.id,
                    member_role="OUTPUT",
                    ordinal=1,
                ),
            )
        )
        session.flush()

        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(
                    ProductionLineTransformationMember(
                        transformation_id=transformation.id,
                        production_line_id=line_d.id,
                        member_role="INPUT",
                        ordinal=1,
                    )
                )
                session.flush()
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(
                    ProductionLineTransformationMember(
                        transformation_id=transformation.id,
                        production_line_id=line_a.id,
                        member_role="OUTPUT",
                        ordinal=2,
                    )
                )
                session.flush()
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(
                    ProductionLine(
                        site_id=site.id,
                        code="INVALID",
                        effective_from=date(2026, 1, 2),
                        effective_to=date(2026, 1, 2),
                    )
                )
                session.flush()
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(
                    ProductionLineTransformationMember(
                        transformation_id=transformation.id,
                        production_line_id=line_d.id,
                        member_role="UNKNOWN",
                        ordinal=3,
                    )
                )
                session.flush()

        case = Case(site_id=site.id, production_line_id=line_a.id, gxp_type="GMP", state=CaseState.DRAFT)
        session.add(case)
        session.flush()
        phase = CaseScopePhase(case_id=case.id, phase="REQUESTED")
        session.add(phase)
        session.flush()
        established = CaseScopeRevision(
            case_scope_phase_id=phase.id,
            revision_no=1,
            state="ESTABLISHED",
            is_current_established=True,
            established_at=datetime.now(timezone.utc),
        )
        session.add(established)
        session.flush()
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(
                    CaseScopeRevision(
                        case_scope_phase_id=phase.id,
                        revision_no=2,
                        state="DRAFT",
                        is_current_established=True,
                    )
                )
                session.flush()
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(
                    CaseScopeRevision(
                        case_scope_phase_id=phase.id,
                        revision_no=2,
                        state="DRAFT",
                        supersedes_revision_id=established.id,
                    )
                )
                session.flush()
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(
                    CaseScopeRevision(
                        case_scope_phase_id=phase.id,
                        revision_no=2,
                        state="ESTABLISHED",
                    )
                )
                session.flush()

        certificate = Certificate(site_id=site.id, production_line_id=line_a.id, certificate_type="GMP")
        session.add(certificate)
        session.flush()
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(
                    CertificateRelationship(
                        source_certificate_id=certificate.id,
                        target_certificate_id=certificate.id,
                        relation_type="SUPERSEDED_BY",
                        effective_on=date(2026, 1, 2),
                    )
                )
                session.flush()
        session.commit()

    _alembic("downgrade", "20260915_0016")
    with postgres_engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260915_0016"
        for table_name in (
            "production_line",
            "production_line_transformation",
            "production_line_transformation_member",
            "case_scope_phase",
            "case_scope_revision",
            "case_scope_revision_block",
            "case_scope_revision_selection",
            "case_scope_revision_unkeyed_entry",
            "certificate_relationship",
        ):
            assert connection.execute(text("SELECT to_regclass(:table_name)"), {"table_name": table_name}).scalar_one() is None
    _alembic("upgrade", "20260929_0017")
    with postgres_engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260929_0017"
        assert connection.execute(text("SELECT to_regclass('production_line')")).scalar_one() == "production_line"
