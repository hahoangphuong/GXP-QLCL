from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

import pytest

from backend.app.document.inspection_qd_kt_team_snapshot_review import (
    DraftTeamSnapshot, TeamMemberAtDraft,
)
from backend.app.document.inspection_qd_kt_draft_version_binding import (
    QdKtDraftVersionBindingBlocked, require_qdkt_draft_version_binding,
)


def snap():
    return DraftTeamSnapshot(
        "case-a", "draft-1", "version-1", "team-1", 2,
        (TeamMemberAtDraft("member-1", "Nguyen Van A", "LEADER", "Thanh tra vien"),),
    )


class ReadOnlySession:
    no_autoflush = nullcontext()

    def __init__(self, record):
        self.record = record
        self.executed = 0

    def execute(self, stmt):
        self.executed += 1
        return self

    def one_or_none(self):
        return self.record


def record(*, case_id="case-a", family="INSPECTION_QD_KT",
           checksum="a" * 64, storage="binding-1"):
    version = SimpleNamespace(
        id="version-1", document_variant_id="variant-1",
        checksum_sha256=checksum, storage_binding_id=storage,
        storage_root=None, storage_relative_path=None,
    )
    variant = SimpleNamespace(id="variant-1", document_id="doc-1")
    doc = SimpleNamespace(id="doc-1", case_id=case_id, family_code=family)
    return version, variant, doc


def test_read_only_binding_keeps_binary_and_issuance_claims_false():
    session = ReadOnlySession(record())
    result = require_qdkt_draft_version_binding(session, snapshot=snap())
    assert result.case_id == "case-a"
    assert result.document_version_id == "version-1"
    assert result.roster_member_ids == ("member-1",)
    assert result.stored_checksum_sha256 == "a" * 64
    assert result.confirmed_binary_roster_match is False
    assert result.approved_decision_link is False
    assert session.executed == 1


@pytest.mark.parametrize("row,error", [
    (None, "VERSION_NOT_FOUND"),
    (record(case_id="case-b"), "OWNER_MISMATCH"),
    (record(family="INSPECTION_KE_HOACH_KT"), "OWNER_MISMATCH"),
    (record(checksum=None), "CHECKSUM_MISSING"),
    (record(checksum="bad"), "CHECKSUM_MISSING"),
    (record(storage=None), "STORAGE_UNBOUND"),
])
def test_missing_cross_case_or_unpinned_document_fails_closed(row, error):
    with pytest.raises(QdKtDraftVersionBindingBlocked, match=error):
        require_qdkt_draft_version_binding(
            ReadOnlySession(row), snapshot=snap(),
        )


def test_invalid_snapshot_never_queries_document():
    session = ReadOnlySession(record())
    with pytest.raises(ValueError, match="DRAFT_DISPLAY_PROVENANCE_INVALID"):
        require_qdkt_draft_version_binding(
            session, snapshot=replace(snap(), document_version_id=""),
        )
    assert session.executed == 0
