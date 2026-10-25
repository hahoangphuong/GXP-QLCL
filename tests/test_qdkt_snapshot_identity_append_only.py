"""QĐKT draft identity must remain distinct across versions and Cases."""
from pathlib import Path

from backend.app.db.models.phase1 import QdKtDraftRosterSnapshot, QdKtDraftRosterMember
from backend.app.document.inspection_qd_kt_snapshot_persistence import canonical_roster_sha256
from backend.app.document.inspection_qd_kt_team_snapshot_review import DraftTeamSnapshot, TeamMemberAtDraft


def test_draft_identity_is_not_inferred_from_document_version():
    table = QdKtDraftRosterSnapshot.__table__
    assert table.c.draft_id.nullable is False
    assert table.c.document_version_id.unique is True
    unique = {frozenset(column.name for column in constraint.columns)
              for constraint in table.constraints if constraint.__class__.__name__ == "UniqueConstraint"}
    assert {"case_id", "draft_id"} in [set(columns) for columns in unique]
    assert QdKtDraftRosterMember.__table__.c.snapshot_id.foreign_keys


def test_digest_is_derived_from_ordered_display_fields():
    members = (
        TeamMemberAtDraft("a", "Name A", "LEADER", "Title"),
        TeamMemberAtDraft("b", "Name B", "MEMBER", "Title"),
    )
    draft = DraftTeamSnapshot("case", "draft", "version", "team", 2, members)
    reordered = DraftTeamSnapshot("case", "draft", "version", "team", 2, members[::-1])
    assert canonical_roster_sha256(draft) != canonical_roster_sha256(reordered)


def test_migration_has_no_historical_backfill_and_deny_mutation_triggers():
    src = Path("migrations/versions/20261025_0025_qdkt_snapshot_identity_append_only.py").read_text()
    assert 'down_revision = "20261025_0024"' in src
    assert "QDKT_0025_REQUIRES_EMPTY_UNLINKED_SNAPSHOTS" in src
    assert "BEFORE UPDATE OR DELETE" in src
    assert "QDKT_SNAPSHOT_APPEND_ONLY" in src
    assert "QDKT_0025_DOWNGRADE_REQUIRES_EMPTY_TABLES" in src
