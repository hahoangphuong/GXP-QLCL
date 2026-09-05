from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.models.phase1 import AppUser, AppUserRole, RbacRole
from backend.app.db.session import build_session_factory
from backend.app.rbac import (
    AppUserProvisioningError,
    RbacBaselineError,
    _normalize_email,
    _normalize_role_code,
    verify_builtin_rbac_baseline,
)


class RbacReadinessError(RuntimeError):
    """Raised when a read-only RBAC readiness condition is not satisfied."""


class RbacReadinessArgumentParser(argparse.ArgumentParser):
    """Convert CLI parse failures into the verifier's deterministic failure output."""

    def error(self, message: str) -> None:
        raise RbacReadinessError(message)


@dataclass(frozen=True)
class RequiredUser:
    email: str
    role_code: str


def parse_required_user(value: str) -> RequiredUser:
    """Parse and normalize the explicit EMAIL:ROLE CLI contract."""
    if value.count(":") != 1:
        raise RbacReadinessError("--require-user must use EMAIL:ROLE.")
    email_value, role_value = value.split(":", 1)
    email = _normalize_email(email_value)
    if email is None:
        raise RbacReadinessError("--require-user email must not be blank.")
    try:
        role_code = _normalize_role_code(role_value)
    except AppUserProvisioningError as exc:
        raise RbacReadinessError("--require-user role must not be blank.") from exc
    return RequiredUser(email=email, role_code=role_code)


def normalize_required_users(values: list[str]) -> tuple[RequiredUser, ...]:
    """Deduplicate identical normalized requirements while preserving CLI order."""
    requirements: list[RequiredUser] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        requirement = parse_required_user(value)
        key = (requirement.email, requirement.role_code)
        if key not in seen:
            requirements.append(requirement)
            seen.add(key)
    return tuple(requirements)


def _load_unique_user(session: Session, email: str) -> AppUser:
    users = session.scalars(select(AppUser).where(AppUser.external_email == email)).all()
    if len(users) != 1:
        if not users:
            raise RbacReadinessError(f"Required user is absent: {email}")
        raise RbacReadinessError(f"Required user identity is ambiguous: {email}")
    return users[0]


def _verify_required_user(session: Session, requirement: RequiredUser) -> None:
    app_user = _load_unique_user(session, requirement.email)
    if not app_user.is_active:
        raise RbacReadinessError(f"Required user is inactive: {requirement.email}")

    assignments = session.execute(
        select(AppUserRole.id)
        .join(RbacRole, RbacRole.id == AppUserRole.rbac_role_id)
        .where(
            AppUserRole.app_user_id == app_user.id,
            RbacRole.role_code == requirement.role_code,
        )
    ).all()
    if len(assignments) != 1:
        if not assignments:
            raise RbacReadinessError(
                f"Required user lacks exact role {requirement.role_code}: {requirement.email}"
            )
        raise RbacReadinessError(
            f"Required user has duplicate exact role assignments: {requirement.email}"
        )


def verify_rbac_readiness(
    *,
    database_url: str,
    required_users: tuple[RequiredUser, ...] = (),
) -> tuple[RequiredUser, ...]:
    """Verify RBAC baseline and explicit user-role requirements without mutation."""
    if not database_url.strip():
        raise RbacReadinessError("--database-url must not be blank.")

    bind = None
    session: Session | None = None
    try:
        factory = build_session_factory(database_url)
        bind = factory.kw.get("bind")
        session = factory()
        verify_builtin_rbac_baseline(session)
        for requirement in required_users:
            _verify_required_user(session, requirement)
        return required_users
    except RbacReadinessError:
        raise
    except RbacBaselineError as exc:
        raise RbacReadinessError(str(exc)) from exc
    except Exception as exc:
        raise RbacReadinessError("Database verification failed.") from exc
    finally:
        # The verifier has no write path; rollback also closes any read transaction.
        if session is not None:
            session.rollback()
            session.close()
        if bind is not None:
            bind.dispose()


def _build_parser() -> argparse.ArgumentParser:
    parser = RbacReadinessArgumentParser(description="Verify read-only application RBAC readiness.")
    parser.add_argument("--database-url", required=True, help="Explicit target database URL.")
    parser.add_argument("--require-user", action="append", default=[], metavar="EMAIL:ROLE")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        requirements = normalize_required_users(args.require_user)
        verified_users = verify_rbac_readiness(
            database_url=args.database_url,
            required_users=requirements,
        )
    except RbacReadinessError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("STATUS=RBAC_READINESS_FAIL", file=sys.stderr)
        return 1

    print("RBAC_BASELINE=PASS")
    for requirement in verified_users:
        print(f"REQUIRED_USER={requirement.email}|ROLE={requirement.role_code}|STATUS=PASS")
    print("STATUS=RBAC_READINESS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
