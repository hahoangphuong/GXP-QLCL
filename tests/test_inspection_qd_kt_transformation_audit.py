"""Provenance facts and source transforms never certify legal/Word equivalence."""
import json
from pathlib import Path

import pytest

from backend.app.document import inspection_qd_kt_provenance_gate as gate
from backend.app.document.inspection_qd_kt_vkn_authority import QdKtAuthorityBlocked, select_qdkt_vkn_authority
from backend.app.document.inspection_qd_kt_legacy_province_band import qdkt_vkn_from_source_province


@pytest.mark.parametrize("change", ["source_step", "format", "modern_owner", "flag"])
def test_inventory_metadata_drift_is_not_accepted(tmp_path, change):
    data = json.loads(gate.SOURCE.read_text(encoding="utf-8"))
    if change == "source_step":
        data["fields"]["Diachicoso"]["provenance_chain"][0]["steps"][0]["code"] = "UNVERIFIED source assignment"
    elif change == "format":
        data["fields"]["Fulldate"]["normalization_or_formatting"] = "server UTC now"
    elif change == "modern_owner":
        data["fields"]["NgaynopHsDK"]["modern_owner_candidate"] = "Case.created_at"
    else:
        data["invariants"]["runtime_contract_changed"] = True
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(gate.QdKtProvenanceGateBlocked):
        gate.inspect_qdkt_source_provenance(path)


def test_correlated_source_hash_edits_do_not_replace_the_primary_pin(tmp_path, monkeypatch):
    inventory = json.loads(gate.SOURCE.read_text(encoding="utf-8"))
    trace = json.loads(gate.TRACE.read_text(encoding="utf-8"))
    inventory["source_zip_sha256"] = trace["source_zip_sha256"] = "0" * 64
    path, trace_path = tmp_path / "inventory.json", tmp_path / "trace.json"
    path.write_text(json.dumps(inventory), encoding="utf-8")
    trace_path.write_text(json.dumps(trace), encoding="utf-8")
    monkeypatch.setattr(gate, "TRACE", trace_path)
    with pytest.raises(gate.QdKtProvenanceGateBlocked):
        gate.inspect_qdkt_source_provenance(path)


def test_duplicate_inventory_keys_do_not_use_last_value(tmp_path):
    data = gate.SOURCE.read_text(encoding="utf-8")
    data = data.replace('"fields": {', '"fields": {}, "fields": {', 1)
    path = tmp_path / "duplicate.json"
    path.write_text(data, encoding="utf-8")
    with pytest.raises(gate.QdKtProvenanceGateBlocked):
        gate.inspect_qdkt_source_provenance(path)


@pytest.mark.parametrize("value", [[], {"schema_version": "inspection-qd-kt-input-provenance/v1", "fields": []}])
def test_malformed_inventory_returns_owner_blocker(tmp_path, value):
    path = tmp_path / "malformed.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(gate.QdKtProvenanceGateBlocked):
        gate.inspect_qdkt_source_provenance(path)


def test_unknown_geography_enum_cannot_be_silently_ignored_for_vaccine():
    with pytest.raises(QdKtAuthorityBlocked):
        select_qdkt_vkn_authority(manufacture_kind="VACCINE_OR_BIOLOGICAL", geography="UNKNOWN_ENUM")


def test_malformed_reachability_returns_owner_blocker(tmp_path):
    data = json.loads(gate.SOURCE.read_text(encoding="utf-8"))
    data["fields"]["Fulldate"]["vba_rendered_operations"][0]["reachability_i2"] = []
    path = tmp_path / "malformed.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(gate.QdKtProvenanceGateBlocked):
        gate.inspect_qdkt_source_provenance(path)


@pytest.mark.parametrize("wrapper", [False, True])
def test_foreign_classification_cannot_masquerade_as_vaccine(wrapper):
    class ForgedClassification:
        def __eq__(self, other):
            return True
    with pytest.raises(QdKtAuthorityBlocked):
        if wrapper:
            qdkt_vkn_from_source_province(manufacture_kind=ForgedClassification(), registered_province=None)
        else:
            select_qdkt_vkn_authority(manufacture_kind=ForgedClassification(), geography="UNPROVEN")


def test_report_is_a_detached_snapshot_not_mutable_review_specifications():
    from backend.app.document.inspection_qd_kt_transformation_audit import build_qdkt_transformation_audit, transformation_audit_json
    report = build_qdkt_transformation_audit()
    expected = transformation_audit_json(report)
    row = report["fields"][0]
    try:
        row["owner_evidence_needed"].append("forged completion")
        assert transformation_audit_json(build_qdkt_transformation_audit()) == expected
    finally:
        row["owner_evidence_needed"].pop()


def test_all_14_fields_remain_unverified_and_have_complete_audit_dimensions():
    from backend.app.document.inspection_qd_kt_transformation_audit import build_qdkt_transformation_audit
    report = build_qdkt_transformation_audit()
    assert {r["logical_operation"] for r in report["fields"]} == gate.EXPECTED_FIELDS
    assert report["status_counts"] == {"VERIFIED": 0, "PARTIAL": 6, "BLOCKED": 4, "CONTRADICTED": 4}
    assert report["legacy_owner_counts"] == {"OWNER_BLOCKED": 8, "OWNER_PARTIAL": 6}
    for row in report["fields"]:
        assert row["status"] != "VERIFIED" and row["ready_to_render"] is False
        for name in ("legacy_source_expression", "legacy_transformation", "canonical_candidate", "ownership", "null_missing_behavior", "multiple_record_behavior", "date_time_handling", "differences", "evidence_refs", "blocker_codes", "owner_evidence_needed"):
            assert row[name] or (name == "legacy_source_expression" and row["operation_type"] == "DELETE")
        assert len(row["physical_targets"]) == 4
    assert report["decision"] == "UNDECIDED" and report["word_uat"] == "NOT_EXECUTED"
    assert report["ready_to_render"] is report["legal_equivalence_verified"] is False


def test_exact_absence_and_numbered_target_facts_are_not_conflated():
    from backend.app.document.inspection_qd_kt_transformation_audit import build_qdkt_transformation_audit
    fields = {r["logical_operation"]: r for r in build_qdkt_transformation_audit()["fields"]}
    for name in ("Fulldate", "Diachicoso", "HsDK", "NgaynopHsDK", "QDKT", "NgayQDKT"):
        assert all(r["candidate_targets"] == [name] and not r["effective_targets"] for r in fields[name]["physical_targets"])
    assert all(r["effective_targets"] == ["Tencoso1", "Tencoso2", "Tencoso3"] for r in fields["Tencoso"]["physical_targets"])
    assert all(r["effective_targets"] == ["TT1x", "TT2x"] for r in fields["TTx"]["physical_targets"])
    for row in fields["VKN"]["physical_targets"]:
        assert row["effective_targets"] == (["VKN1", "VKN2"] if row["gxp_type"] in ("GLP", "GMP") else [])
        assert "VKN" not in row["candidate_targets"]


@pytest.mark.parametrize("change", ["status", "ready", "missing", "duplicate", "format"])
def test_committed_report_cannot_self_promote(tmp_path, change):
    from backend.app.document.inspection_qd_kt_transformation_audit import build_qdkt_transformation_audit, validate_qdkt_transformation_report, QdKtTransformationAuditBlocked
    report = build_qdkt_transformation_audit()
    if change == "status": report["fields"][0]["status"] = "VERIFIED"
    elif change == "ready": report["ready_to_render"] = True
    elif change == "missing": report["fields"].pop()
    elif change == "duplicate": report["fields"][0] = report["fields"][1]
    else: report["fields"][0]["legacy_transformation"] = "unverified transformation"
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(QdKtTransformationAuditBlocked, match="QDKT_TRANSFORMATION_AUDIT_REPORT_DRIFT"):
        validate_qdkt_transformation_report(path)


@pytest.mark.parametrize("change", ["duplicate", "missing", "unknown_variant"])
def test_report_rejects_mutated_physical_observation(tmp_path, change):
    from backend.app.document.inspection_qd_kt_transformation_audit import OBSERVATION, build_qdkt_transformation_audit, QdKtTransformationAuditBlocked
    data = json.loads(OBSERVATION.read_text(encoding="utf-8"))
    if change == "duplicate": data["templates"][0]["bookmark_names"].append("TT1x")
    elif change == "missing": data["templates"][0]["bookmark_names"].remove("TT1x")
    else: data["templates"][0]["gxp_type"] = []
    path = tmp_path / "observation.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(QdKtTransformationAuditBlocked):
        build_qdkt_transformation_audit(observation_path=path)


def test_helper_body_change_does_not_become_proven_transform(tmp_path):
    from backend.app.document.inspection_qd_kt_transformation_audit import HELPERS, build_qdkt_transformation_audit, QdKtTransformationAuditBlocked
    data = json.loads(HELPERS.read_text(encoding="utf-8"))
    data["functions"]["Del_LastPeriod"]["source"] = ["invented trim-all punctuation"]
    path = tmp_path / "helpers.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(QdKtTransformationAuditBlocked, match="QDKT_AUDIT_HELPER_SOURCE_DRIFT"):
        build_qdkt_transformation_audit(helper_path=path)


def test_read_only_report_and_cli_do_not_call_clock_db_renderer_or_storage(monkeypatch):
    import io
    from sqlalchemy.orm import Session
    from backend.app.document import service
    from backend.app.document.inspection_qd_kt_transformation_audit import build_qdkt_transformation_audit, transformation_audit_json
    from tools.audit_qdkt_source_transformations import main
    def forbidden(*args, **kwargs):
        raise AssertionError("audit called a live side-effect boundary")
    for name in ("execute", "flush", "commit", "add", "delete"):
        monkeypatch.setattr(Session, name, forbidden)
    for name in vars(service):
        if "render" in name or "generate" in name: monkeypatch.setattr(service, name, forbidden)
    for name in ("read_stream", "write_stream", "copy", "move"):
        monkeypatch.setattr(service.LocalStorageService, name, forbidden)
    for name in ("write_text", "write_bytes", "mkdir", "unlink"):
        monkeypatch.setattr(Path, name, forbidden)
    report = build_qdkt_transformation_audit()
    assert transformation_audit_json(report) == transformation_audit_json(build_qdkt_transformation_audit())
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)
    assert main(["--format", "json"]) == 2
    assert json.loads(output.getvalue()) == report


def test_checked_in_json_and_markdown_are_reproducible():
    from backend.app.document.inspection_qd_kt_transformation_audit import REPORT, ROOT, validate_qdkt_transformation_report, transformation_audit_json, transformation_audit_markdown
    report = validate_qdkt_transformation_report()
    assert REPORT.read_text(encoding="utf-8") == transformation_audit_json(report)
    assert (ROOT / "docs/QDKT_14_BOOKMARK_TRANSFORMATION_AUDIT.md").read_text(encoding="utf-8") == transformation_audit_markdown(report)
