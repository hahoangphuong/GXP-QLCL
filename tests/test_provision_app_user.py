from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.rbac import ensure_builtin_rbac_baseline
from backend.app.runtime_schema import expected_alembic_head_revision
from tools import import_legacy_production as production_import
from tools import provision_app_user as provision_tool


def _prepare_runtime_db(path: Path) -> str:
    database_url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    head = expected_alembic_head_revision()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("DELETE FROM alembic_version"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"), {"version_num": head})
    engine.dispose()
    return database_url


def _patch_runtime_contract(monkeypatch, runtime_env: Path, database_url: str) -> None:
    contract = production_import.RuntimeDatabaseContract(
        runtime_env_path=runtime_env,
        app_env="production",
        db_mode="local_postgres",
        db_name="gxp_qlcl",
        db_user="gxp_app",
        database_url=database_url,
        database_url_redacted=production_import._redact_database_url(database_url),
    )
    monkeypatch.setattr(provision_tool.production_import, "_load_runtime_database_contract", lambda path: (contract, {}))


def test_provision_cli_rejects_canonical_database_by_default(tmp_path: Path, monkeypatch) -> None:
    runtime_env = tmp_path / "runtime.env"
    database_url = _prepare_runtime_db(tmp_path / "prod.db")
    _patch_runtime_contract(monkeypatch, runtime_env, database_url)

    with pytest.raises(provision_tool.ProvisionCliError, match="Refusing to provision against canonical database"):
        provision_tool.execute_provision(
            runtime_env_path=runtime_env,
            target_database_name="gxp_qlcl",
            email="hahoangphuong@gmail.com",
            username="hahoangphuong",
            role_code="admin",
        )


def test_provision_cli_requires_existing_rbac_baseline(tmp_path: Path, monkeypatch) -> None:
    runtime_env = tmp_path / "runtime.env"
    source_url = _prepare_runtime_db(tmp_path / "prod.db")
    target_url = production_import._target_database_url(source_url, "gxp_legacy_rehearsal")
    _patch_runtime_contract(monkeypatch, runtime_env, source_url)
    _prepare_runtime_db(Path(target_url.removeprefix("sqlite:///")))

    with pytest.raises(provision_tool.ProvisionCliError, match="Missing required RBAC permission"):
        provision_tool.execute_provision(
            runtime_env_path=runtime_env,
            target_database_name="gxp_legacy_rehearsal",
            email="hahoangphuong@gmail.com",
            username="hahoangphuong",
            role_code="admin",
        )


def test_provision_cli_assigns_existing_admin_role_idempotently(tmp_path: Path, monkeypatch) -> None:
    runtime_env = tmp_path / "runtime.env"
    source_url = _prepare_runtime_db(tmp_path / "prod.db")
    target_url = production_import._target_database_url(source_url, "gxp_legacy_rehearsal")
    _patch_runtime_contract(monkeypatch, runtime_env, source_url)
    _prepare_runtime_db(Path(target_url.removeprefix("sqlite:///")))
    engine = create_engine(target_url, future=True)
    with Session(engine) as session:
        ensure_builtin_rbac_baseline(session)
        session.commit()
    engine.dispose()

    first = provision_tool.execute_provision(
        runtime_env_path=runtime_env,
        target_database_name="gxp_legacy_rehearsal",
        email="hahoangphuong@gmail.com",
        username="hahoangphuong",
        role_code="admin",
        subject="google-subject-001",
    )
    second = provision_tool.execute_provision(
        runtime_env_path=runtime_env,
        target_database_name="gxp_legacy_rehearsal",
        email="hahoangphuong@gmail.com",
        username="hahoangphuong",
        role_code="admin",
    )

    assert first.user_created is True
    assert first.role_assignment_created is True
    assert first.rbac_role_count == 4
    assert first.rbac_permission_count == 19
    assert first.rbac_role_permission_count == 50
    assert second.user_created is False
    assert second.role_assignment_created is False
    assert second.external_subject == "google-subject-001"
