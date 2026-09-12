"""add db.ktra semantic foundation

Revision ID: 20260912_0012
Revises: 20260912_0011
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260912_0012"
down_revision = "20260912_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inspection_outcome", sa.Column("final_evaluation", sa.Text(), nullable=True))
    op.add_column("inspection_outcome", sa.Column("minutes_recorded_on", sa.Date(), nullable=True))
    op.add_column("inspection_outcome", sa.Column("minutes_recorded_time", sa.Time(), nullable=True))
    op.add_column("inspection_outcome", sa.Column("minutes_legacy_raw", sa.Text(), nullable=True))
    op.add_column("inspection_outcome", sa.Column("compliance_due_on", sa.Date(), nullable=True))
    op.create_check_constraint(
        "inspection_outcome_minutes_time_requires_date",
        "inspection_outcome",
        "minutes_recorded_time IS NULL OR minutes_recorded_on IS NOT NULL",
    )

    op.add_column("inspection_plan", sa.Column("decision_reference", sa.String(length=255), nullable=True))
    op.add_column("inspection_plan", sa.Column("decision_date", sa.Date(), nullable=True))
    op.add_column("inspection_plan", sa.Column("decision_legacy_raw", sa.Text(), nullable=True))

    # Expand only: existing rows may have ordinal zero or free-text roles.
    # The preflight determines whether a later revision can tighten this schema.
    op.add_column("inspection_team_member", sa.Column("role_code", sa.String(length=16), nullable=True))
    op.create_check_constraint(
        "team_member_role_code_known",
        "inspection_team_member",
        "role_code IS NULL OR role_code IN ('LEADER', 'SECRETARY', 'MEMBER')",
    )

    op.create_table(
        "inspection_approval_submission",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("case_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("stage", sa.String(length=3), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=255), nullable=True),
        sa.Column("submitted_on", sa.Date(), nullable=True),
        sa.Column("submitted_time", sa.Time(), nullable=True),
        sa.Column("completed_on", sa.Date(), nullable=True),
        sa.Column("completed_time", sa.Time(), nullable=True),
        sa.Column("pct_submission_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("legacy_raw_source", sa.Text(), nullable=True),
        sa.CheckConstraint("round_no >= 1", name="approval_submission_round_positive"),
        sa.CheckConstraint("stage IN ('PCT', 'CT')", name="approval_submission_stage_known"),
        sa.CheckConstraint("submitted_time IS NULL OR submitted_on IS NOT NULL", name="approval_submission_submitted_time_requires_date"),
        sa.CheckConstraint("completed_time IS NULL OR completed_on IS NOT NULL", name="approval_submission_completed_time_requires_date"),
        sa.CheckConstraint(
            "(stage = 'PCT' AND pct_submission_id IS NULL) OR (stage = 'CT' AND pct_submission_id IS NOT NULL)",
            name="approval_submission_pct_parent_shape",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["case.id"]),
        sa.ForeignKeyConstraint(["pct_submission_id"], ["inspection_approval_submission.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "stage", "round_no"),
    )
    op.create_index("ix_approval_submission_case_stage_round", "inspection_approval_submission", ["case_id", "stage", "round_no"])
    op.create_index("ix_inspection_approval_submission_pct_submission_id", "inspection_approval_submission", ["pct_submission_id"])


def downgrade() -> None:
    op.drop_index("ix_inspection_approval_submission_pct_submission_id", table_name="inspection_approval_submission")
    op.drop_index("ix_approval_submission_case_stage_round", table_name="inspection_approval_submission")
    op.drop_table("inspection_approval_submission")
    op.drop_constraint("team_member_role_code_known", "inspection_team_member", type_="check")
    op.drop_column("inspection_team_member", "role_code")
    op.drop_column("inspection_plan", "decision_legacy_raw")
    op.drop_column("inspection_plan", "decision_date")
    op.drop_column("inspection_plan", "decision_reference")
    op.drop_constraint("inspection_outcome_minutes_time_requires_date", "inspection_outcome", type_="check")
    op.drop_column("inspection_outcome", "compliance_due_on")
    op.drop_column("inspection_outcome", "minutes_legacy_raw")
    op.drop_column("inspection_outcome", "minutes_recorded_time")
    op.drop_column("inspection_outcome", "minutes_recorded_on")
    op.drop_column("inspection_outcome", "final_evaluation")
