"""preserve repeatable legacy inspection decisions and minutes occurrences

Revision ID: 20260913_0013
Revises: 20260912_0012
"""
from alembic import op
import sqlalchemy as sa


revision = "20260913_0013"
down_revision = "20260912_0012"
branch_labels = None
depends_on = None


def _uuid() -> sa.UUID:
    return sa.UUID(as_uuid=False)


def upgrade() -> None:
    op.create_table("inspection_decision", sa.Column("id", _uuid(), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("inspection_plan_id", _uuid(), nullable=False), sa.Column("ordinal", sa.Integer(), nullable=False), sa.Column("reference", sa.String(255), nullable=False), sa.Column("decision_on", sa.Date(), nullable=False), sa.Column("legacy_raw", sa.Text(), nullable=False), sa.Column("relation_type", sa.String(16)), sa.Column("related_decision_id", _uuid()), sa.ForeignKeyConstraint(["inspection_plan_id"], ["inspection_plan.id"]), sa.ForeignKeyConstraint(["related_decision_id"], ["inspection_decision.id"]), sa.UniqueConstraint("inspection_plan_id", "ordinal"), sa.CheckConstraint("ordinal >= 1", name="inspection_decision_ordinal_positive"), sa.CheckConstraint("relation_type IS NULL OR relation_type IN ('REPLACES')", name="inspection_decision_relation_known"), sa.CheckConstraint("(relation_type IS NULL) = (related_decision_id IS NULL)", name="inspection_decision_relation_shape"))
    op.create_index("ix_inspection_decision_related_decision_id", "inspection_decision", ["related_decision_id"])
    op.create_table("inspection_minutes_record", sa.Column("id", _uuid(), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("inspection_outcome_id", _uuid(), nullable=False), sa.Column("ordinal", sa.Integer(), nullable=False), sa.Column("recorded_on", sa.Date(), nullable=False), sa.Column("recorded_time", sa.Time()), sa.Column("precision", sa.String(32), nullable=False), sa.Column("source_format", sa.String(32), nullable=False), sa.Column("legacy_raw", sa.Text(), nullable=False), sa.ForeignKeyConstraint(["inspection_outcome_id"], ["inspection_outcome.id"]), sa.UniqueConstraint("inspection_outcome_id", "ordinal"), sa.CheckConstraint("ordinal >= 1", name="inspection_minutes_record_ordinal_positive"), sa.CheckConstraint("recorded_time IS NULL OR recorded_on IS NOT NULL", name="inspection_minutes_record_time_requires_date"))


def downgrade() -> None:
    op.drop_index("ix_inspection_decision_related_decision_id", table_name="inspection_decision")
    op.drop_table("inspection_minutes_record")
    op.drop_table("inspection_decision")
