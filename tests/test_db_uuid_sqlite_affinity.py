"""SQLite must never coerce a valid UUID into a floating-point number."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    CaseScopeRevision,
    Company,
    EvaluationScopeTaxonomyNode,
)


@pytest.mark.parametrize(
    "model, field",
    [
        (Company, "id"),
        (EvaluationScopeTaxonomyNode, "id"),
        (EvaluationScopeTaxonomyNode, "parent_node_id"),
        (CaseScopeRevision, "supersedes_revision_id"),
    ],
)
def test_uuid_model_columns_use_sqlite_text_and_native_postgres_uuid(model, field):
    declared = model.__table__.c[field].type
    assert declared.compile(dialect=sqlite.dialect()) == "VARCHAR(36)"
    assert declared.compile(dialect=postgresql.dialect()) == "UUID"


@pytest.mark.parametrize(
    "identity",
    [
        "12345678-e999-9999-9999-999999999999",  # Old SQLite UUID affinity -> inf.
        "12345678-9012-3456-7890-123456789012",  # Old UUID affinity -> float.
        "deadbeef-1234-4567-8901-abcdef123456",
    ],
)
def test_uuid_roundtrips_without_sqlite_numeric_affinity(identity):
    engine = create_engine("sqlite:///:memory:", future=True)
    Company.__table__.create(engine)
    try:
        with Session(engine) as session:
            session.add(Company(id=identity, legal_name="UUID probe"))
            session.commit()
            loaded = session.get(Company, identity)
            assert loaded is not None
            assert loaded.id == identity
            assert session.scalar(
                text("SELECT typeof(id) FROM company WHERE id = :identity"),
                {"identity": identity},
            ) == "text"
            assert session.scalars(select(Company.id)).all() == [identity]
    finally:
        engine.dispose()
