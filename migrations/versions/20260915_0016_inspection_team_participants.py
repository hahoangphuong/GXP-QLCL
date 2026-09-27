"""add structured inspection-team participant identities

Revision ID: 20260915_0016
Revises: 20260914_0015
"""
from alembic import op
import sqlalchemy as sa


revision = "20260915_0016"
down_revision = "20260914_0015"
branch_labels = None
depends_on = None


def _uuid() -> sa.UUID:
    return sa.UUID(as_uuid=False)


def upgrade() -> None:
    # The expand migration replaces the old two-identity constraint with the
    # discriminated shape below; both new kinds intentionally have no Person.
    op.drop_constraint(op.f("ck_inspection_team_member_team_member_has_identity"), "inspection_team_member", type_="check")
    op.create_table(
        "inspection_team_participant_catalog",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("participant_kind", sa.String(32), nullable=False, server_default="ORGANIZATION_REPRESENTATIVE"),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("organization_name", sa.String(255)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("participant_kind = 'ORGANIZATION_REPRESENTATIVE'", name="team_participant_catalog_kind_known"),
    )
    op.create_table(
        "inspection_team_participant_alias",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("participant_id", _uuid(), sa.ForeignKey("inspection_team_participant_catalog.id"), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_sheet", sa.String(64), nullable=False),
        sa.Column("source_value", sa.Text(), nullable=False),
        sa.Column("source_value_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_system", "source_sheet", "source_value_hash"),
    )
    op.create_index("ix_inspection_team_participant_alias_participant_id", "inspection_team_participant_alias", ["participant_id"])
    op.add_column("inspection_team_member", sa.Column("participant_catalog_id", _uuid(), sa.ForeignKey("inspection_team_participant_catalog.id")))
    op.add_column("inspection_team_member", sa.Column("identity_kind", sa.String(32)))
    op.add_column("inspection_team_member", sa.Column("display_name", sa.String(255)))
    op.add_column("inspection_team_member", sa.Column("legacy_source_token", sa.Text()))
    op.create_index("ix_inspection_team_member_participant_catalog_id", "inspection_team_member", ["participant_catalog_id"])
    op.create_check_constraint("team_member_identity_kind_known", "inspection_team_member", "identity_kind IS NULL OR identity_kind IN ('INSPECTOR_PROFILE', 'LEGACY_PERSON', 'ORGANIZATION_REPRESENTATIVE')")
    op.create_check_constraint("team_member_identity_display_name_required", "inspection_team_member", "identity_kind IS NULL OR display_name IS NOT NULL")
    op.create_check_constraint("team_member_identity_shape", "inspection_team_member", "COALESCE(((identity_kind IS NULL AND participant_catalog_id IS NULL AND (inspector_profile_id IS NOT NULL OR person_id IS NOT NULL)) OR (identity_kind = 'INSPECTOR_PROFILE' AND inspector_profile_id IS NOT NULL AND person_id IS NULL AND participant_catalog_id IS NULL) OR (identity_kind = 'LEGACY_PERSON' AND inspector_profile_id IS NULL AND person_id IS NULL AND participant_catalog_id IS NULL) OR (identity_kind = 'ORGANIZATION_REPRESENTATIVE' AND inspector_profile_id IS NULL AND person_id IS NULL AND participant_catalog_id IS NOT NULL)), FALSE)")


def downgrade() -> None:
    # CHECK names are expanded by the project naming convention during
    # upgrade, so downgrade must address the same convention-resolved names.
    op.drop_constraint(
        op.f("ck_inspection_team_member_team_member_identity_shape"),
        "inspection_team_member",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_inspection_team_member_team_member_identity_display_name_required"),
        "inspection_team_member",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_inspection_team_member_team_member_identity_kind_known"),
        "inspection_team_member",
        type_="check",
    )
    op.drop_index("ix_inspection_team_member_participant_catalog_id", table_name="inspection_team_member")
    for name in ("legacy_source_token", "display_name", "identity_kind", "participant_catalog_id"):
        op.drop_column("inspection_team_member", name)
    op.drop_index("ix_inspection_team_participant_alias_participant_id", table_name="inspection_team_participant_alias")
    op.drop_table("inspection_team_participant_alias")
    op.drop_table("inspection_team_participant_catalog")
    op.create_check_constraint(
        op.f("ck_inspection_team_member_team_member_has_identity"),
        "inspection_team_member",
        "inspector_profile_id IS NOT NULL OR person_id IS NOT NULL",
    )
