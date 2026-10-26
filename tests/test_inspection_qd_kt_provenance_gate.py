"""Source-backed offline guard; this is not a DOCX parity certification."""
from copy import deepcopy
import json

import pytest

from backend.app.document.inspection_qd_kt_provenance_gate import (
    SOURCE, QdKtProvenanceGateBlocked, inspect_qdkt_source_provenance,
)


def test_real_pinned_inventory_has_eight_blocked_and_six_partial():
    result = inspect_qdkt_source_provenance()
    assert len(result.blocked_fields) == 8
    assert len(result.partial_fields) == 6
    assert result.proven_fields == ()
    assert result.ready_for_typed_payload is False
    assert {"Diadiem", "Diachicoso", "QDKT", "NgayQDKT", "VKN", "VKNx"} <= set(result.blocked_fields)


def _mutated(tmp_path, mutate):
    content = json.loads(SOURCE.read_text(encoding="utf-8"))
    mutate(content)
    path = tmp_path / "modified.json"
    path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.parametrize("field", ["Diadiem", "Diachicoso", "QDKT", "NgayQDKT", "VKN", "VKNx"])
def test_unreviewed_owner_promotion_is_rejected(tmp_path, field):
    path = _mutated(tmp_path, lambda data: data["fields"][field].update(owner_classification="OWNER_PROVEN"))
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_OWNER_STATUS_REQUIRES_REVIEW"):
        inspect_qdkt_source_provenance(path)


def test_removing_or_renaming_a_physical_bookmark_is_rejected(tmp_path):
    path = _mutated(tmp_path, lambda data: data["fields"].pop("TTx"))
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_PHYSICAL_BOOKMARK_SET_CHANGED"):
        inspect_qdkt_source_provenance(path)


def test_missing_vba_source_semantics_is_rejected(tmp_path):
    path = _mutated(tmp_path, lambda data: data["fields"]["Diadiem"].update(source_semantic_endpoint=""))
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_SOURCE_PROVENANCE_INCOMPLETE"):
        inspect_qdkt_source_provenance(path)


def test_ambiguous_bookmark_metadata_is_rejected(tmp_path):
    path = _mutated(tmp_path, lambda data: data["fields"]["VKN"].update(physical_bookmark="TTx"))
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_SOURCE_PROVENANCE_INCOMPLETE"):
        inspect_qdkt_source_provenance(path)


@pytest.mark.parametrize("name", ["Fulldate", "QDKT", "TT3Del"])
def test_active_i2_operation_cannot_be_retagged_as_unreachable(tmp_path, name):
    def mutate(data):
        for operation in data["fields"][name]["vba_rendered_operations"]:
            if operation["reachability_i2"] != "UNREACHABLE_I2":
                operation["reachability_i2"] = "UNREACHABLE_I2"
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_I2_OPERATION_TRACE_CHANGED"):
        inspect_qdkt_source_provenance(_mutated(tmp_path, mutate))


def test_wrong_active_vba_line_is_rejected(tmp_path):
    def mutate(data):
        data["fields"]["Diadiem"]["vba_rendered_operations"][0]["line"] = 999
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_I2_OPERATION_TRACE_CHANGED"):
        inspect_qdkt_source_provenance(_mutated(tmp_path, mutate))


def test_delete_is_not_silently_promoted_to_write(tmp_path):
    def mutate(data):
        data["fields"]["TT3Del"]["vba_rendered_operations"][0]["operation_type"] = "WRITE"
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_I2_OPERATION_TRACE_CHANGED"):
        inspect_qdkt_source_provenance(_mutated(tmp_path, mutate))


def test_missing_source_variable_chain_is_rejected(tmp_path):
    def mutate(data):
        data["fields"]["VKN"]["provenance_chain"] = data["fields"]["VKN"]["provenance_chain"][:1]
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_I2_SOURCE_CHAIN_INCOMPLETE"):
        inspect_qdkt_source_provenance(_mutated(tmp_path, mutate))


def test_absent_active_expression_is_rejected(tmp_path):
    def mutate(data):
        data["fields"]["Tencoso"]["vba_rendered_operations"][0]["expression"] = ""
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_I2_OPERATION_TRACE_CHANGED"):
        inspect_qdkt_source_provenance(_mutated(tmp_path, mutate))


def test_delete_bookmark_may_have_no_value_expression(tmp_path):
    # Real TT3Del is a DELETE operation without a rendered value.
    inventory = inspect_qdkt_source_provenance()
    assert "TT3Del" in inventory.partial_fields
    def mutate(data):
        data["fields"]["TT3Del"]["vba_rendered_operations"][0]["expression"] = ""
    assert inspect_qdkt_source_provenance(_mutated(tmp_path, mutate)).ready_for_typed_payload is False


def test_inventory_expression_cannot_diverge_from_separate_vba_trace(tmp_path):
    def mutate(data):
        data["fields"]["Diachicoso"]["vba_rendered_operations"][0]["expression"] = "Site.site_address"
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_VBA_TRACE_MISMATCH"):
        inspect_qdkt_source_provenance(_mutated(tmp_path, mutate))


def test_inventory_branch_predicate_cannot_diverge_from_vba_trace(tmp_path):
    def mutate(data):
        data["fields"]["VKN"]["vba_rendered_operations"][0]["branch_predicates"] = "COMMON"
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_VBA_TRACE_MISMATCH"):
        inspect_qdkt_source_provenance(_mutated(tmp_path, mutate))


def test_inventory_call_chain_cannot_diverge_from_vba_trace(tmp_path):
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_VBA_TRACE_MISMATCH"):
        inspect_qdkt_source_provenance(
            _mutated(tmp_path, lambda data: data["call_chain"].reverse())
        )


def test_replaced_vba_trace_is_rejected_without_promoting_owner(tmp_path, monkeypatch):
    import backend.app.document.inspection_qd_kt_provenance_gate as gate
    trace = json.loads(gate.TRACE.read_text(encoding="utf-8"))
    trace["physical_bookmark_operations"] = [
        op for op in trace["physical_bookmark_operations"] if
        not (op["physical_bookmark"] == "QDKT" and op["reachability_i2"] == "REACHABLE_I2")
    ]
    trace_path = tmp_path / "modified-trace.json"
    trace_path.write_text(json.dumps(trace, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(gate, "TRACE", trace_path)
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_VBA_TRACE_MISMATCH"):
        inspect_qdkt_source_provenance()


def test_missing_vba_trace_fails_closed(tmp_path, monkeypatch):
    import backend.app.document.inspection_qd_kt_provenance_gate as gate
    monkeypatch.setattr(gate, "TRACE", tmp_path / "missing-trace.json")
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_VBA_TRACE_UNVERIFIED"):
        inspect_qdkt_source_provenance()
