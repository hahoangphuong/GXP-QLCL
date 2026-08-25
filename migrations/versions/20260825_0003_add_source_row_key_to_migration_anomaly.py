"""add_source_row_key_to_migration_anomaly

Revision ID: 20260825_0003
Revises: c1f9d7c8b2aa
Create Date: 2026-08-25 11:20:00.000000
"""
from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260825_0003"
down_revision = "c1f9d7c8b2aa"
branch_labels = None
depends_on = None


def _backfill_source_row_key() -> None:
    connection = op.get_bind()
    migration_anomaly = sa.table(
        "migration_anomaly",
        sa.column("id", sa.String()),
        sa.column("legacy_row_id", sa.String()),
        sa.column("detail_json", sa.Text()),
        sa.column("source_row_key", sa.String()),
    )
    rows = connection.execute(
        sa.select(
            migration_anomaly.c.id,
            migration_anomaly.c.legacy_row_id,
            migration_anomaly.c.detail_json,
        )
    ).mappings()
    unresolved_ids: list[str] = []
    for row in rows:
        source_row_key: str | None = None
        detail_json = row["detail_json"]
        if detail_json:
            try:
                payload = json.loads(detail_json)
            except (TypeError, ValueError):
                payload = None
            if isinstance(payload, dict):
                candidate = str(payload.get("source_row_key", "") or "").strip()
                if candidate:
                    source_row_key = candidate
        if source_row_key is None:
            legacy_row_id = str(row["legacy_row_id"] or "").strip()
            if legacy_row_id:
                source_row_key = legacy_row_id
        if source_row_key is None:
            unresolved_ids.append(str(row["id"]))
            continue
        connection.execute(
            migration_anomaly.update()
            .where(migration_anomaly.c.id == row["id"])
            .values(source_row_key=source_row_key)
        )
    if unresolved_ids:
        raise RuntimeError(
            "Cannot backfill migration_anomaly.source_row_key for rows: "
            + ", ".join(sorted(unresolved_ids))
        )


def upgrade() -> None:
    with op.batch_alter_table("migration_anomaly") as batch_op:
        batch_op.add_column(sa.Column("source_row_key", sa.String(length=64), nullable=True))
    _backfill_source_row_key()
    with op.batch_alter_table("migration_anomaly") as batch_op:
        batch_op.alter_column("source_row_key", existing_type=sa.String(length=64), nullable=False)
        batch_op.create_index("ix_migration_anomaly_source_row_key", ["source_row_key"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("migration_anomaly") as batch_op:
        batch_op.drop_index("ix_migration_anomaly_source_row_key")
        batch_op.drop_column("source_row_key")
