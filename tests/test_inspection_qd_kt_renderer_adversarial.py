"""Adversarial Python inputs; no real approvals or actual Word UAT asserted."""
from dataclasses import replace
from datetime import datetime, tzinfo
from pathlib import Path
import builtins
from contextlib import contextmanager

import pytest

from test_inspection_qd_kt_renderer_contract import fixture
from backend.app.document.inspection_qd_kt_renderer_contract import (
    RendererDecision, RendererPreflightResult, assess_renderer_preflight,
    decision_digest, normalize_submission_date, SubmissionDateBlocked,
    word_uat_digest, inspect_renderer_candidates,
    read_dossier_snapshot,
)
from backend.app.document import inspection_qd_kt_renderer_contract as owner


def test_forged_physical_summary_cannot_establish_completeness(tmp_path):
    inputs = fixture(tmp_path)
    first = inputs["physical"][0]
    forged = replace(first.audit, bookmark_count=99, bookmark_names=("HsDK",))
    inputs["physical"] = (replace(first, audit=forged),) + inputs["physical"][1:]
    result = assess_renderer_preflight(**inputs)
    assert not result.contract_evidence_complete
    assert "QDKT_PHYSICAL_AUDIT_CONFLICT:GLP" in result.blockers


def test_audit_scalar_types_cannot_compare_equal_to_the_real_measurement(tmp_path):
    inputs = fixture(tmp_path)
    first = inputs["physical"][0]
    inputs["physical"] = (replace(first, audit=replace(first.audit, bookmark_count=0.0)),) + inputs["physical"][1:]
    assert not assess_renderer_preflight(**inputs).contract_evidence_complete


def test_undeclared_physical_approval_flag_is_not_ignored(tmp_path):
    inputs = fixture(tmp_path)
    object.__setattr__(inputs["physical"][0], "approved", True)
    assert not assess_renderer_preflight(**inputs).contract_evidence_complete


def test_impossible_approval_offset_is_not_normalized_into_evidence(tmp_path):
    inputs = fixture(tmp_path)
    record = inputs["trusted_approvals"]["LEGAL_TEMPLATE"]
    inputs["trusted_approvals"]["LEGAL_TEMPLATE"] = record.model_copy(update={"approved_at": "2026-01-03T13:00:00+00:60"})
    assert not assess_renderer_preflight(**inputs).contract_evidence_complete


def test_malformed_nested_physical_state_returns_blocker_not_exception(tmp_path):
    inputs = fixture(tmp_path)
    first = inputs["physical"][0]
    inputs["physical"] = (replace(first, audit=replace(first.audit, gxp_type=[])),) + inputs["physical"][1:]
    assert not assess_renderer_preflight(**inputs).contract_evidence_complete


def test_model_copy_undeclared_fields_cannot_disappear_during_serialization(tmp_path):
    inputs = fixture(tmp_path)
    inputs["decision"] = inputs["decision"].model_copy(update={"approved": True})
    assert not assess_renderer_preflight(**inputs).contract_evidence_complete


def test_model_construct_wrong_primitive_cannot_be_coerced_to_valid_json(tmp_path):
    inputs = fixture(tmp_path)
    record = inputs["trusted_approvals"]["LEGAL_TEMPLATE"]
    inputs["trusted_approvals"]["LEGAL_TEMPLATE"] = record.model_copy(update={
        "approved_at": datetime.fromisoformat(record.approved_at),
    })
    assert not assess_renderer_preflight(**inputs).contract_evidence_complete


def test_ambiguous_duplicate_approval_purpose_is_not_merged(tmp_path):
    inputs = fixture(tmp_path)
    record = inputs["trusted_approvals"]["LEGAL_TEMPLATE"]
    inputs["trusted_approvals"]["duplicate"] = record.model_copy(update={"record_id": "duplicate"})
    inputs["decision"] = inputs["decision"].model_copy(update={
        "approval_record_ids": inputs["decision"].approval_record_ids + ("duplicate",),
    })
    assert not assess_renderer_preflight(**inputs).contract_evidence_complete


def test_uat_approval_cannot_predate_execution(tmp_path):
    inputs = fixture(tmp_path)
    record = inputs["trusted_approvals"]["WORD_UAT"]
    inputs["trusted_approvals"]["WORD_UAT"] = record.model_copy(update={"approved_at": "2025-01-01T00:00:00Z"})
    assert not assess_renderer_preflight(**inputs).contract_evidence_complete


def test_non_uat_approval_cannot_carry_unchecked_subject_digest(tmp_path):
    inputs = fixture(tmp_path)
    record = inputs["trusted_approvals"]["LEGAL_TEMPLATE"]
    inputs["trusted_approvals"]["LEGAL_TEMPLATE"] = record.model_copy(update={"subject_sha256": "0" * 64})
    assert not assess_renderer_preflight(**inputs).contract_evidence_complete


def test_malformed_dossier_timestamp_returns_structured_blocker(tmp_path):
    class BrokenZone(tzinfo):
        def utcoffset(self, dt):
            raise RuntimeError("untrusted callback executed")
    inputs = fixture(tmp_path)
    inputs["observed"] = replace(inputs["observed"], submitted_on=datetime(2026, 1, 2, tzinfo=BrokenZone()))
    assert not assess_renderer_preflight(**inputs).contract_evidence_complete


@pytest.mark.parametrize("field", ["physical", "word_uat", "trusted_approvals"])
def test_invalid_outer_container_is_blocked(tmp_path, field):
    inputs = fixture(tmp_path)
    inputs[field] = None
    assert not assess_renderer_preflight(**inputs).contract_evidence_complete


def test_digest_entrypoint_revalidates_constructed_models(tmp_path):
    inputs = fixture(tmp_path)
    with pytest.raises(ValueError):
        decision_digest(inputs["decision"].model_copy(update={"ready_to_render": True}))


def test_result_cannot_claim_complete_with_blockers():
    with pytest.raises(ValueError):
        RendererPreflightResult(("BLOCKED",), True)


def test_no_physical_bytes_means_no_primary_proof(tmp_path):
    inputs = fixture(tmp_path)
    inputs["physical"] = tuple(replace(row, candidate_bytes=None) for row in inputs["physical"])
    result = assess_renderer_preflight(**inputs)
    assert "QDKT_PHYSICAL_BYTES_UNBOUND:GLP" in result.blockers
    assert not result.contract_evidence_complete


def test_modified_candidate_bytes_cannot_reuse_old_hash_and_spans(tmp_path):
    inputs = fixture(tmp_path, "ADD_BOOKMARKS")
    first = inputs["physical"][0]
    inputs["physical"] = (replace(first, candidate_bytes=b"substituted bytes"),) + inputs["physical"][1:]
    result = assess_renderer_preflight(**inputs)
    assert result.blockers == ("QDKT_PHYSICAL_EVIDENCE_INVALID",)


def test_synthetic_bytes_with_consistent_audit_still_cannot_claim_primary_origin(tmp_path):
    inputs = fixture(tmp_path)
    inputs["physical"] = tuple(replace(row, origin="SYNTHETIC") for row in inputs["physical"])
    result = assess_renderer_preflight(**inputs)
    assert "QDKT_SYNTHETIC_PHYSICAL_EVIDENCE:GLP" in result.blockers
    assert not result.contract_evidence_complete


@pytest.mark.parametrize("origin", ["UNVERIFIED", "SYNTHETIC"])
def test_uat_origin_cannot_be_replaced_by_pass_flag_even_with_simulated_acceptance(tmp_path, origin):
    inputs = fixture(tmp_path)
    inputs["word_uat"] = tuple(row.model_copy(update={"evidence_origin": origin}) for row in inputs["word_uat"])
    record = inputs["trusted_approvals"]["WORD_UAT"]
    inputs["trusted_approvals"]["WORD_UAT"] = record.model_copy(update={"subject_sha256": word_uat_digest(inputs["word_uat"])})
    result = assess_renderer_preflight(**inputs)
    assert "QDKT_WORD_UAT_ORIGIN_UNVERIFIED:GLP" in result.blockers
    assert not result.contract_evidence_complete


def test_duplicate_uat_cannot_replace_missing_gxp_variant(tmp_path):
    inputs = fixture(tmp_path)
    inputs["word_uat"] = (inputs["word_uat"][0],) * 4
    record = inputs["trusted_approvals"]["WORD_UAT"]
    inputs["trusted_approvals"]["WORD_UAT"] = record.model_copy(update={"subject_sha256": word_uat_digest(inputs["word_uat"])})
    assert "QDKT_WORD_UAT_SET_INCOMPLETE" in assess_renderer_preflight(**inputs).blockers


def test_foreign_python_object_serializer_is_never_invoked(tmp_path):
    calls = []
    class Foreign:
        def model_dump_json(self):
            calls.append("serializer")
            return "{}"
    inputs = fixture(tmp_path)
    inputs["decision"] = Foreign()
    assert assess_renderer_preflight(**inputs).blockers == ("QDKT_EVIDENCE_SCHEMA_INVALID",)
    assert calls == []


def test_subclassed_models_and_cyclic_constructed_state_are_blocked(tmp_path):
    class ForeignDecision(RendererDecision):
        pass
    inputs = fixture(tmp_path)
    inputs["decision"] = ForeignDecision.model_construct(**inputs["decision"].__dict__)
    assert assess_renderer_preflight(**inputs).blockers == ("QDKT_EVIDENCE_SCHEMA_INVALID",)
    inputs = fixture(tmp_path)
    cyclic = []
    cyclic.append(cyclic)
    inputs["decision"] = inputs["decision"].model_copy(update={"templates": cyclic})
    assert assess_renderer_preflight(**inputs).blockers == ("QDKT_EVIDENCE_SCHEMA_INVALID",)


def test_direct_normalizer_does_not_execute_foreign_equality_callback():
    class Foreign:
        def __eq__(self, other):
            raise AssertionError("foreign equality invoked")
    with pytest.raises(SubmissionDateBlocked):
        normalize_submission_date(Foreign(), rule="ISO_DATE_ONLY")


def test_preflight_is_read_only_and_does_not_reopen_changed_candidate_paths(tmp_path, monkeypatch):
    inputs = fixture(tmp_path)
    semantics = owner.load_qdkt_dossier_bookmark_source_evidence()
    assets = owner.load_inspection_qd_kt_template_assets()
    for path in tmp_path.glob("*.dotx"):
        path.write_bytes(b"later path substitution")
    calls = []
    def prohibited(*args, **kwargs):
        calls.append("side effect")
        raise AssertionError("preflight invoked filesystem/DB/render boundary")
    from sqlalchemy.orm import Session
    from backend.app.document import service as document_service
    for method in ("flush", "commit", "add", "delete", "execute"):
        monkeypatch.setattr(Session, method, prohibited)
    for name in vars(document_service):
        if "render" in name or "generate" in name:
            monkeypatch.setattr(document_service, name, prohibited)
    monkeypatch.setattr(document_service.LocalStorageService, "write_stream", prohibited)
    monkeypatch.setattr(document_service.LocalStorageService, "read_stream", prohibited)
    monkeypatch.setattr(owner, "load_qdkt_dossier_bookmark_source_evidence", lambda: semantics)
    monkeypatch.setattr(owner, "load_inspection_qd_kt_template_assets", lambda: assets)
    monkeypatch.setattr(Path, "open", prohibited)
    monkeypatch.setattr(Path, "write_bytes", prohibited)
    monkeypatch.setattr(Path, "write_text", prohibited)
    monkeypatch.setattr(builtins, "open", prohibited)
    result = assess_renderer_preflight(**inputs)
    assert result.contract_evidence_complete  # in-memory test receipts only
    assert result.ready_to_render is False
    assert calls == []


def test_candidate_acquisition_hashes_and_parses_one_read(tmp_path, monkeypatch):
    inputs = fixture(tmp_path)
    paths = {row.gxp_type: tmp_path / (row.gxp_type + ".dotx") for row in inputs["decision"].templates}
    counts = {}
    original_open = Path.open
    def single_open(path, *args, **kwargs):
        counts[path] = counts.get(path, 0) + 1
        assert counts[path] == 1
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", single_open)
    results = inspect_renderer_candidates(inputs["decision"], paths=paths)
    assert len(results) == 4
    assert all(row.candidate_bytes for row in results)
    assert set(counts.values()) == {1}


def test_reader_executes_only_one_select_without_flush_commit_or_mutation(tmp_path):
    inputs = fixture(tmp_path)
    snapshot = inputs["observed"]
    calls = []
    class ReadOnlySession:
        @property
        @contextmanager
        def no_autoflush(self):
            calls.append("no_autoflush")
            yield
        def execute(self, statement):
            assert statement.is_select
            calls.append("select")
            return self
        def all(self):
            return [(snapshot.case_id, snapshot.site_id, snapshot.application_id,
                     snapshot.application_case_id, snapshot.application_version,
                     snapshot.dossier_code, snapshot.submitted_on)]
        def flush(self):
            raise AssertionError("flush")
        def commit(self):
            raise AssertionError("commit")
        def add(self, obj):
            raise AssertionError("add")
    assert read_dossier_snapshot(ReadOnlySession(), case_id=snapshot.case_id) == snapshot
    assert calls == ["no_autoflush", "select"]


def test_preflight_uses_one_validated_manifest_snapshot(tmp_path, monkeypatch):
    inputs = fixture(tmp_path)
    assets = owner.load_inspection_qd_kt_template_assets()
    calls = []
    def read_once():
        calls.append("manifest")
        if len(calls) > 1:
            raise ValueError("manifest changed during assessment")
        return assets
    monkeypatch.setattr(owner, "load_inspection_qd_kt_template_assets", read_once)
    result = assess_renderer_preflight(**inputs)
    assert result.contract_evidence_complete
    assert result.ready_to_render is False
    assert calls == ["manifest"]
