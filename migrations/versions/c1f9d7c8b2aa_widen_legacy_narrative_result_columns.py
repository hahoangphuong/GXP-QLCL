"""widen_legacy_narrative_result_columns

Revision ID: c1f9d7c8b2aa
Revises: 7ad763833b09
Create Date: 2026-08-24 13:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1f9d7c8b2aa"
down_revision = "20260820_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("case_assessment", "assessment_result", existing_type=sa.String(length=255), type_=sa.Text(), existing_nullable=True)
    op.alter_column("inspection_outcome", "outcome_result", existing_type=sa.String(length=255), type_=sa.Text(), existing_nullable=True)
    op.alter_column("change_approval", "result_label", existing_type=sa.String(length=255), type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("change_approval", "result_label", existing_type=sa.Text(), type_=sa.String(length=255), existing_nullable=True)
    op.alter_column("inspection_outcome", "outcome_result", existing_type=sa.Text(), type_=sa.String(length=255), existing_nullable=True)
    op.alter_column("case_assessment", "assessment_result", existing_type=sa.Text(), type_=sa.String(length=255), existing_nullable=True)
