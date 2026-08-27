"""certificate line ownership and certificate version metadata

Revision ID: 20260827_0004
Revises: 20260825_0003
Create Date: 2026-08-27 15:45:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260827_0004"
down_revision = "20260825_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("certificate", sa.Column("line_code", sa.String(length=32), nullable=True))
    op.add_column("certificate_version", sa.Column("applicable_standard", sa.String(length=255), nullable=True))
    op.add_column("certificate_version", sa.Column("issuing_authority", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("certificate_version", "issuing_authority")
    op.drop_column("certificate_version", "applicable_standard")
    op.drop_column("certificate", "line_code")
