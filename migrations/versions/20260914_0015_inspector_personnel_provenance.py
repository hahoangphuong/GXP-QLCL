"""add inspector personnel master fields and TTviên source provenance

Revision ID: 20260914_0015
Revises: 20260913_0014
"""
from alembic import op
import sqlalchemy as sa


revision = "20260914_0015"
down_revision = "20260913_0014"
branch_labels = None
depends_on = None


ROSTER_GROUP_CHECK = (
    "roster_group IS NULL OR roster_group IN "
    "('DRUG_ADMINISTRATION_AND_TRADITIONAL_MEDICINE', "
    "'NATIONAL_INSTITUTE_OF_DRUG_QUALITY_CONTROL', "
    "'HO_CHI_MINH_CITY_DRUG_QUALITY_CONTROL_INSTITUTE', "
    "'NATIONAL_INSTITUTE_FOR_VACCINE_AND_BIOLOGICALS_CONTROL', "
    "'PROVINCIAL_HEALTH_DEPARTMENTS')"
)


def _uuid() -> sa.UUID:
    return sa.UUID(as_uuid=False)


def upgrade() -> None:
    # Nullable source-derived text preserves pre-B3 inspector profiles without inventing roster facts.
    op.add_column("inspector_profile", sa.Column("roster_group", sa.String(length=64), nullable=True))
    op.add_column("inspector_profile", sa.Column("honorific", sa.String(length=64), nullable=True))
    op.add_column("inspector_profile", sa.Column("qualification", sa.String(length=255), nullable=True))
    op.add_column("inspector_profile", sa.Column("position", sa.String(length=255), nullable=True))
    op.add_column("inspector_profile", sa.Column("organizational_unit", sa.String(length=255), nullable=True))
    op.add_column("inspector_profile", sa.Column("professional_specialty", sa.String(length=255), nullable=True))
    op.add_column("inspector_profile", sa.Column("legacy_pct_marker", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("inspector_profile", sa.Column("legacy_star_marker", sa.Boolean(), nullable=False, server_default="false"))
    op.create_check_constraint("inspector_profile_roster_group_known", "inspector_profile", ROSTER_GROUP_CHECK)
    op.create_index("ix_inspector_profile_roster_group", "inspector_profile", ["roster_group"])
    op.create_index("ix_inspector_profile_professional_specialty", "inspector_profile", ["professional_specialty"])

    op.create_table(
        "legacy_inspector_source_record",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_sheet", sa.String(length=64), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("inspector_profile_id", _uuid(), nullable=False),
        sa.Column("canonical_payload_sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["inspector_profile_id"], ["inspector_profile.id"]),
        sa.UniqueConstraint("snapshot_sha256", "source_sheet", "source_row_number"),
        sa.CheckConstraint("source_row_number >= 1", name="legacy_inspector_source_record_row_positive"),
        sa.CheckConstraint("source_sheet = 'TTviên'", name="legacy_inspector_source_record_sheet_known"),
    )
    op.create_index(
        "ix_legacy_inspector_source_record_inspector_profile_id",
        "legacy_inspector_source_record",
        ["inspector_profile_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_legacy_inspector_source_record_inspector_profile_id", table_name="legacy_inspector_source_record")
    op.drop_table("legacy_inspector_source_record")
    op.drop_index("ix_inspector_profile_professional_specialty", table_name="inspector_profile")
    op.drop_index("ix_inspector_profile_roster_group", table_name="inspector_profile")
    op.drop_constraint("inspector_profile_roster_group_known", "inspector_profile", type_="check")
    op.drop_column("inspector_profile", "legacy_star_marker")
    op.drop_column("inspector_profile", "legacy_pct_marker")
    op.drop_column("inspector_profile", "professional_specialty")
    op.drop_column("inspector_profile", "organizational_unit")
    op.drop_column("inspector_profile", "position")
    op.drop_column("inspector_profile", "qualification")
    op.drop_column("inspector_profile", "honorific")
    op.drop_column("inspector_profile", "roster_group")
