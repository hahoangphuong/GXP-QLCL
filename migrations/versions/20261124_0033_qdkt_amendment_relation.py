"""Allow explicit AMENDS without conflating amendment and replacement."""
from alembic import op
import sqlalchemy as sa

revision = "20261124_0033"
down_revision = "20261124_0032"
branch_labels = None
depends_on = None

_RELATION_CHECK = "ck_inspection_decision_inspection_decision_relation_known"


def upgrade():
    with op.batch_alter_table("inspection_decision") as batch:
        batch.drop_constraint(op.f(_RELATION_CHECK), type_="check")
        batch.create_check_constraint(
            "inspection_decision_relation_known",
            "relation_type IS NULL OR relation_type IN ('REPLACES', 'AMENDS')",
        )


def downgrade():
    if op.get_bind().execute(sa.text(
        "SELECT count(*) FROM inspection_decision WHERE relation_type = 'AMENDS'"
    )).scalar_one():
        raise RuntimeError("Refusing to downgrade explicit amended QDKT decision history.")
    with op.batch_alter_table("inspection_decision") as batch:
        batch.drop_constraint(op.f(_RELATION_CHECK), type_="check")
        batch.create_check_constraint(
            "inspection_decision_relation_known",
            "relation_type IS NULL OR relation_type IN ('REPLACES')",
        )
