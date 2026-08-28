"""general info workspace fields from legacy site snapshot

Revision ID: 20260828_0005
Revises: 20260827_0004
Create Date: 2026-08-28 10:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260828_0005"
down_revision = "20260827_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("company", sa.Column("assigned_specialist_text", sa.Text(), nullable=True))
    op.add_column("site", sa.Column("foreign_investment_text", sa.Text(), nullable=True))
    op.add_column("site", sa.Column("contact_information", sa.Text(), nullable=True))
    op.add_column("site", sa.Column("professional_responsible_person_name", sa.Text(), nullable=True))
    op.add_column("site", sa.Column("quality_assurance_person_name", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("site", "quality_assurance_person_name")
    op.drop_column("site", "professional_responsible_person_name")
    op.drop_column("site", "contact_information")
    op.drop_column("site", "foreign_investment_text")
    op.drop_column("company", "assigned_specialist_text")
