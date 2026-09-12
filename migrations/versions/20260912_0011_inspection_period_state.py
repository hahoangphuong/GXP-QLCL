"""persist source state for inspection timing

Revision ID: 20260912_0011
Revises: 20260912_0010
"""
from alembic import op
import sqlalchemy as sa

revision = "20260912_0011"
down_revision = "20260912_0010"
branch_labels = None
depends_on = None

_STATES = "'KNOWN', 'PENDING_INPUT', 'NOT_APPLICABLE', 'MISSING', 'NON_DATE_EXPRESSION', 'UNRESOLVED'"

def upgrade() -> None:
    # Existing outcomes predate source-bound period classification.  Do not
    # relabel them as a business sentinel until that classification is run.
    op.add_column("inspection_outcome", sa.Column("inspection_period_state", sa.String(32), nullable=True))
    op.create_check_constraint("inspection_outcome_period_state", "inspection_outcome", f"inspection_period_state IN ({_STATES})")
    op.create_check_constraint("inspection_period_segment_ordinal_positive", "inspection_period_segment", "ordinal >= 1")

def downgrade() -> None:
    op.drop_constraint("inspection_period_segment_ordinal_positive", "inspection_period_segment", type_="check")
    op.drop_constraint("inspection_outcome_period_state", "inspection_outcome", type_="check")
    op.drop_column("inspection_outcome", "inspection_period_state")
