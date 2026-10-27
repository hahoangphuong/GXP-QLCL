"""Synthetic contract behavior is not legal approval or actual Word UAT."""
from dataclasses import replace
from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, CaseApplication, Company, Site
from backend.app.document.inspection_qd_kt_dotx_binary_audit import inspect_qdkt_dotx_binary
from backend.app.document.inspection_qd_kt_renderer_contract import (
    ApprovalRecord, BookmarkPlacement, DossierSnapshot, PhysicalTemplateEvidence,
    RendererDecision, SubmissionDateBlocked, SYNTHETIC_INPUT_SHA256, UAT_CHECKS,
    WordUatEvidence, assess_renderer_preflight, decision_digest, load_renderer_decision,
    normalize_submission_date, read_dossier_snapshot, word_uat_digest,
    inspect_renderer_candidates,
)
from backend.app.document.inspection_qd_kt_template_asset_contract import InspectionQdKtTemplateAsset
from backend.app.document import inspection_qd_kt_renderer_contract as contract_module


def source():
    case, site, application = (str(uuid4()) for _ in range(3))
    return DossierSnapshot(case, site, application, case, 1, "SYNTHETIC-001", datetime.fromisoformat("2026-01-02T00:30:00+07:00"), origin="PERSISTED_CASE_APPLICATION")


def fixture(tmp_path, option="DEPRECATE_WRITES", *, absent=False):
    decision = load_renderer_decision()
    templates, physical = [], []
    for t in decision.templates:
        bookmarks = "" if option == "DEPRECATE_WRITES" or absent else (
            '<w:bookmarkStart w:id="1" w:name="HsDK"/><w:bookmarkEnd w:id="1"/>'
            '<w:bookmarkStart w:id="2" w:name="NgaynopHsDK"/><w:bookmarkEnd w:id="2"/>'
        )
        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"/></Types>')
            archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p>' + bookmarks + '</w:p></w:body></w:document>')
        data = stream.getvalue()
        path = tmp_path / (t.gxp_type + ".dotx")
        path.write_bytes(data)
        checksum = sha256(data).hexdigest()
        audit = inspect_qdkt_dotx_binary(path, asset=InspectionQdKtTemplateAsset(t.gxp_type, path.name, "template", path.name, checksum))
        placements = tuple(BookmarkPlacement(bookmark=s.name, part=s.part_name, start_location=s.start_location, end_location=s.end_location, semantic_context="Synthetic proposed placement") for s in audit.bookmark_spans)
        templates.append(t.model_copy(update={"candidate_version": "synthetic-contract-test-v1", "candidate_sha256": checksum, "placements": placements}))
        # Test-only simulation of trusted primary-byte receipt: never persisted.
        physical.append(PhysicalTemplateEvidence(audit, "PRIMARY_CANDIDATE_BYTES"))
    decision = decision.model_copy(update={"decision": option, "submission_date_rule": "AWARE_RECORDED_OFFSET_DATE", "date_display_format": "DD/MM/YYYY", "templates": tuple(templates)})
    digest = decision_digest(decision)
    uat = tuple(WordUatEvidence(
        gxp_type=t.gxp_type, contract_sha256=digest, template_sha256=t.candidate_sha256,
        template_version=t.candidate_version, execution="MICROSOFT_WORD_DESKTOP", result="PASS",
        word_version="TEST-ONLY", tester_ref="SYNTHETIC-TESTER", executed_at="2026-01-03T12:00:00+00:00",
        output_sha256="e" * 64, synthetic_input_sha256=SYNTHETIC_INPUT_SHA256,
        screenshot_refs=("TEST-ONLY",), acceptance_checks=tuple(sorted(UAT_CHECKS)),
    ) for t in templates)
    ledger = {}
    for purpose, role in (("LEGAL_TEMPLATE", "LEGAL_OWNER"), ("DOSSIER_SEMANTICS", "BUSINESS_OWNER"), ("DATE_NORMALIZATION", "BUSINESS_OWNER"), ("DEPRECATE_WRITES", "LEGAL_OWNER"), ("WORD_UAT", "UAT_OWNER")):
        ledger[purpose] = ApprovalRecord(record_id=purpose, contract_sha256=digest, purpose=purpose, role=role,
            reviewer_ref="TEST-ONLY", evidence_ref="TEST-ONLY", approved_at="2026-01-03T13:00:00+00:00", disposition="APPROVED",
            subject_sha256=word_uat_digest(uat) if purpose == "WORD_UAT" else None)
    decision = decision.model_copy(update={"approval_record_ids": tuple(ledger)})
    snapshot = source()
    return dict(decision=decision, expected=snapshot, observed=snapshot, trusted_approvals=ledger, physical=tuple(physical), word_uat=uat)


def test_committed_contract_fails_closed_and_has_no_approval():
    result = assess_renderer_preflight(decision=load_renderer_decision(), expected=None, observed=None, trusted_approvals={})
    assert "QDKT_LEGAL_DECISION_UNDECIDED" in result.blockers
    assert "QDKT_LEGAL_TEMPLATE_UNAPPROVED" in result.blockers
    assert not result.contract_evidence_complete
    assert result.ready_to_render is False


@pytest.mark.parametrize("option", ["ADD_BOOKMARKS", "DEPRECATE_WRITES"])
def test_complete_simulated_contract_is_not_render_authorization(tmp_path, option):
    result = assess_renderer_preflight(**fixture(tmp_path, option))
    assert result.blockers == ()
    assert result.contract_evidence_complete
    assert result.ready_to_render is False
    with pytest.raises((AttributeError, TypeError)):
        result.ready_to_render = True


@pytest.mark.parametrize("field,value,code", [
    ("case_id", str(uuid4()), "QDKT_CANONICAL_IDENTITY_CONFLICT"),
    ("application_id", str(uuid4()), "QDKT_CANONICAL_IDENTITY_CONFLICT"),
    ("site_id", str(uuid4()), "QDKT_CANONICAL_IDENTITY_CONFLICT"),
    ("application_case_id", str(uuid4()), "QDKT_APPLICATION_CASE_IDENTITY_CONFLICT"),
    ("application_version", 2, "QDKT_APPLICATION_VERSION_STALE"),
    ("dossier_code", None, "QDKT_DOSSIER_CODE_MISSING"),
    ("dossier_code", "-", "QDKT_DOSSIER_CODE_MISSING"),
    ("dossier_code", "SYNTHETIC-CONFLICT", "QDKT_DOSSIER_VALUE_CONFLICT"),
    ("submitted_on", None, "QDKT_SUBMISSION_DATE_MISSING"),
    ("submitted_on", datetime(2026, 1, 2), "QDKT_NAIVE_TIMESTAMP_UNRESOLVED"),
    ("origin", "SYNTHETIC", "QDKT_SYNTHETIC_SOURCE_UNSUPPORTED"),
])
def test_canonical_provenance_negative_paths(tmp_path, field, value, code):
    inputs = fixture(tmp_path)
    inputs["observed"] = replace(inputs["observed"], **{field: value})
    result = assess_renderer_preflight(**inputs)
    assert code in result.blockers
    assert not result.contract_evidence_complete and not result.ready_to_render


def test_equal_instants_with_different_recorded_calendar_days_conflict(tmp_path):
    inputs = fixture(tmp_path)
    inputs["observed"] = replace(inputs["observed"], submitted_on=datetime.fromisoformat("2026-01-01T17:30:00+00:00"))
    assert inputs["expected"].submitted_on == inputs["observed"].submitted_on
    assert "QDKT_DOSSIER_VALUE_CONFLICT" in assess_renderer_preflight(**inputs).blockers


@pytest.mark.parametrize("purpose,code", [
    ("LEGAL_TEMPLATE", "QDKT_LEGAL_TEMPLATE_UNAPPROVED"),
    ("DATE_NORMALIZATION", "QDKT_DATE_NORMALIZATION_UNAPPROVED"),
    ("DEPRECATE_WRITES", "QDKT_LEGACY_WRITE_DEPRECATION_UNAPPROVED"),
])
def test_missing_trusted_owner_approval_is_never_approval(tmp_path, purpose, code):
    inputs = fixture(tmp_path)
    inputs["trusted_approvals"].pop(purpose)
    result = assess_renderer_preflight(**inputs)
    assert "QDKT_APPROVAL_NOT_IN_TRUSTED_LEDGER" in result.blockers
    assert code in result.blockers


def test_stale_approval_hash_and_rejected_disposition_fail(tmp_path):
    inputs = fixture(tmp_path)
    for key in ("LEGAL_TEMPLATE", "DOSSIER_SEMANTICS"):
        record = inputs["trusted_approvals"][key]
        inputs["trusted_approvals"][key] = record.model_copy(update={"contract_sha256": "f" * 64, "disposition": "REJECTED"})
    assert "QDKT_APPROVAL_REJECTED_OR_STALE" in assess_renderer_preflight(**inputs).blockers


def test_option_a_absent_bookmarks_and_missing_placements_block(tmp_path):
    result = assess_renderer_preflight(**fixture(tmp_path, "ADD_BOOKMARKS", absent=True))
    for kind in ("GLP", "GMP", "GMPbb", "GSP"):
        assert f"QDKT_BOOKMARK_PLACEMENT_UNAPPROVED:{kind}" in result.blockers
        assert f"QDKT_REQUIRED_BOOKMARK_ABSENT_OR_AMBIGUOUS:{kind}:HsDK" in result.blockers


def test_checksum_synthetic_evidence_and_duplicate_template_set_block(tmp_path):
    inputs = fixture(tmp_path)
    first = inputs["physical"][0]
    inputs["physical"] = (replace(first, origin="SYNTHETIC", audit=replace(first.audit, actual_sha256="0" * 64)),) + inputs["physical"][1:]
    result = assess_renderer_preflight(**inputs)
    assert "QDKT_SYNTHETIC_PHYSICAL_EVIDENCE:GLP" in result.blockers
    assert "QDKT_TEMPLATE_CHECKSUM_CONFLICT:GLP" in result.blockers
    inputs["physical"] = inputs["physical"] + (first,)
    assert "QDKT_PHYSICAL_TEMPLATE_SET_INCOMPLETE" in assess_renderer_preflight(**inputs).blockers


@pytest.mark.parametrize("update,code", [
    ({"execution": "NOT_EXECUTED", "result": "NOT_EXECUTED"}, "QDKT_WORD_UAT_NOT_EXECUTED_OR_FAILED:GLP"),
    ({"template_sha256": "0" * 64}, "QDKT_WORD_UAT_IDENTITY_CONFLICT:GLP"),
    ({"screenshot_refs": ()}, "QDKT_WORD_UAT_EVIDENCE_INCOMPLETE:GLP"),
    ({"synthetic_input_sha256": "1" * 64}, "QDKT_WORD_UAT_INPUT_CONFLICT:GLP"),
    ({"executed_at": "2026-01-03"}, "QDKT_WORD_UAT_TIME_INVALID:GLP"),
])
def test_word_uat_is_separate_and_bound_to_exact_candidate_and_evidence(tmp_path, update, code):
    inputs = fixture(tmp_path)
    inputs["word_uat"] = (inputs["word_uat"][0].model_copy(update=update),) + inputs["word_uat"][1:]
    result = assess_renderer_preflight(**inputs)
    assert code in result.blockers
    assert "QDKT_WORD_UAT_APPROVAL_SUBJECT_CONFLICT" in result.blockers


@pytest.mark.parametrize("value,rule,expected", [
    ("2026-01-02", "ISO_DATE_ONLY", date(2026, 1, 2)),
    (date(2024, 2, 29), "ISO_DATE_ONLY", date(2024, 2, 29)),
    ("2026-01-02T00:30:00+07:00", "AWARE_RECORDED_OFFSET_DATE", date(2026, 1, 2)),
    ("2026-01-01T17:30:00Z", "AWARE_RECORDED_OFFSET_DATE", date(2026, 1, 1)),
])
def test_normalization_only_preserves_explicit_calendar_day(value, rule, expected):
    assert normalize_submission_date(value, rule=rule) == expected


@pytest.mark.parametrize("value,rule", [
    (None, "ISO_DATE_ONLY"), ("2026-02-30", "ISO_DATE_ONLY"),
    ("02/01/2026", "ISO_DATE_ONLY"), ("2026-01-02", "UNDECIDED"),
    ("2026-01-02T00:00:00", "AWARE_RECORDED_OFFSET_DATE"),
    (datetime(2026, 1, 2), "AWARE_RECORDED_OFFSET_DATE"),
    ("2026-01-02T00:00:00Z", "ISO_DATE_ONLY"),
    ("2026-01-02T12:00:00+25:00", "AWARE_RECORDED_OFFSET_DATE"),
    ("2026-01-02T12:00:00+00:60", "AWARE_RECORDED_OFFSET_DATE"),
    (True, "ISO_DATE_ONLY"), ("2026-01-02T00:00:00Z", "GUESS_UTC"),
])
def test_ambiguous_or_unsupported_date_transform_is_rejected(value, rule):
    with pytest.raises(SubmissionDateBlocked):
        normalize_submission_date(value, rule=rule)


@pytest.mark.parametrize("extra", [{"approved": True}, {"ready_to_render": True}, {"ready_to_render": 0}, {"decision": "APPROVED"}])
def test_unexpected_approval_flags_and_activation_rejected(extra):
    payload = load_renderer_decision().model_dump(mode="json")
    payload.update(extra)
    with pytest.raises(ValidationError):
        RendererDecision.model_validate_json(json.dumps(payload))


def test_bypassed_model_validation_cannot_promote_preflight(tmp_path):
    inputs = fixture(tmp_path)
    inputs["decision"] = inputs["decision"].model_copy(update={"ready_to_render": True})
    result = assess_renderer_preflight(**inputs)
    assert result.blockers == ("QDKT_EVIDENCE_SCHEMA_INVALID",)
    assert result.ready_to_render is False


def test_candidate_reader_rejects_wrong_sha_before_physical_evidence(tmp_path):
    inputs = fixture(tmp_path, "ADD_BOOKMARKS")
    paths = {t.gxp_type: tmp_path / (t.gxp_type + ".dotx") for t in inputs["decision"].templates}
    assert len(inspect_renderer_candidates(inputs["decision"], paths=paths)) == 4
    paths["GMP"].write_bytes(b"modified candidate")
    with pytest.raises(ValueError, match="CHECKSUM_MISMATCH"):
        inspect_renderer_candidates(inputs["decision"], paths=paths)
    with pytest.raises(ValueError, match="SET_INCOMPLETE"):
        inspect_renderer_candidates(inputs["decision"], paths={})


def test_approved_placement_must_match_exact_span_location(tmp_path):
    inputs = fixture(tmp_path, "ADD_BOOKMARKS")
    first = inputs["decision"].templates[0]
    changed = first.model_copy(update={"placements": (first.placements[0].model_copy(update={"start_location": "/wrong"}), first.placements[1])})
    inputs["decision"] = inputs["decision"].model_copy(update={"templates": (changed,) + inputs["decision"].templates[1:]})
    result = assess_renderer_preflight(**inputs)
    assert "QDKT_BOOKMARK_PLACEMENT_CONFLICT:GLP:HsDK" in result.blockers
    assert "QDKT_APPROVAL_REJECTED_OR_STALE" in result.blockers


def test_option_b_cannot_silently_ignore_existing_targets(tmp_path):
    inputs = fixture(tmp_path, "ADD_BOOKMARKS")
    inputs["decision"] = inputs["decision"].model_copy(update={"decision": "DEPRECATE_WRITES"})
    result = assess_renderer_preflight(**inputs)
    assert "QDKT_DEPRECATED_BOOKMARK_STILL_PRESENT:GLP:HsDK" in result.blockers
    assert "QDKT_UNEXPECTED_BOOKMARK_PLACEMENT:GLP" in result.blockers


def test_trusted_record_cannot_use_wrong_role_or_blank_reviewer(tmp_path):
    inputs = fixture(tmp_path)
    original = inputs["trusted_approvals"]["LEGAL_TEMPLATE"]
    inputs["trusted_approvals"]["LEGAL_TEMPLATE"] = original.model_copy(update={"role": "BUSINESS_OWNER"})
    assert "QDKT_LEGAL_TEMPLATE_UNAPPROVED" in assess_renderer_preflight(**inputs).blockers
    inputs["trusted_approvals"]["LEGAL_TEMPLATE"] = original.model_copy(update={"reviewer_ref": " "})
    assert assess_renderer_preflight(**inputs).blockers == ("QDKT_EVIDENCE_SCHEMA_INVALID",)


def test_missing_or_invalid_primary_semantic_contract_stays_structured_and_blocked(tmp_path, monkeypatch):
    inputs = fixture(tmp_path)
    def unavailable():
        raise ValueError("source unavailable")
    monkeypatch.setattr(contract_module, "load_qdkt_dossier_bookmark_source_evidence", unavailable)
    result = assess_renderer_preflight(**inputs)
    assert "QDKT_SUBMISSION_SEMANTICS_UNVERIFIED" in result.blockers
    assert not result.contract_evidence_complete


def test_snapshot_without_explicit_persisted_source_origin_fails_closed(tmp_path):
    inputs = fixture(tmp_path)
    row = inputs["observed"]
    unproven = DossierSnapshot(row.case_id, row.site_id, row.application_id,
        row.application_case_id, row.application_version, row.dossier_code, row.submitted_on)
    inputs.update(expected=unproven, observed=unproven)
    result = assess_renderer_preflight(**inputs)
    assert not result.contract_evidence_complete


def test_dossier_reader_uses_persisted_owner_without_flushing_or_discarding_draft(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'dossier.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="SYNTHETIC")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="SYNTHETIC")
        session.add(site)
        session.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
        session.add(case)
        session.flush()
        app = CaseApplication(case_id=case.id, dossier_code="SYNTHETIC-DB", submitted_on=datetime(2026, 1, 2))
        session.add(app)
        session.commit()
        case_id, app_id = case.id, app.id
        app.dossier_code = "SYNTHETIC-UNSAVED-DRAFT"
        snapshot = read_dossier_snapshot(session, case_id=case_id)
        assert snapshot.dossier_code == "SYNTHETIC-DB"
        assert snapshot.application_id == app_id
        assert app.dossier_code == "SYNTHETIC-UNSAVED-DRAFT"
        assert app in session.dirty
        with pytest.raises(ValueError, match="OWNER_MISSING_OR_AMBIGUOUS"):
            read_dossier_snapshot(session, case_id=str(uuid4()))
        session.rollback()
    engine.dispose()


def test_schema_is_timestamp_with_timezone_not_other_date_only_tables():
    column = CaseApplication.__table__.c.submitted_on
    assert column.type.timezone is True
    source_text = Path("migrations/versions/7ad763833b09_initial_schema_runtime.py").read_text(encoding="utf-8")
    application_block = source_text.split("op.create_table('case_application',", 1)[1].split("op.create_table(", 1)[0]
    assert "sa.Column('submitted_on', sa.DateTime(timezone=True)" in application_block
