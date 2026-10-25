from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest

from backend.app.document.inspection_qd_kt_team_snapshot_review import (
    DraftTeamSnapshot, TeamMemberAtDraft,
)
from backend.app.document.inspection_qd_kt_snapshot_persistence import (
    QdKtSnapshotWriteBlocked, canonical_roster_sha256, stage_qdkt_draft_snapshot,
)


def snapshot():
    return DraftTeamSnapshot(
        case_id="case-1", draft_id="draft-1", document_version_id="doc-version-1",
        team_id="team-1", team_revision=2,
        members=(
            TeamMemberAtDraft("member-1", "Nguyen Van A", "LEADER", "Truong phong"),
            TeamMemberAtDraft("member-2", "Nguyen Van B", "MEMBER", "Chuyen vien"),
        ),
    )


class FakeSession:
    def __init__(self, snap, *, revision=None, members=None, existing=None, persisted=None):
        self.team = SimpleNamespace(row_version=revision if revision is not None else snap.team_revision)
        self.members = members if members is not None else [
            SimpleNamespace(id=m.inspector_id, display_name=m.display_name, role_code=m.role)
            for m in snap.members
        ]
        self.existing = existing
        self.persisted = persisted or []
        self.items = []
        self.flush_count = 0
        self.read_number = 0

    def scalar(self, statement):
        self.read_number += 1
        return self.team if self.read_number == 1 else self.existing

    def scalars(self, statement):
        self.read_number += 1
        return SimpleNamespace(all=lambda: self.members if self.read_number == 2 else self.persisted)

    def add(self, obj):
        self.items.append(obj)

    def flush(self):
        self.flush_count += 1
        for item in self.items:
            if item.__class__.__name__ == "QdKtDraftRosterSnapshot" and item.id is None:
                item.id = "snapshot-1"


@pytest.fixture
def bound(monkeypatch):
    import backend.app.document.inspection_qd_kt_snapshot_persistence as module

    def valid_binding(_session, *, snapshot):
        return SimpleNamespace(stored_checksum_sha256="a" * 64)
    monkeypatch.setattr(module, "require_qdkt_draft_version_binding", valid_binding)


def args(snap):
    return {
        "snapshot": snap, "actor_user_id": "actor-1",
        "rendered_roster_sha256": canonical_roster_sha256(snap),
        "expected_docx_sha256": "a" * 64,
    }


def test_stages_snapshot_members_and_audit_without_commit(bound):
    snap = snapshot()
    session = FakeSession(snap)
    row = stage_qdkt_draft_snapshot(session, **args(snap))
    assert row.document_version_id == snap.document_version_id
    assert row.roster_sha256 == canonical_roster_sha256(snap)
    assert session.flush_count == 1
    assert [x.__class__.__name__ for x in session.items] == [
        "QdKtDraftRosterSnapshot", "QdKtDraftRosterMember",
        "QdKtDraftRosterMember", "AuditEvent",
    ]


@pytest.mark.parametrize("change,error", [
    ({"actor_user_id": ""}, "ACTOR_REQUIRED"),
    ({"rendered_roster_sha256": "0" * 64}, "RENDERED_ROSTER_DIGEST_MISMATCH"),
    ({"expected_docx_sha256": "0" * 64}, "DRAFT_BINARY_CHECKSUM_CHANGED"),
])
def test_invalid_proof_blocks_without_staging(bound, change, error):
    snap = snapshot()
    session = FakeSession(snap)
    with pytest.raises(QdKtSnapshotWriteBlocked, match=error):
        stage_qdkt_draft_snapshot(session, **{**args(snap), **change})
    assert not session.items


def test_stale_team_revision_blocks_without_staging(bound):
    snap = snapshot()
    session = FakeSession(snap, revision=3)
    with pytest.raises(QdKtSnapshotWriteBlocked, match="TEAM_STALE"):
        stage_qdkt_draft_snapshot(session, **args(snap))
    assert not session.items


def test_changed_roster_blocks_without_staging(bound):
    snap = snapshot()
    session = FakeSession(snap, members=[
        SimpleNamespace(id="member-1", display_name="Nguyen Van A", role_code="LEADER"),
        SimpleNamespace(id="member-3", display_name="Other", role_code="MEMBER"),
    ])
    with pytest.raises(QdKtSnapshotWriteBlocked, match="MEMBERS_STALE"):
        stage_qdkt_draft_snapshot(session, **args(snap))
    assert not session.items


def test_duplicate_draft_version_rejects_mismatched_snapshot(bound):
    snap = snapshot()
    existing = SimpleNamespace(
        id="previous", case_id="case-1", source_team_id="team-1",
        source_team_revision=2, roster_sha256="0" * 64,
    )
    session = FakeSession(snap, existing=existing)
    with pytest.raises(QdKtSnapshotWriteBlocked, match="ALREADY_BOUND"):
        stage_qdkt_draft_snapshot(session, **args(snap))
    assert not session.items
