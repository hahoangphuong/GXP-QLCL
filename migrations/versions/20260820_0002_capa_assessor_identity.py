"""capa_assessor_identity

Revision ID: 20260820_0002
Revises: 7ad763833b09
Create Date: 2026-08-20 21:20:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260820_0002"
down_revision = "7ad763833b09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("capa_cycle") as batch_op:
        batch_op.add_column(sa.Column("assessor_user_id", sa.UUID(as_uuid=False), nullable=True))
        batch_op.create_index(op.f("ix_capa_cycle_assessor_user_id"), ["assessor_user_id"], unique=False)
        batch_op.create_foreign_key(
            op.f("fk_capa_cycle_assessor_user_id_app_user"),
            "app_user",
            ["assessor_user_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("capa_cycle") as batch_op:
        batch_op.drop_constraint(op.f("fk_capa_cycle_assessor_user_id_app_user"), type_="foreignkey")
        batch_op.drop_index(op.f("ix_capa_cycle_assessor_user_id"))
        batch_op.drop_column("assessor_user_id")
