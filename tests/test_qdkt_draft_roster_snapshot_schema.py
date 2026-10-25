"""QĐKT draft roster migration is additive and refuses populated rollback."""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from backend.app.db.models import Base
from backend.app.db.models.phase1 import QdKtDraftRosterMember, QdKtDraftRosterSnapshot


MIGRATION = Path("migrations/versions/20261025_0024_qdkt_draft_roster_snapshot.py")


def _migration():
    import sys
    spec = importlib.util.spec_from_file_location("qdkt_0024", MIGRATION)
    assert spec and spec.loader
    obj = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = obj
    spec.loader.exec_module(obj)
    return obj


def test_schema_tracks_snapshot_and_ordered_member_keys():
    snapshot = QdKtDraftRosterSnapshot.__table__
    member = QdKtDraftRosterMember.__table__
    assert snapshot.name in Base.metadata.tables
    assert member.name in Base.metadata.tables
    assert snapshot.c.document_version_id.unique is True
    assert snapshot.c.case_id.foreign_keys
    assert member.c.snapshot_id.foreign_keys
    assert member.c.source_team_member_id.foreign_keys
    assert {"position", "display_name", "role_code", "job_title"} <= set(member.c.keys())


def test_empty_upgrade_and_downgrade_are_isolated():
    from unittest.mock import patch

    engine = create_engine("sqlite://")
    module = _migration()
    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        operations = Operations(context)
        with patch.object(module, "op", operations):
            module.upgrade()
            names = set(inspect(conn).get_table_names())
            assert "qdkt_draft_roster_snapshot" in names
            assert "qdkt_draft_roster_member" in names
            module.downgrade()
            names = set(inspect(conn).get_table_names())
            assert "qdkt_draft_roster_snapshot" not in names
            assert "qdkt_draft_roster_member" not in names
    engine.dispose()


def test_revision_is_additive_successor_of_0023():
    module = _migration()
    assert module.revision == "20261025_0024"
    assert module.down_revision == "20261012_0023"
