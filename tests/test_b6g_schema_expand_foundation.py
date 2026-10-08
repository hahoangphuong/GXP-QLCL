from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from backend.app.db.models import Base
from backend.app.db.models.phase1 import (
    Case,
    CaseScopePhase,
    CaseScopeRevision,
    Certificate,
    CertificateRelationship,
    CertificateVersion,
    ProductionLine,
    ProductionLineTransformation,
    ProductionLineTransformationMember,
)


MIGRATION = Path("migrations/versions/20260929_0017_production_line_scope_certificate_foundation.py")

B6G_TABLES = (
    ProductionLine.__table__,
    ProductionLineTransformation.__table__,
    ProductionLineTransformationMember.__table__,
    CaseScopePhase.__table__,
    CaseScopeRevision.__table__,
    Base.metadata.tables["case_scope_revision_block"],
    Base.metadata.tables["case_scope_revision_selection"],
    Base.metadata.tables["case_scope_revision_unkeyed_entry"],
    CertificateRelationship.__table__,
)


def _constraint_names(table: object) -> set[str | None]:
    return {constraint.name for constraint in table.constraints}  # type: ignore[attr-defined]


def test_b6g_metadata_contains_expand_only_foundation_tables_and_nullable_ownership_fks():
    assert {
        "production_line",
        "production_line_transformation",
        "production_line_transformation_member",
        "case_scope_phase",
        "case_scope_revision",
        "case_scope_revision_block",
        "case_scope_revision_selection",
        "case_scope_revision_unkeyed_entry",
        "certificate_relationship",
    }.issubset(Base.metadata.tables)
    assert Case.__table__.c.production_line_id.nullable is True
    assert Certificate.__table__.c.production_line_id.nullable is True
    assert "scope_code" in Case.__table__.c
    assert "line_code" in Certificate.__table__.c


def test_production_line_identity_uses_effective_interval_without_unproven_gxp_or_unique_code_key():
    table = ProductionLine.__table__
    assert {"site_id", "code", "effective_from", "effective_to", "row_version"}.issubset(table.c.keys())
    assert "gxp_type" not in table.c
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("site_id", "code") not in unique_columns
    assert "ck_production_line_production_line_effective_interval" in _constraint_names(table)
    assert "ix_production_line_site_code" in {index.name for index in table.indexes}


def test_transformation_owner_and_member_schema_enforce_per_role_ordinal_shape_but_not_service_graph_rules():
    transformation = ProductionLineTransformation.__table__
    assert {
        "site_id",
        "transformation_type",
        "effective_on",
        "reason",
        "created_by_user_id",
        "row_version",
    }.issubset(transformation.c.keys())
    assert transformation.c.site_id.nullable is False
    assert transformation.c.created_by_user_id.nullable is False
    assert {
        "ck_production_line_transformation_production_line_transformation_type_known",
        "ck_production_line_transformation_production_line_transformation_reason_nonblank",
    } <= _constraint_names(transformation)
    assert {
        "ix_production_line_transformation_site_id",
        "ix_production_line_transformation_created_by_user_id",
        "ix_production_line_transformation_effective_on",
    } <= {index.name for index in transformation.indexes}

    table = ProductionLineTransformationMember.__table__
    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert unique_constraints["uq_production_line_transformation_member_line"] == (
        "transformation_id",
        "production_line_id",
    )
    assert unique_constraints["uq_production_line_transformation_member_role_ordinal"] == (
        "transformation_id",
        "member_role",
        "ordinal",
    )
    assert ("transformation_id", "ordinal") not in unique_constraints.values()
    names = _constraint_names(table)
    assert "ck_production_line_transformation_member_production_line_transformation_member_role_known" in names
    assert "ck_production_line_transformation_member_production_line_transformation_member_ordinal_positive" in names
    assert "acyclic" not in "\n".join(filter(None, names)).lower()


def test_b6g_metadata_names_every_schema_object_without_collisions():
    named_objects = [
        (table.name, constraint.name)
        for table in B6G_TABLES
        for constraint in table.constraints
        if constraint.name is not None
    ] + [
        (table.name, index.name)
        for table in B6G_TABLES
        for index in table.indexes
        if index.name is not None
    ]
    names = [name for _, name in named_objects]
    assert len(names) == len(set(names)), named_objects


def test_scope_phase_revision_schema_preserves_phase_identity_and_postgresql_current_indexes():
    phase = CaseScopePhase.__table__
    revision = CaseScopeRevision.__table__
    assert ("case_id", "phase") in {
        tuple(column.name for column in constraint.columns)
        for constraint in phase.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    names = _constraint_names(revision)
    assert {
        "ck_case_scope_revision_case_scope_revision_number_positive",
        "ck_case_scope_revision_case_scope_revision_state_known",
        "ck_case_scope_revision_case_scope_revision_draft_not_current",
        "ck_case_scope_revision_case_scope_revision_established_requires_timestamp",
        "ck_case_scope_revision_case_scope_revision_not_self_superseding",
        "ck_case_scope_revision_case_scope_revision_correction_reason_required",
    } <= names
    assert {
        "created_by_user_id",
        "established_at",
        "established_by_user_id",
        "correction_reason",
    }.issubset(revision.c.keys())
    assert {"ix_case_scope_revision_created_by_user_id", "ix_case_scope_revision_established_by_user_id"} <= {
        index.name for index in revision.indexes
    }
    indexes = {index.name: index for index in revision.indexes}
    assert {"uq_case_scope_revision_one_draft", "uq_case_scope_revision_one_current_established"} <= set(indexes)
    assert "WHERE state = 'DRAFT'" in str(CreateIndex(indexes["uq_case_scope_revision_one_draft"]).compile(dialect=postgresql.dialect()))
    assert "WHERE is_current_established" in str(
        CreateIndex(indexes["uq_case_scope_revision_one_current_established"]).compile(dialect=postgresql.dialect())
    )


def test_certificate_lifecycle_schema_is_identity_owned_and_preserves_unknown_legacy_state():
    version = CertificateVersion.__table__
    relationship = CertificateRelationship.__table__
    assert version.c.lifecycle_state.nullable is True
    assert "case_id" not in version.c
    assert "production_line_id" not in version.c
    assert "ck_certificate_version_certificate_version_lifecycle_state_known" in _constraint_names(version)
    assert {
        "ck_certificate_relationship_certificate_relationship_not_self",
        "ck_certificate_relationship_certificate_relationship_type_known",
    } <= _constraint_names(relationship)
    assert ("source_certificate_id", "target_certificate_id", "relation_type") in {
        tuple(column.name for column in constraint.columns)
        for constraint in relationship.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }


def test_b6g_migration_is_expand_only_and_reversible_to_0016():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260929_0017"' in source
    assert 'down_revision = "20260915_0016"' in source
    assert "op.create_table(\n        \"production_line\"" in source
    assert "op.add_column(\"case\", sa.Column(\"production_line_id\"" in source
    assert "op.add_column(\"certificate\", sa.Column(\"production_line_id\"" in source
    assert "op.add_column(\"certificate_version\", sa.Column(\"lifecycle_state\"" in source
    assert 'name="uq_production_line_transformation_member_line"' in source
    assert 'name="uq_production_line_transformation_member_role_ordinal"' in source
    assert "UPDATE " not in source
    assert "INSERT INTO " not in source
    assert "DELETE FROM " not in source
    assert "op.drop_column(\"case\", \"production_line_id\")" in source
    assert "op.drop_column(\"certificate\", \"production_line_id\")" in source
    assert "op.drop_column(\"certificate_version\", \"lifecycle_state\")" in source


def test_b6g_migration_upgrade_and_downgrade_cover_only_the_expand_contract():
    spec = importlib.util.spec_from_file_location("migration_20260929_0017", MIGRATION)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    class RecordingOperations:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

        def f(self, name: str) -> str:
            return f"resolved:{name}"

        def __getattr__(self, name: str):
            def operation(*args: object, **kwargs: object) -> None:
                self.calls.append((name, args, kwargs))

            return operation

    operations = RecordingOperations()
    migration.op = operations
    migration.upgrade()
    upgraded_tables = {args[0] for name, args, _ in operations.calls if name == "create_table"}
    assert {
        "production_line",
        "production_line_transformation",
        "production_line_transformation_member",
        "case_scope_phase",
        "case_scope_revision",
        "certificate_relationship",
    } <= upgraded_tables
    assert any(name == "add_column" and args[0] == "case" for name, args, _ in operations.calls)
    assert any(name == "add_column" and args[0] == "certificate" for name, args, _ in operations.calls)

    operations.calls.clear()
    migration.downgrade()
    dropped_tables = [args[0] for name, args, _ in operations.calls if name == "drop_table"]
    assert dropped_tables[:3] == [
        "certificate_relationship",
        "case_scope_revision_unkeyed_entry",
        "case_scope_revision_selection",
    ]
    assert any(name == "drop_column" and args == ("case", "production_line_id") for name, args, _ in operations.calls)
    assert any(
        name == "drop_column" and args == ("certificate_version", "lifecycle_state")
        for name, args, _ in operations.calls
    )


def test_b6g_postgresql_ddl_renders_new_foundation_tables_and_partial_indexes():
    for table in (ProductionLine.__table__, CaseScopeRevision.__table__, CertificateRelationship.__table__):
        assert "CREATE TABLE" in str(CreateTable(table).compile(dialect=postgresql.dialect()))
    for index in CaseScopeRevision.__table__.indexes:
        if index.name and index.name.startswith("uq_case_scope_revision_one_"):
            assert "CREATE UNIQUE INDEX" in str(CreateIndex(index).compile(dialect=postgresql.dialect()))
