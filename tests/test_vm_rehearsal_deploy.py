from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from backend.app.db.base import Base
from backend.app.runtime_schema import expected_alembic_head_revision
from tools import import_legacy_production as production_import
from tools import prepare_rehearsal_deploy as rehearsal_deploy
from tools.env_utils import parse_env_file
def _prepare_target_db(path: Path, *, revision: str | None = None) -> str:
    database_url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    current_revision = expected_alembic_head_revision() if revision is None else revision
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("DELETE FROM alembic_version"))
        if current_revision is not None:
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
                {"version_num": current_revision},
            )
    engine.dispose()
    return database_url


def _patch_runtime_contract(monkeypatch: pytest.MonkeyPatch, runtime_env: Path, database_url: str) -> None:
    contract = production_import.RuntimeDatabaseContract(
        runtime_env_path=runtime_env,
        app_env="production",
        db_mode="local_postgres",
        db_name="gxp_qlcl",
        db_user="gxp_app",
        database_url=database_url,
        database_url_redacted=production_import._redact_database_url(database_url),
    )
    monkeypatch.setattr(rehearsal_deploy.production_import, "_load_runtime_database_contract", lambda path: (contract, {}))
def test_prepare_rehearsal_runtime_env_rejects_canonical_target_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text("DB_NAME=gxp_qlcl\n", encoding="utf-8", newline="\n")
    _patch_runtime_contract(monkeypatch, runtime_env, _prepare_target_db(tmp_path / "prod.db"))

    with pytest.raises(rehearsal_deploy.RehearsalDeployError, match="requires target database 'gxp_legacy_rehearsal'"):
        rehearsal_deploy.prepare_rehearsal_runtime_env(
            runtime_env_path=runtime_env,
            output_runtime_env_path=tmp_path / "runtime.rehearsal.env",
            target_database_name="gxp_qlcl",
        )


def test_prepare_rehearsal_runtime_env_preserves_canonical_env_and_points_runtime_to_rehearsal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical_env = tmp_path / "runtime.env"
    canonical_env.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "DB_MODE=local_postgres",
                "DB_NAME=gxp_qlcl",
                "DB_USER=gxp_app",
                "DB_PASSWORD=secret",
                "DB_HOST=127.0.0.1",
                "DB_PORT=5432",
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    canonical_before = canonical_env.read_text(encoding="utf-8")
    canonical_url = _prepare_target_db(tmp_path / "prod.db")
    target_url = production_import._target_database_url(canonical_url, rehearsal_deploy.DEFAULT_REHEARSAL_TARGET_DB)
    _prepare_target_db(Path(target_url.removeprefix("sqlite:///")))
    _patch_runtime_contract(monkeypatch, canonical_env, canonical_url)

    output_env = tmp_path / "runtime.rehearsal.env"
    plan = rehearsal_deploy.prepare_rehearsal_runtime_env(
        runtime_env_path=canonical_env,
        output_runtime_env_path=output_env,
    )

    assert canonical_env.read_text(encoding="utf-8") == canonical_before
    assert plan.canonical_database == "gxp_qlcl"
    assert plan.rehearsal_database == "gxp_legacy_rehearsal"
    assert plan.alembic_current_revision == expected_alembic_head_revision()
    assert plan.alembic_head_revision == expected_alembic_head_revision()
    written = parse_env_file(output_env)
    assert written["DB_NAME"] == "gxp_legacy_rehearsal"
    assert written["DATABASE_URL"] == target_url


def test_prepare_rehearsal_runtime_env_requires_expected_alembic_head(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    canonical_env = tmp_path / "runtime.env"
    canonical_env.write_text("DB_NAME=gxp_qlcl\n", encoding="utf-8", newline="\n")
    canonical_url = _prepare_target_db(tmp_path / "prod.db")
    target_url = production_import._target_database_url(canonical_url, rehearsal_deploy.DEFAULT_REHEARSAL_TARGET_DB)
    _prepare_target_db(Path(target_url.removeprefix("sqlite:///")), revision="wrong-head")
    _patch_runtime_contract(monkeypatch, canonical_env, canonical_url)

    with pytest.raises(rehearsal_deploy.RehearsalDeployError, match="alembic revision mismatch"):
        rehearsal_deploy.prepare_rehearsal_runtime_env(
            runtime_env_path=canonical_env,
            output_runtime_env_path=tmp_path / "runtime.rehearsal.env",
        )


def test_rehearsal_deploy_script_runs_preflight_before_handing_off_to_production_switch() -> None:
    script_text = (Path(__file__).resolve().parents[1] / "infra" / "vm" / "deploy_rehearsal.sh").read_text(encoding="utf-8")

    assert 'python3 "${REPO_ROOT}/tools/prepare_rehearsal_deploy.py" \\' in script_text
    assert 'VM_RUNTIME_ENV_FILE="${REHEARSAL_RUNTIME_ENV_FILE}" "${SCRIPT_DIR}/deploy_prod.sh"' in script_text
    assert script_text.index('python3 "${REPO_ROOT}/tools/prepare_rehearsal_deploy.py" \\') < script_text.index(
        'VM_RUNTIME_ENV_FILE="${REHEARSAL_RUNTIME_ENV_FILE}" "${SCRIPT_DIR}/deploy_prod.sh"'
    )
