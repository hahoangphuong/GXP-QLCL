"""Decision-specific QĐKT roster persistence must not imply approval."""
from pathlib import Path
from sqlalchemy import create_engine
from backend.app.db.models import Base
from backend.app.db.models.phase1 import QdKtIssuedRoster, QdKtIssuedRosterMember


def test_issued_roster_is_owned_by_specific_decision_not_case_team():
    parent = QdKtIssuedRoster.__table__
    child = QdKtIssuedRosterMember.__table__
    assert parent.name in Base.metadata.tables
    assert parent.c.inspection_decision_id.unique is True
    assert parent.c.inspection_decision_id.foreign_keys
    assert parent.c.source_draft_snapshot_id.nullable
    assert parent.c.confirmed_by_user_id.nullable is False
    assert child.c.issued_roster_id.foreign_keys
    assert child.c.position.nullable is False


def test_migration_is_additive_and_refuses_nonempty_rollback():
    source = Path("migrations/versions/20261025_0026_qdkt_issued_roster.py").read_text()
    assert 'down_revision = "20261025_0025"' in source
    assert 'QDKT_0026_DOWNGRADE_REQUIRES_EMPTY_TABLES' in source
    assert "BEFORE UPDATE OR DELETE" in source
    assert "UPDATE inspection_decision" not in source
    assert "INSERT INTO" not in source
