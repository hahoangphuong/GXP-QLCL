"""PostgreSQL round-trip coverage for A5 migration 20261005_0019."""
from __future__ import annotations

import os
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.app.runtime_schema import expected_alembic_head_revision


if os.environ.get("A3_POSTGRES_MIGRATION_INTEGRATION") != "1":
    pytest.skip(
        "runs only in the disposable PostgreSQL migration gate",
        allow_module_level=True,
    )

DATABASE_URL = os.environ.get("DATABASE_URL", "")
EXPECTED_DATABASE = os.environ.get("A3_DISPOSABLE_POSTGRES_DATABASE", "")
if not DATABASE_URL.startswith("postgresql"):
    raise RuntimeError("A5 migration gate requires PostgreSQL")
if not EXPECTED_DATABASE or make_url(DATABASE_URL).database != EXPECTED_DATABASE:
    raise RuntimeError("A5 migration gate requires its explicitly named disposable database")


def _alembic(*arguments: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        check=True,
        env={**os.environ, "DATABASE_URL": DATABASE_URL},
    )


def _revision(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _row_version_column(engine):
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = 'change_request' "
                "AND column_name = 'row_version'"
            )
        ).one_or_none()


def test_a5_change_request_migration_round_trip_preserves_existing_rbac_data() -> None:
    engine = create_engine(DATABASE_URL, future=True)
    head = expected_alembic_head_revision()
    assert head == "20261005_0019"
    preexisting_edit_permission_id = str(uuid4())
    role_ids = {
        name: str(uuid4())
        for name in ("inspector", "manager", "admin", "custom_reviewer")
    }
    try:
        assert _revision(engine) == head
        assert _row_version_column(engine) is not None

        _alembic("downgrade", "20261003_0018")
        assert _revision(engine) == "20261003_0018"
        assert _row_version_column(engine) is None

        # Build a controlled pre-0019 RBAC baseline. The initial head migration
        # may already have seeded A5 permissions, and the corrected downgrade is
        # deliberately non-destructive, so remove only those disposable-gate
        # rows before seeding provenance that predates 0019.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM rbac_role_permission WHERE rbac_permission_id IN "
                    "(SELECT id FROM rbac_permission WHERE permission_code IN "
                    "('change_request.edit', 'change_request.approve'))"
                )
            )
            connection.execute(
                text(
                    "DELETE FROM rbac_permission WHERE permission_code IN "
                    "('change_request.edit', 'change_request.approve')"
                )
            )
            connection.execute(
                text(
                    "DELETE FROM rbac_role_permission WHERE rbac_role_id IN "
                    "(SELECT id FROM rbac_role WHERE role_code IN "
                    "('inspector','manager','admin','custom_reviewer'))"
                )
            )
            connection.execute(
                text(
                    "DELETE FROM rbac_role WHERE role_code IN "
                    "('inspector','manager','admin','custom_reviewer')"
                )
            )
            for role_code, role_id in role_ids.items():
                connection.execute(
                    text(
                        "INSERT INTO rbac_role (id, role_code, description) "
                        "VALUES (:id, :role_code, :description)"
                    ),
                    {"id": role_id, "role_code": role_code, "description": f"A5 test {role_code}"},
                )
            connection.execute(
                text(
                    "INSERT INTO rbac_permission (id, permission_code, description) "
                    "VALUES (:id, 'change_request.edit', :description)"
                ),
                {
                    "id": preexisting_edit_permission_id,
                    "description": "Create or update change requests and structured change details.",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO rbac_role_permission "
                    "(id, rbac_role_id, rbac_permission_id) "
                    "VALUES (:id, :role_id, :permission_id)"
                ),
                {
                    "id": str(uuid4()),
                    "role_id": role_ids["custom_reviewer"],
                    "permission_id": preexisting_edit_permission_id,
                },
            )

        _alembic("upgrade", "head")
        assert _revision(engine) == head
        assert _row_version_column(engine) is not None

        with engine.connect() as connection:
            permissions = {
                row.permission_code: row.id
                for row in connection.execute(
                    text(
                        "SELECT id, permission_code FROM rbac_permission "
                        "WHERE permission_code IN ('change_request.edit', 'change_request.approve')"
                    )
                )
            }
            assert set(permissions) == {"change_request.edit", "change_request.approve"}
            assert str(permissions["change_request.edit"]) == preexisting_edit_permission_id
            mappings = set(
                connection.execute(
                    text(
                        "SELECT r.role_code, p.permission_code "
                        "FROM rbac_role_permission rp "
                        "JOIN rbac_role r ON r.id = rp.rbac_role_id "
                        "JOIN rbac_permission p ON p.id = rp.rbac_permission_id "
                        "WHERE p.permission_code IN ('change_request.edit', 'change_request.approve')"
                    )
                )
            )
            assert mappings == {
                ("custom_reviewer", "change_request.edit"),
                ("inspector", "change_request.edit"),
                ("manager", "change_request.edit"),
                ("manager", "change_request.approve"),
                ("admin", "change_request.edit"),
                ("admin", "change_request.approve"),
            }

        # Downgrade must remove only schema owned by 0019. It cannot delete RBAC
        # rows by code because upgrade deliberately reuses pre-existing rows.
        _alembic("downgrade", "20261003_0018")
        assert _revision(engine) == "20261003_0018"
        assert _row_version_column(engine) is None
        with engine.connect() as connection:
            assert str(
                connection.execute(
                    text(
                        "SELECT id FROM rbac_permission "
                        "WHERE permission_code = 'change_request.edit'"
                    )
                ).scalar_one()
            ) == preexisting_edit_permission_id
            assert connection.execute(
                text(
                    "SELECT count(*) "
                    "FROM rbac_role_permission rp "
                    "JOIN rbac_role r ON r.id = rp.rbac_role_id "
                    "JOIN rbac_permission p ON p.id = rp.rbac_permission_id "
                    "WHERE r.role_code = 'custom_reviewer' "
                    "AND p.permission_code = 'change_request.edit'"
                )
            ).scalar_one() == 1

        # Re-upgrade must be idempotent over the preserved data.
        _alembic("upgrade", "head")
        assert _revision(engine) == head
        assert _row_version_column(engine) is not None
        with engine.connect() as connection:
            assert str(
                connection.execute(
                    text(
                        "SELECT id FROM rbac_permission "
                        "WHERE permission_code = 'change_request.edit'"
                    )
                ).scalar_one()
            ) == preexisting_edit_permission_id
            mappings = set(
                connection.execute(
                    text(
                        "SELECT r.role_code, p.permission_code "
                        "FROM rbac_role_permission rp "
                        "JOIN rbac_role r ON r.id = rp.rbac_role_id "
                        "JOIN rbac_permission p ON p.id = rp.rbac_permission_id "
                        "WHERE p.permission_code IN ('change_request.edit', 'change_request.approve')"
                    )
                )
            )
            assert mappings == {
                ("custom_reviewer", "change_request.edit"),
                ("inspector", "change_request.edit"),
                ("manager", "change_request.edit"),
                ("manager", "change_request.approve"),
                ("admin", "change_request.edit"),
                ("admin", "change_request.approve"),
            }

        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM rbac_role_permission WHERE rbac_role_id IN "
                    "(SELECT id FROM rbac_role WHERE role_code IN "
                    "('inspector','manager','admin','custom_reviewer'))"
                )
            )
            connection.execute(
                text(
                    "DELETE FROM rbac_role WHERE role_code IN "
                    "('inspector','manager','admin','custom_reviewer')"
                )
            )
    finally:
        engine.dispose()
