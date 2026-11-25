from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

import pytest

from backend.app.db.enums import DocumentVariantType
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
           checksum="a" * 64, storage="binding-1", binding_case="case-a",
           root=None, locator=None, persisted_binding=None,
           variant_type=DocumentVariantType.EDITABLE_DOCX):
    # Scalar tuple from the exact single joined SQL statement, not ORM
    # instances; tests must not accidentally permit identity-map hydration.
    return (
        "version-1", "variant-1", "variant-1", "doc-1",
        variant_type, "doc-1", case_id, family, checksum,
        storage, root, locator,
        storage if persisted_binding is None else persisted_binding,
        binding_case,
    )


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
    (record(variant_type=DocumentVariantType.SCANNED_PDF), "NOT_EDITABLE_DOCX"),
    (record(variant_type=DocumentVariantType.GENERATED_PDF), "NOT_EDITABLE_DOCX"),
    (record(variant_type=DocumentVariantType.EDITABLE_XLSX), "NOT_EDITABLE_DOCX"),
    (record(variant_type=None), "NOT_EDITABLE_DOCX"),
    (record(checksum=None), "CHECKSUM_MISSING"),
    (record(checksum="bad"), "CHECKSUM_MISSING"),
    (record(storage=None), "STORAGE_UNBOUND"),
    (record(storage="binding-1", binding_case="case-b"), "STORAGE_OWNER_MISMATCH"),
    (record(storage="binding-1", persisted_binding="binding-2"), "STORAGE_OWNER_MISMATCH"),
    (record(storage=None, root="synology", locator=None), "STORAGE_UNBOUND"),
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


def test_explicit_root_locator_can_bind_without_binding_row():
    actual = require_qdkt_draft_version_binding(
        ReadOnlySession(record(storage=None, root="synology",
                               locator="case-a/drafts/draft.docx")),
        snapshot=snap(),
    )
    assert actual.document_version_id == "version-1"
    assert actual.confirmed_binary_roster_match is False
    assert actual.approved_decision_link is False


@pytest.mark.parametrize("locator", [
    "../other-case/draft.docx",
    "case-a/../../other-case/draft.docx",
    "/other-case/draft.docx",
    r"\\server\share\draft.docx",
    "C:/other-case/draft.docx",
    "case-a//draft.docx",
    "case-a/./draft.docx",
    "case-a\\draft.docx",
    "case-a/draft.docx\x00",
    "case-a/draft.docx:stream",
    "case-a/draft.docx.",
    "case-a/draft.docx ",
    "case-a/COM¹/draft.docx",
    "case-a/NUL.docx",
    "case-a/draft\u202e.docx",
    "case-a/cafe\u0301.docx",
    "case-a/draft\x85.docx",
])
def test_unbound_unsafe_storage_locator_fails_closed(locator):
    session = ReadOnlySession(record(storage=None, root="synology", locator=locator))
    with pytest.raises(QdKtDraftVersionBindingBlocked, match="STORAGE_LOCATOR_INVALID"):
        require_qdkt_draft_version_binding(session, snapshot=snap())
    assert session.executed == 1


def test_bound_storage_does_not_treat_optional_legacy_locator_as_authority():
    # When a real StorageBinding exists, its Case owner is authoritative;
    # optional legacy root/path metadata cannot override that binding.
    result = require_qdkt_draft_version_binding(
        ReadOnlySession(record(storage="binding-1", root=None, locator=None)),
        snapshot=snap(),
    )
    assert result.document_version_id == "version-1"


@pytest.mark.parametrize("locator", [
    "hồ-sơ/quyết-định.docx",
    "case-a/COM10/draft.final.docx",
])
def test_canonical_relative_locator_keeps_metadata_only_binding(locator):
    result = require_qdkt_draft_version_binding(
        ReadOnlySession(record(storage=None, root="synology", locator=locator)),
        snapshot=snap(),
    )
    assert not result.confirmed_binary_roster_match
    assert not result.approved_decision_link
