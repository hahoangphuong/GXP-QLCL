"""Restore ORM timestamp defaults for approval submissions.

Revision ID: 20261108_0028
Revises: 20261101_0027
"""
from alembic import op
import sqlalchemy as sa

revision = "20261108_0028"
down_revision = "20261101_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("created_at", "updated_at"):
        op.alter_column("inspection_approval_submission", column,
                        existing_type=sa.DateTime(timezone=True), existing_nullable=False,
                        server_default=sa.text("CURRENT_TIMESTAMP"))


def downgrade() -> None:
    for column in ("created_at", "updated_at"):
        op.alter_column("inspection_approval_submission", column,
                        existing_type=sa.DateTime(timezone=True), existing_nullable=False,
                        server_default=None)
