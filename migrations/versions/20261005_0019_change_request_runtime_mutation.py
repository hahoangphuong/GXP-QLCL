"""Add ChangeRequest aggregate concurrency and bounded-context RBAC.

Revision ID: 20261005_0019
Revises: 20261003_0018
Create Date: 2026-10-05
"""

from __future__ import annotations

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20261005_0019"
down_revision = "20261003_0018"
branch_labels = None
depends_on = None


_PERMISSION_DEFINITIONS = {
    "change_request.edit": "Create or update change requests and structured change details.",
    "change_request.approve": "Record change-request decisions and advance change-request lifecycle.",
}
_ROLE_PERMISSIONS = {
    "inspector": {"change_request.edit"},
    "manager": {"change_request.edit", "change_request.approve"},
    "admin": {"change_request.edit", "change_request.approve"},
}


def _tables(bind):
    metadata = sa.MetaData()
    return (
        sa.Table("rbac_role", metadata, autoload_with=bind),
        sa.Table("rbac_permission", metadata, autoload_with=bind),
        sa.Table("rbac_role_permission", metadata, autoload_with=bind),
    )


def _upgrade_existing_rbac(bind) -> None:
    role, permission, role_permission = _tables(bind)
    role_rows = {
        row.role_code: row.id
        for row in bind.execute(
            sa.select(role.c.id, role.c.role_code).where(role.c.role_code.in_(tuple(_ROLE_PERMISSIONS)))
        )
    }
    permission_ids: dict[str, str] = {}
    for code, description in _PERMISSION_DEFINITIONS.items():
        existing = bind.execute(
            sa.select(permission.c.id, permission.c.description).where(permission.c.permission_code == code)
        ).one_or_none()
        if existing is None:
            permission_id = str(uuid4())
            bind.execute(
                permission.insert().values(
                    id=permission_id,
                    permission_code=code,
                    description=description,
                )
            )
        else:
            permission_id = existing.id
            if (existing.description or "") != description:
                raise RuntimeError(f"Conflicting pre-existing RBAC permission description for {code}.")
        permission_ids[code] = permission_id

    for role_code, permission_codes in _ROLE_PERMISSIONS.items():
        role_id = role_rows.get(role_code)
        if role_id is None:
            continue
        for code in permission_codes:
            permission_id = permission_ids[code]
            exists = bind.execute(
                sa.select(role_permission.c.id).where(
                    role_permission.c.rbac_role_id == role_id,
                    role_permission.c.rbac_permission_id == permission_id,
                )
            ).first()
            if exists is None:
                bind.execute(
                    role_permission.insert().values(
                        id=str(uuid4()),
                        rbac_role_id=role_id,
                        rbac_permission_id=permission_id,
                    )
                )


def upgrade() -> None:
    op.add_column(
        "change_request",
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
    )
    _upgrade_existing_rbac(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    role, permission, role_permission = _tables(bind)
    permission_rows = list(
        bind.execute(
            sa.select(permission.c.id).where(
                permission.c.permission_code.in_(tuple(_PERMISSION_DEFINITIONS))
            )
        )
    )
    permission_ids = [row.id for row in permission_rows]
    if permission_ids:
        bind.execute(
            role_permission.delete().where(
                role_permission.c.rbac_permission_id.in_(permission_ids)
            )
        )
        bind.execute(
            permission.delete().where(permission.c.id.in_(permission_ids))
        )
    op.drop_column("change_request", "row_version")
