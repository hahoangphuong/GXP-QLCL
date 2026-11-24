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
        sa.Column("created_by_user_id", UUID_TEXT_SAFE, sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("purpose IN ('INITIAL', 'AMENDMENT', 'REPLACEMENT')", name="qdkt_preparation_purpose_known"),
        sa.CheckConstraint("length(trim(notes)) <= 4000", name="qdkt_preparation_notes_length"),
    )
    op.create_index("ix_qdkt_preparation_case_id", "qdkt_preparation", ["case_id"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM qdkt_preparation")).scalar_one():
        raise RuntimeError("Refusing to discard persisted QĐKT preparation intents.")
    op.drop_index("ix_qdkt_preparation_case_id", table_name="qdkt_preparation")
    op.drop_table("qdkt_preparation")
