from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models.phase1 import AppUser, AppUserRole, RbacPermission, RbacRole, RbacRolePermission
from backend.app.rbac import (
    AppUserProvisioningError,
    BUILTIN_PERMISSION_CODES,
    BUILTIN_ROLE_CODES,
    RbacBaselineError,
    ensure_builtin_rbac_baseline,
    provision_app_user,
    verify_builtin_rbac_baseline,
)


def _build_session(database_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_fresh_database_receives_builtin_rbac_baseline(tmp_path: Path) -> None:
    with _build_session(tmp_path / "rbac.sqlite") as session:
        summary = ensure_builtin_rbac_baseline(session)
        session.commit()

        assert summary.roles_created == 4
        assert summary.permissions_created == 19
        assert summary.role_permissions_created == 50
        assert session.query(RbacRole).count() == 4
        assert session.query(RbacPermission).count() == 19
        assert session.query(RbacRolePermission).count() == 50
        assert {row.role_code for row in session.query(RbacRole).all()} == set(BUILTIN_ROLE_CODES)
        assert {row.permission_code for row in session.query(RbacPermission).all()} == set(BUILTIN_PERMISSION_CODES)


def test_builtin_rbac_baseline_rerun_is_idempotent(tmp_path: Path) -> None:
    with _build_session(tmp_path / "rbac.sqlite") as session:
        ensure_builtin_rbac_baseline(session)
        session.commit()
        summary = ensure_builtin_rbac_baseline(session)
        session.commit()

        assert summary.roles_created == 0
        assert summary.permissions_created == 0
        assert summary.role_permissions_created == 0
        assert summary.roles_verified == 4
        assert summary.permissions_verified == 19
        assert summary.role_permissions_verified == 50
        assert session.query(RbacRole).count() == 4
        assert session.query(RbacPermission).count() == 19
        assert session.query(RbacRolePermission).count() == 50


def test_builtin_rbac_baseline_fails_closed_on_unexpected_builtin_role_permission(tmp_path: Path) -> None:
    with _build_session(tmp_path / "rbac.sqlite") as session:
        ensure_builtin_rbac_baseline(session)
        rogue_permission = RbacPermission(permission_code="rogue.permission", description="Rogue permission")
        session.add(rogue_permission)
        session.flush()
        admin_role = session.query(RbacRole).filter_by(role_code="admin").one()
        session.add(RbacRolePermission(rbac_role_id=admin_role.id, rbac_permission_id=rogue_permission.id))
        session.commit()

        with pytest.raises(RbacBaselineError, match="unexpected permissions"):
            verify_builtin_rbac_baseline(session)


def test_provision_app_user_creates_user_and_role_assignment_without_duplicates(tmp_path: Path) -> None:
    with _build_session(tmp_path / "rbac.sqlite") as session:
        ensure_builtin_rbac_baseline(session)
        session.commit()

        first = provision_app_user(
            session,
            username="hahoangphuong",
            email="hahoangphuong@gmail.com",
            role_code="admin",
            external_subject="google-subject-001",
        )
        session.commit()

        second = provision_app_user(
            session,
            username="hahoangphuong",
            email="hahoangphuong@gmail.com",
            role_code="admin",
        )
        session.commit()

        assert first.user_created is True
        assert first.role_assignment_created is True
        assert second.user_created is False
        assert second.user_updated is False
        assert second.role_assignment_created is False
        assert second.external_subject == "google-subject-001"
        assert session.query(AppUser).count() == 1
        assert session.query(AppUserRole).count() == 1


def test_provision_app_user_rejects_unknown_role(tmp_path: Path) -> None:
    with _build_session(tmp_path / "rbac.sqlite") as session:
        ensure_builtin_rbac_baseline(session)
        session.commit()

        with pytest.raises(AppUserProvisioningError, match="RBAC role does not exist"):
            provision_app_user(
                session,
                username="hahoangphuong",
                email="hahoangphuong@gmail.com",
                role_code="owner",
            )
