"""Add independent editable QĐKT preparation intents; no backfill."""
from alembic import op
import sqlalchemy as sa
from backend.app.db.base import UUID_TEXT_SAFE

revision = "20261124_0032"
down_revision = "20261113_0031"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "qdkt_preparation",
        sa.Column("id", UUID_TEXT_SAFE, primary_key=True),
        sa.Column("case_id", UUID_TEXT_SAFE, sa.ForeignKey("case.id"), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PREPARING"),
        sa.CheckConstraint("status IN ('PREPARING', 'CANCELLED')", name="qdkt_preparation_status_known"),
        sa.Column("created_by_user_id", UUID_TEXT_SAFE, sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("purpose IN ('INITIAL', 'AMENDMENT', 'REPLACEMENT')", name="qdkt_preparation_purpose_known"),
        sa.CheckConstraint("length(trim(notes)) <= 4000", name="qdkt_preparation_notes_length"),
    )
    op.create_index("ix_qdkt_preparation_case_id", "qdkt_preparation", ["case_id"])
    op.create_table(
        "qdkt_preparation_member",
        sa.Column("id", UUID_TEXT_SAFE, primary_key=True),
        sa.Column("preparation_id", UUID_TEXT_SAFE, sa.ForeignKey("qdkt_preparation.id"), nullable=False),
        sa.Column("source_team_id", UUID_TEXT_SAFE, nullable=False),
        sa.Column("source_team_revision", sa.Integer(), nullable=False),
        sa.Column("source_member_id", UUID_TEXT_SAFE, nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("role_code", sa.String(16), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("preparation_id", "sort_order"),
        sa.UniqueConstraint("preparation_id", "source_member_id"),
        sa.CheckConstraint("source_team_revision >= 1", name="qdkt_preparation_member_revision_positive"),
        sa.CheckConstraint("sort_order >= 0", name="qdkt_preparation_member_order_nonnegative"),
        sa.CheckConstraint("role_code IN ('LEADER', 'SECRETARY', 'MEMBER')", name="qdkt_preparation_member_role_known"),
        sa.CheckConstraint("length(trim(display_name)) > 0", name="qdkt_preparation_member_name_nonblank"),
    )
    op.create_index("ix_qdkt_preparation_member_preparation_id", "qdkt_preparation_member", ["preparation_id"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM qdkt_preparation")).scalar_one():
        raise RuntimeError("Refusing to discard persisted QĐKT preparation intents.")
    op.drop_table("qdkt_preparation_member")
    op.drop_index("ix_qdkt_preparation_case_id", table_name="qdkt_preparation")
    op.drop_table("qdkt_preparation")
