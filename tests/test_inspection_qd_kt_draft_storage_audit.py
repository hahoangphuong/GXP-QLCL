"""Storage-backed DOCX audit uses a pinned exact locator, never a folder search."""
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
from dataclasses import replace
from zipfile import ZipFile

import pytest

from backend.app.document.inspection_qd_kt_draft_provenance import QdKtDraftProvenance
from backend.app.document.inspection_qd_kt_draft_storage_audit import (
    QdKtDraftStorageAuditBlocked, QdKtExactDraftLocator,
    audit_qdkt_draft_storage_binary,
)

CT = "http://schemas.openxmlformats.org/package/2006/content-types"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"


def fixture():
    buf = BytesIO()
    with ZipFile(buf, "w") as out:
        out.writestr("[Content_Types].xml", (
            f'<Types xmlns="{CT}"><Override PartName="/word/document.xml"'
            f' ContentType="{DOCX}"/></Types>'
        ))
        out.writestr("word/document.xml", f'<w:document xmlns:w="{W}"><w:body/></w:document>')
    payload = buf.getvalue()
    source = QdKtDraftProvenance(
        "case-1", "draft-1", "version-1", "document-1",
        sha256(payload).hexdigest(), "team-1", 2, ("member-1",),
    )
    locator = QdKtExactDraftLocator(
        "case-1", "version-1", "inspection", "case-1/qdkt/draft.docx",
        storage_binding_owner_verified=True,
    )
    return payload, source, locator


class FakeStorage:
    def __init__(self, binary):
        self.binary = binary
        self.calls = []

    @contextmanager
    def read_stream(self, path, *, root):
        self.calls.append((path, root))
        yield BytesIO(self.binary)


def test_matching_storage_bytes_are_verified_without_approving_word_layout():
    data, source, locator = fixture()
    storage = FakeStorage(data)
    result = audit_qdkt_draft_storage_binary(storage, provenance=source, locator=locator)
    assert storage.calls == [("case-1/qdkt/draft.docx", "inspection")]
    assert result.actual_docx_bytes_verified
    assert not result.roster_in_document_verified
    assert not result.visual_word_uat_verified
    assert not result.ready_to_render


@pytest.mark.parametrize("changes", [
    {"case_id": "case-2"},
    {"document_version_id": "version-2"},
    {"storage_root": "dkkd"},
    {"storage_relative_path": "../escape.docx"},
    {"storage_relative_path": "/absolute.docx"},
    {"storage_relative_path": "case-1//draft.docx"},
    {"storage_relative_path": "C:drive.docx"},
    {"storage_relative_path": "case-1/qdkt/evil\\x00.docx"},
    {"storage_relative_path": "case-1/qdkt/evil\\n.docx"},
    {"storage_relative_path": "case-1/qdkt/evil\\x7f.docx"},
    {"storage_binding_owner_verified": False},
])
def test_unproven_locator_is_rejected_before_storage_access(changes):
    data, source, locator = fixture()
    storage = FakeStorage(data)
    with pytest.raises(QdKtDraftStorageAuditBlocked, match="LOCATOR_UNPROVEN"):
        audit_qdkt_draft_storage_binary(
            storage, provenance=source, locator=replace(locator, **changes),
        )
    assert storage.calls == []


def test_tampered_storage_bytes_fail_checksum():
    data, source, locator = fixture()
    storage = FakeStorage(data + b"tampered")
    with pytest.raises(ValueError, match="CHECKSUM_MISMATCH"):
        audit_qdkt_draft_storage_binary(storage, provenance=source, locator=locator)


def test_binary_size_limit_stops_stream():
    _, source, locator = fixture()
    storage = FakeStorage(b"x" * (32 * 1024 * 1024 + 1))
    with pytest.raises(QdKtDraftStorageAuditBlocked, match="SIZE_UNSAFE"):
        audit_qdkt_draft_storage_binary(storage, provenance=source, locator=locator)


def test_db_resolved_locator_proves_document_version_and_binding_ownership():
    from contextlib import nullcontext
    from types import SimpleNamespace
    from backend.app.document.inspection_qd_kt_draft_storage_audit import (
        resolve_qdkt_draft_storage_locator,
    )
    data, provenance, _ = fixture()

    class Session:
        no_autoflush = nullcontext()
        def __init__(self, rows):
            self.rows = rows
        def execute(self, statement):
            return self
        def all(self):
            return self.rows

    version = SimpleNamespace(
        id="version-1", document_variant_id="variant-1",
        storage_binding_id="binding-1", storage_root="inspection",
        storage_relative_path="case-1/qdkt/draft.docx",
        checksum_sha256=sha256(data).hexdigest(),
    )
    variant = SimpleNamespace(id="variant-1", document_id="document-1")
    doc = SimpleNamespace(id="document-1", case_id="case-1", family_code="INSPECTION_QD_KT")
    binding = SimpleNamespace(id="binding-1", case_id="case-1", relative_path="case-1")
    result = resolve_qdkt_draft_storage_locator(
        Session([(version, variant, doc, binding)]), provenance=provenance,
    )
    assert result.storage_binding_owner_verified
    assert result.storage_relative_path == "case-1/qdkt/draft.docx"
    for changed in (
        ("case_id", "other-case", binding),
        ("relative_path", "wrong-folder", binding),
    ):
        key, value, _ = changed
        bad_binding = SimpleNamespace(**vars(binding))
        setattr(bad_binding, key, value)
        with pytest.raises(QdKtDraftStorageAuditBlocked, match="OWNER_MISMATCH"):
            resolve_qdkt_draft_storage_locator(
                Session([(version, variant, doc, bad_binding)]), provenance=provenance,
            )
    with pytest.raises(QdKtDraftStorageAuditBlocked, match="NOT_UNIQUE"):
        resolve_qdkt_draft_storage_locator(Session([]), provenance=provenance)


def test_db_binding_rejects_parent_segments_in_bound_folder():
    from contextlib import nullcontext
    from types import SimpleNamespace
    from backend.app.document.inspection_qd_kt_draft_storage_audit import resolve_qdkt_draft_storage_locator
    data, provenance, _ = fixture()

    class Session:
        no_autoflush = nullcontext()
        def __init__(self, values):
            self.values = values
        def execute(self, query):
            return self
        def all(self):
            return self.values

    version = SimpleNamespace(id="version-1", document_variant_id="variant-1",
        storage_binding_id="binding-1", storage_root="inspection",
        storage_relative_path="case-1/../other/draft.docx",
        checksum_sha256=sha256(data).hexdigest())
    variant = SimpleNamespace(id="variant-1", document_id="document-1")
    doc = SimpleNamespace(id="document-1", case_id="case-1", family_code="INSPECTION_QD_KT")
    binding = SimpleNamespace(id="binding-1", case_id="case-1", relative_path="case-1/..")
    with pytest.raises(QdKtDraftStorageAuditBlocked, match="OWNER_MISMATCH"):
        resolve_qdkt_draft_storage_locator(
            Session([(version, variant, doc, binding)]), provenance=provenance,
        )


def test_internal_case_entrypoint_orders_all_gates_before_storage(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from backend.app.document.inspection_qd_kt_draft_storage_audit import audit_case_qdkt_draft_binary_readonly
    from backend.app.document.inspection_qd_kt_team_snapshot_review import DraftTeamSnapshot, TeamMemberAtDraft
    import backend.app.document.inspection_qd_kt_draft_storage_audit as module

    data, source, locator = fixture()
    calls = []
    monkeypatch.setattr(module, "read_qdkt_draft_provenance",
        lambda session, *, case_id, snapshot: calls.append("source") or source)
    monkeypatch.setattr(module, "resolve_qdkt_draft_storage_locator",
        lambda session, *, provenance: calls.append("binding") or locator)
    storage = FakeStorage(data)
    snapshot = DraftTeamSnapshot("case-1", "draft-1", "version-1", "team-1", 2,
        (TeamMemberAtDraft("member-1", "Inspector", "LEADER", "Unverified"),))
    session = SimpleNamespace(no_autoflush=nullcontext())
    evidence = audit_case_qdkt_draft_binary_readonly(
        session, storage, case_id="case-1", snapshot=snapshot,
    )
    assert calls == ["source", "binding", "source", "binding", "source", "binding"]
    assert storage.calls == [(locator.storage_relative_path, "inspection")] * 2
    assert evidence.actual_docx_bytes_verified
    assert not evidence.ready_to_render
    calls.clear()
    storage.calls.clear()
    with pytest.raises(QdKtDraftStorageAuditBlocked, match="CASE_MISMATCH"):
        audit_case_qdkt_draft_binary_readonly(
            session, storage, case_id="other-case", snapshot=snapshot,
        )
    assert calls == [] and storage.calls == []


@pytest.mark.parametrize("invalid", [None, "", "text", bytearray(b"x"), 0])
def test_storage_stream_rejects_nonbyte_chunks_including_falsy_eof(invalid):
    data, source, locator = fixture()

    class MalformedStorage(FakeStorage):
        @contextmanager
        def read_stream(self, path, *, root):
            self.calls.append((path, root))
            class BrokenStream:
                def read(self, n):
                    return invalid
            yield BrokenStream()

    storage = MalformedStorage(data)
    with pytest.raises(QdKtDraftStorageAuditBlocked, match="STREAM_TYPE_INVALID"):
        audit_qdkt_draft_storage_binary(storage, provenance=source, locator=locator)
    assert storage.calls == [(locator.storage_relative_path, "inspection")]


def test_storage_stream_rejects_single_oversized_adapter_chunk():
    data, source, locator = fixture()

    class OverreadStorage(FakeStorage):
        @contextmanager
        def read_stream(self, path, *, root):
            class OverreadingStream:
                def read(self, n):
                    return b"x" * (n + 1)
            yield OverreadingStream()

    with pytest.raises(QdKtDraftStorageAuditBlocked, match="CHUNK_SIZE_UNSAFE"):
        audit_qdkt_draft_storage_binary(
            OverreadStorage(data), provenance=source, locator=locator,
        )


def test_storage_stream_accepts_fragmented_binary_reads():
    data, source, locator = fixture()

    class FragmentedStorage(FakeStorage):
        @contextmanager
        def read_stream(self, path, *, root):
            self.calls.append((path, root))
            class FragmentedStream:
                offset = 0
                def read(self, n):
                    chunk = data[self.offset:self.offset + 7]
                    self.offset += len(chunk)
                    return chunk
            yield FragmentedStream()

    storage = FragmentedStorage(data)
    evidence = audit_qdkt_draft_storage_binary(storage, provenance=source, locator=locator)
    assert evidence.verified_sha256 == sha256(data).hexdigest()
    assert not evidence.ready_to_render


@pytest.mark.parametrize("unsafe_path", [
    "case-1/qdkt/draft\\x00.docx",
    "case-1/qdkt/draft\\r.docx",
    "case-1/qdkt/draft\\x1f.docx",
    "case-1/qdkt/draft\\x7f.docx",
])
def test_db_binding_rejects_control_characters_before_storage_read(unsafe_path):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from backend.app.document.inspection_qd_kt_draft_storage_audit import (
        resolve_qdkt_draft_storage_locator,
    )

    data, provenance, _ = fixture()

    class Session:
        no_autoflush = nullcontext()
        def execute(self, query):
            return self
        def all(self):
            return [(
                SimpleNamespace(id="version-1", document_variant_id="variant-1",
                    storage_binding_id="binding-1", storage_root="inspection",
                    storage_relative_path=unsafe_path,
                    checksum_sha256=sha256(data).hexdigest()),
                SimpleNamespace(id="variant-1", document_id="document-1"),
                SimpleNamespace(id="document-1", case_id="case-1", family_code="INSPECTION_QD_KT"),
                SimpleNamespace(id="binding-1", case_id="case-1", relative_path="case-1"),
            )]

    with pytest.raises(QdKtDraftStorageAuditBlocked, match="OWNER_MISMATCH"):
        resolve_qdkt_draft_storage_locator(Session(), provenance=provenance)


@pytest.mark.parametrize("stage", ["open", "read", "close"])
@pytest.mark.parametrize("error_type", [OSError, RuntimeError, EOFError, ConnectionError, TimeoutError])
def test_storage_adapter_lifecycle_failures_are_blocked(stage, error_type):
    data, source, locator = fixture()

    class BrokenStorage(FakeStorage):
        @contextmanager
        def read_stream(self, path, *, root):
            self.calls.append((path, root))
            if stage == "open":
                raise error_type("adapter interrupted")
            class Stream:
                def read(self, n):
                    if stage == "read":
                        raise error_type("adapter interrupted")
                    if not hasattr(self, "seen"):
                        self.seen = True
                        return data
                    return b""
            try:
                yield Stream()
            finally:
                if stage == "close":
                    raise error_type("adapter interrupted")

    storage = BrokenStorage(data)
    with pytest.raises(QdKtDraftStorageAuditBlocked, match="READ_FAILED") as caught:
        audit_qdkt_draft_storage_binary(storage, provenance=source, locator=locator)
    assert isinstance(caught.value.__cause__, error_type)
    assert storage.calls == [(locator.storage_relative_path, "inspection")]


def test_storage_adapter_programming_error_not_swallowed():
    data, source, locator = fixture()

    class BrokenStorage(FakeStorage):
        @contextmanager
        def read_stream(self, path, *, root):
            self.calls.append((path, root))
            raise TypeError("incorrect storage adapter API")
            yield  # pragma: no cover

    with pytest.raises(TypeError, match="incorrect storage adapter API"):
        audit_qdkt_draft_storage_binary(
            BrokenStorage(data), provenance=source, locator=locator,
        )


@pytest.mark.parametrize("changes", [
    {"stored_checksum_sha256": "not-a-sha256"},
    {"ready_to_render": True},
    {"issuance_approved": True},
    {"case_roster_identity_verified": False},
    {"version_case_ownership_verified": False},
    {"binary_content_verified": True},
    {"job_title_provenance_verified": True},
])
def test_unproven_binary_metadata_blocks_before_storage_read(changes):
    data, source, locator = fixture()
    storage = FakeStorage(data)
    with pytest.raises(ValueError, match="PROVENANCE_UNPROVEN"):
        audit_qdkt_draft_storage_binary(
            storage, provenance=replace(source, **changes), locator=locator,
        )
    assert storage.calls == []


def test_valid_binary_metadata_still_reads_and_keeps_renderer_blocked():
    data, source, locator = fixture()
    storage = FakeStorage(data)
    evidence = audit_qdkt_draft_storage_binary(storage, provenance=source, locator=locator)
    assert storage.calls == [(locator.storage_relative_path, "inspection")]
    assert evidence.actual_docx_bytes_verified
    assert not evidence.ready_to_render


@pytest.mark.parametrize("drift", ["provenance", "locator"])
def test_internal_audit_rejects_observed_source_drift_after_read(monkeypatch, drift):
    from contextlib import nullcontext
    from dataclasses import replace
    from types import SimpleNamespace
    from backend.app.document.inspection_qd_kt_draft_storage_audit import (
        audit_case_qdkt_draft_binary_readonly,
    )
    from backend.app.document.inspection_qd_kt_team_snapshot_review import (
        DraftTeamSnapshot, TeamMemberAtDraft,
    )
    import backend.app.document.inspection_qd_kt_draft_storage_audit as module

    data, source, locator = fixture()
    snapshot = DraftTeamSnapshot("case-1", "draft-1", "version-1", "team-1", 2,
        (TeamMemberAtDraft("member-1", "Inspector", "LEADER", "Unverified"),))
    seen = []
    def source_reader(session, *, case_id, snapshot):
        seen.append("source")
        if drift == "provenance" and seen.count("source") == 2:
            return replace(source, draft_id="changed-draft")
        return source
    def locator_reader(session, *, provenance):
        seen.append("locator")
        if drift == "locator" and seen.count("locator") == 2:
            return replace(locator, storage_relative_path="case-1/qdkt/changed.docx")
        return locator

    monkeypatch.setattr(module, "read_qdkt_draft_provenance", source_reader)
    monkeypatch.setattr(module, "resolve_qdkt_draft_storage_locator", locator_reader)
    storage = FakeStorage(data)
    with pytest.raises(QdKtDraftStorageAuditBlocked, match="SOURCE_CHANGED"):
        audit_case_qdkt_draft_binary_readonly(
            SimpleNamespace(no_autoflush=nullcontext()), storage,
            case_id="case-1", snapshot=snapshot,
        )
    assert seen == ["source", "locator", "source", "locator"]
    assert storage.calls == [(locator.storage_relative_path, "inspection")]


def test_internal_audit_rechecks_unchanged_source_after_storage(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from backend.app.document.inspection_qd_kt_draft_storage_audit import (
        audit_case_qdkt_draft_binary_readonly,
    )
    from backend.app.document.inspection_qd_kt_team_snapshot_review import (
        DraftTeamSnapshot, TeamMemberAtDraft,
    )
    import backend.app.document.inspection_qd_kt_draft_storage_audit as module

    data, source, locator = fixture()
    calls = []
    monkeypatch.setattr(module, "read_qdkt_draft_provenance",
        lambda *args, **kwargs: calls.append("source") or source)
    monkeypatch.setattr(module, "resolve_qdkt_draft_storage_locator",
        lambda *args, **kwargs: calls.append("locator") or locator)
    snapshot = DraftTeamSnapshot("case-1", "draft-1", "version-1", "team-1", 2,
        (TeamMemberAtDraft("member-1", "Inspector", "LEADER", "Unverified"),))
    evidence = audit_case_qdkt_draft_binary_readonly(
        SimpleNamespace(no_autoflush=nullcontext()), FakeStorage(data),
        case_id="case-1", snapshot=snapshot,
    )
    assert calls == ["source", "locator", "source", "locator", "source", "locator"]
    assert evidence.actual_docx_bytes_verified
    assert not evidence.ready_to_render


def test_db_locator_query_refreshes_existing_identity_map_rows():
    from contextlib import nullcontext
    from types import SimpleNamespace
    from backend.app.document.inspection_qd_kt_draft_storage_audit import (
        resolve_qdkt_draft_storage_locator,
    )
    data, provenance, _ = fixture()
    seen = []
    class Session:
        no_autoflush = nullcontext()
        def execute(self, statement):
            seen.append(statement.get_execution_options().get("populate_existing"))
            return self
        def all(self):
            return [(
                SimpleNamespace(id="version-1", document_variant_id="variant-1",
                    storage_binding_id="binding-1", storage_root="inspection",
                    storage_relative_path="case-1/qdkt/draft.docx",
                    checksum_sha256=sha256(data).hexdigest()),
                SimpleNamespace(id="variant-1", document_id="document-1"),
                SimpleNamespace(id="document-1", case_id="case-1", family_code="INSPECTION_QD_KT"),
                SimpleNamespace(id="binding-1", case_id="case-1", relative_path="case-1"),
            )]
    resolve_qdkt_draft_storage_locator(Session(), provenance=provenance)
    assert seen == [True]


def test_internal_case_audit_detects_in_place_storage_replacement(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from backend.app.document.inspection_qd_kt_draft_storage_audit import (
        audit_case_qdkt_draft_binary_readonly,
    )
    from backend.app.document.inspection_qd_kt_team_snapshot_review import (
        DraftTeamSnapshot, TeamMemberAtDraft,
    )
    import backend.app.document.inspection_qd_kt_draft_storage_audit as module

    data, source, locator = fixture()
    monkeypatch.setattr(module, "read_qdkt_draft_provenance",
        lambda *args, **kwargs: source)
    monkeypatch.setattr(module, "resolve_qdkt_draft_storage_locator",
        lambda *args, **kwargs: locator)

    class ReplacedStorage(FakeStorage):
        @contextmanager
        def read_stream(self, path, *, root):
            self.calls.append((path, root))
            yield BytesIO(data if len(self.calls) == 1 else data + b"replaced")

    snapshot = DraftTeamSnapshot("case-1", "draft-1", "version-1", "team-1", 2,
        (TeamMemberAtDraft("member-1", "Inspector", "LEADER", "Unverified"),))
    storage = ReplacedStorage(data)
    with pytest.raises(ValueError, match="CHECKSUM_MISMATCH"):
        audit_case_qdkt_draft_binary_readonly(
            SimpleNamespace(no_autoflush=nullcontext()), storage,
            case_id="case-1", snapshot=snapshot,
        )
    assert storage.calls == [(locator.storage_relative_path, "inspection")] * 2


@pytest.mark.parametrize("drift", ["provenance", "locator"])
def test_internal_case_audit_blocks_drift_during_second_storage_read(monkeypatch, drift):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from backend.app.document.inspection_qd_kt_draft_storage_audit import (
        audit_case_qdkt_draft_binary_readonly,
    )
    from backend.app.document.inspection_qd_kt_team_snapshot_review import (
        DraftTeamSnapshot, TeamMemberAtDraft,
    )
    import backend.app.document.inspection_qd_kt_draft_storage_audit as module

    data, source, locator = fixture()
    calls = []
    def source_reader(session, *, case_id, snapshot):
        calls.append("source")
        if drift == "provenance" and calls.count("source") == 3:
            return replace(source, draft_id="changed-during-second-read")
        return source
    def locator_reader(session, *, provenance):
        calls.append("locator")
        if drift == "locator" and calls.count("locator") == 3:
            return replace(locator, storage_relative_path="case-1/qdkt/moved.docx")
        return locator
    monkeypatch.setattr(module, "read_qdkt_draft_provenance", source_reader)
    monkeypatch.setattr(module, "resolve_qdkt_draft_storage_locator", locator_reader)
    snapshot = DraftTeamSnapshot("case-1", "draft-1", "version-1", "team-1", 2,
        (TeamMemberAtDraft("member-1", "Inspector", "LEADER", "Unverified"),))
    storage = FakeStorage(data)
    with pytest.raises(QdKtDraftStorageAuditBlocked, match="SOURCE_CHANGED"):
        audit_case_qdkt_draft_binary_readonly(
            SimpleNamespace(no_autoflush=nullcontext()), storage,
            case_id="case-1", snapshot=snapshot,
        )
    assert calls == ["source", "locator"] * 3
    assert storage.calls == [(locator.storage_relative_path, "inspection")] * 2
