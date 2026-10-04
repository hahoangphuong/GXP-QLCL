"""Add the canonical CAPA incoming correspondence reference.

Revision ID: 20261003_0018
Revises: 20260929_0017
Create Date: 2026-10-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20261003_0018"
down_revision = "20260929_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("capa_cycle", sa.Column("incoming_reference", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("capa_cycle", "incoming_reference")
