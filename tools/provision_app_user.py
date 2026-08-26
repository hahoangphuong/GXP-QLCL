from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import argparse
import json
import sys

from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.models.phase1 import AppUserRole, RbacPermission, RbacRole, RbacRolePermission
from backend.app.db.session import build_session_factory
from backend.app.rbac import (
    AppUserProvisioningError,
    RbacBaselineError,
    provision_app_user,
    verify_builtin_rbac_baseline,
)
from backend.app.runtime_schema import expected_alembic_head_revision
from tools import import_legacy_production as production_import


DEFAULT_RUNTIME_ENV_PATH = Path("/etc/gxp/runtime.env")


@dataclass(frozen=True)
class ProvisionReport:
    runtime_env_path: str
    target_database: str
    username: str
    external_email: str
    external_subject: str | None
    role_code: str
    user_created: bool
    user_updated: bool
    role_assignment_created: bool
    rbac_role_count: int
    rbac_permission_count: int
    rbac_role_permission_count: int


class ProvisionCliError(RuntimeError):
    """Raised when explicit app-user provisioning must fail closed."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision an explicit application RBAC user.")
    parser.add_argument("--runtime-env", type=Path, default=DEFAULT_RUNTIME_ENV_PATH)
    parser.add_argument("--target-db", required=True, help="Explicit target database name.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--subject", default="")
    parser.add_argument("--display-name", default="")
    parser.add_argument(
        "--allow-canonical-target-db",
        action="store_true",
        help="Explicitly allow provisioning against the canonical production database.",
    )
    return parser


def _count_rows(session: Session, model: type[RbacRole] | type[RbacPermission] | type[RbacRolePermission]) -> int:
    return len(session.query(model).all())


def execute_provision(
    *,
    runtime_env_path: Path,
    target_database_name: str,
    email: str,
    username: str,
    role_code: str,
    subject: str | None = None,
    display_name: str | None = None,
    allow_canonical_target_db: bool = False,
) -> ProvisionReport:
    contract, _env = production_import._load_runtime_database_contract(runtime_env_path)
    normalized_target_database_name = target_database_name.strip()
    if not normalized_target_database_name:
        raise ProvisionCliError("target database name must not be blank.")
    if normalized_target_database_name == contract.db_name and not allow_canonical_target_db:
        raise ProvisionCliError(
            f"Refusing to provision against canonical database {contract.db_name!r} without --allow-canonical-target-db."
        )

    target_database_url = production_import._target_database_url(contract.database_url, normalized_target_database_name)
    factory = build_session_factory(target_database_url)
    bind = factory.kw.get("bind")
    session = factory()
    try:
        current_revision = production_import._current_alembic_revision(session)
        head_revision = expected_alembic_head_revision()
        if current_revision != head_revision:
            raise ProvisionCliError(
                f"Alembic revision mismatch: current={current_revision!r}, head={head_revision!r}."
            )
        try:
            verify_builtin_rbac_baseline(session)
        except RbacBaselineError as exc:
            raise ProvisionCliError(str(exc)) from exc
        summary = provision_app_user(
            session,
            username=username,
            email=email,
            role_code=role_code,
            external_subject=subject,
            display_name=display_name,
        )
        session.commit()
        return ProvisionReport(
            runtime_env_path=str(runtime_env_path),
            target_database=normalized_target_database_name,
            username=summary.username,
            external_email=summary.external_email,
            external_subject=summary.external_subject,
            role_code=summary.role_code,
            user_created=summary.user_created,
            user_updated=summary.user_updated,
            role_assignment_created=summary.role_assignment_created,
            rbac_role_count=_count_rows(session, RbacRole),
            rbac_permission_count=_count_rows(session, RbacPermission),
            rbac_role_permission_count=_count_rows(session, RbacRolePermission),
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        if bind is not None:
            bind.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        report = execute_provision(
            runtime_env_path=args.runtime_env,
            target_database_name=args.target_db,
            email=args.email,
            username=args.username,
            role_code=args.role,
            subject=args.subject or None,
            display_name=args.display_name or None,
            allow_canonical_target_db=args.allow_canonical_target_db,
        )
    except (ProvisionCliError, AppUserProvisioningError, production_import.ProductionImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
