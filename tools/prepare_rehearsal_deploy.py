from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import argparse
import json
import os
import sys
import tempfile

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.session import build_session_factory
from backend.app.runtime_schema import expected_alembic_head_revision
from tools import import_legacy_production as production_import
from tools.env_utils import parse_env_file


DEFAULT_RUNTIME_ENV_PATH = Path("/etc/gxp/runtime.env")
DEFAULT_REHEARSAL_TARGET_DB = production_import.DEFAULT_REHEARSAL_TARGET_DB


class RehearsalDeployError(RuntimeError):
    """Raised when rehearsal deployment preflight must fail closed."""


@dataclass(frozen=True)
class RehearsalDeployPlan:
    canonical_runtime_env_path: str
    output_runtime_env_path: str
    canonical_database: str
    rehearsal_database: str
    canonical_database_url_redacted: str
    rehearsal_database_url_redacted: str
    alembic_current_revision: str | None
    alembic_head_revision: str


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    lines: list[str] = []
    for key, value in values.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            raise RehearsalDeployError("Runtime env keys must not be blank.")
        lines.append(f"{normalized_key}={'' if value is None else value}")
    payload = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise


def _normalize_target_database_name(target_database_name: str) -> str:
    normalized = target_database_name.strip()
    if not normalized:
        raise RehearsalDeployError("Rehearsal target database name must not be blank.")
    if normalized != DEFAULT_REHEARSAL_TARGET_DB:
        raise RehearsalDeployError(
            f"Rehearsal deploy requires target database {DEFAULT_REHEARSAL_TARGET_DB!r}, got {normalized!r}."
        )
    return normalized


def verify_rehearsal_target_database(*, runtime_env_path: Path, target_database_name: str = DEFAULT_REHEARSAL_TARGET_DB) -> RehearsalDeployPlan:
    normalized_target_database_name = _normalize_target_database_name(target_database_name)
    contract, _env = production_import._load_runtime_database_contract(runtime_env_path)
    if contract.db_name == normalized_target_database_name:
        raise RehearsalDeployError(
            f"Rehearsal target database {normalized_target_database_name!r} must differ from canonical database {contract.db_name!r}."
        )
    target_database_url = production_import._target_database_url(contract.database_url, normalized_target_database_name)
    factory = build_session_factory(target_database_url)
    bind = factory.kw.get("bind")
    session = factory()
    try:
        try:
            session.execute(text("SELECT 1"))
            current_revision = production_import._current_alembic_revision(session)
        except production_import.ProductionImportError as exc:
            raise RehearsalDeployError(str(exc)) from exc
        except SQLAlchemyError as exc:
            raise RehearsalDeployError(
                f"Rehearsal target database {normalized_target_database_name!r} is missing or unreachable."
            ) from exc
    finally:
        session.close()
        if bind is not None:
            bind.dispose()

    head_revision = expected_alembic_head_revision()
    if not head_revision:
        raise RehearsalDeployError("Could not determine the expected Alembic head revision for rehearsal deploy.")
    if current_revision != head_revision:
        raise RehearsalDeployError(
            f"Rehearsal target database {normalized_target_database_name!r} alembic revision mismatch: "
            f"current={current_revision!r}, head={head_revision!r}."
        )
    return RehearsalDeployPlan(
        canonical_runtime_env_path=str(runtime_env_path),
        output_runtime_env_path="",
        canonical_database=contract.db_name,
        rehearsal_database=normalized_target_database_name,
        canonical_database_url_redacted=contract.database_url_redacted,
        rehearsal_database_url_redacted=production_import._redact_database_url(target_database_url),
        alembic_current_revision=current_revision,
        alembic_head_revision=head_revision,
    )


def prepare_rehearsal_runtime_env(
    *,
    runtime_env_path: Path,
    output_runtime_env_path: Path,
    target_database_name: str = DEFAULT_REHEARSAL_TARGET_DB,
) -> RehearsalDeployPlan:
    normalized_target_database_name = _normalize_target_database_name(target_database_name)
    contract, env = production_import._load_runtime_database_contract(runtime_env_path)
    if contract.db_name == normalized_target_database_name:
        raise RehearsalDeployError(
            f"Rehearsal target database {normalized_target_database_name!r} must differ from canonical database {contract.db_name!r}."
        )
    plan = verify_rehearsal_target_database(
        runtime_env_path=runtime_env_path,
        target_database_name=normalized_target_database_name,
    )
    derived_env = dict(parse_env_file(runtime_env_path))
    derived_env["DB_NAME"] = normalized_target_database_name
    derived_env["DATABASE_URL"] = production_import._target_database_url(contract.database_url, normalized_target_database_name)
    _write_env_file(output_runtime_env_path, derived_env)
    return RehearsalDeployPlan(
        canonical_runtime_env_path=plan.canonical_runtime_env_path,
        output_runtime_env_path=str(output_runtime_env_path),
        canonical_database=plan.canonical_database,
        rehearsal_database=plan.rehearsal_database,
        canonical_database_url_redacted=plan.canonical_database_url_redacted,
        rehearsal_database_url_redacted=plan.rehearsal_database_url_redacted,
        alembic_current_revision=plan.alembic_current_revision,
        alembic_head_revision=plan.alembic_head_revision,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare and validate the rehearsal VM deploy runtime contract.")
    parser.add_argument("--runtime-env", type=Path, default=DEFAULT_RUNTIME_ENV_PATH)
    parser.add_argument("--output-runtime-env", type=Path, required=True)
    parser.add_argument("--target-db", default=DEFAULT_REHEARSAL_TARGET_DB)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        plan = prepare_rehearsal_runtime_env(
            runtime_env_path=args.runtime_env,
            output_runtime_env_path=args.output_runtime_env,
            target_database_name=args.target_db,
        )
    except (RehearsalDeployError, production_import.ProductionImportError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(asdict(plan), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
