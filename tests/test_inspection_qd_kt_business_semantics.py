from __future__ import annotations

from copy import deepcopy

import pytest

from tools.resolve_inspection_qd_kt_business_semantics import (
    EXPECTED_SOURCE_SHA256,
    build_business_semantics,
)


def _source_provenance() -> dict[str, object]:
    # Mirrors only the classification surface needed by this overlay contract.
    fields: dict[str, dict[str, object]] = {}
    blocked = {
        "Fulldate",
        "Diadiem",
        "Diadiemx",
        "Diachicoso",
        "QDKT",
        "NgayQDKT",
        "VKNx",
        "VKN",
    }
    names = [
        "Fulldate",
        "Tencoso",
        "Diadiem",
        "Diadiemx",
        "Diachicoso",
        "HsDK",
        "NgaynopHsDK",
        "QDKT",
        "NgayQDKT",
        "VKNx",
        "VKN",
        "TT3x",
        "TT3Del",
        "TTx",
    ]
    for name in names:
        fields[name] = {
            "source_semantic_endpoint": f"source:{name}",
            "owner_classification": "OWNER_BLOCKED" if name in blocked else "OWNER_PARTIAL",
            "blocker": f"legacy blocker:{name}",
        }
    return {
        "schema_version": "inspection-qd-kt-input-provenance/v1",
        "source_zip_sha256": EXPECTED_SOURCE_SHA256,
        "fields": fields,
    }


def test_user_confirmed_qdkt_composite_input_moves_only_qdkt_pair_to_partial():
    source = _source_provenance()
    before = deepcopy(source)

    report = build_business_semantics(source)

    assert source == before, "overlay must not mutate source-derived provenance"
    assert report["classification_counts"] == {
        "OWNER_PROVEN": 0,
        "OWNER_PARTIAL": 8,
        "OWNER_BLOCKED": 6,
    }
    assert report["decision"]["typed_qd_kt_input_contract"] == "BUSINESS_INPUT_CONTRACT_MISSING"
    assert report["decision"]["schema_change_authorized"] is False

    for field_name, meaning in {
        "QDKT": "QĐKT decision reference/number",
        "NgayQDKT": "QĐKT decision date",
    }.items():
        field = report["fields"][field_name]
        assert field["owner_classification"] == "OWNER_PARTIAL"
        evidence = field["business_semantic_evidence"]
        assert evidence["evidence_kind"] == "USER_CONFIRMED_BUSINESS_SEMANTICS"
        assert evidence["business_input_owner"] == "user-authored QĐKT composite text input"
        assert evidence["business_meaning"] == meaning
        assert evidence["composite_input_contains"] == ["QDKT", "NgayQDKT"]
        assert evidence["raw_preservation_candidate"] == "InspectionPlan.decision_document_hint"


def test_overlay_does_not_repurpose_inspection_outcome_decision_reference():
    report = build_business_semantics(_source_provenance())
    assert report["invariants"]["inspection_outcome_reused_as_qdkt_owner"] is False
    assert "InspectionOutcome.decision_reference" not in report["fields"]["QDKT"]["modern_owner_candidate"]


def test_overlay_rejects_wrong_legacy_source_lineage():
    source = _source_provenance()
    source["source_zip_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="unexpected legacy source SHA256"):
        build_business_semantics(source)


def test_overlay_fails_closed_when_qdkt_pair_is_missing():
    source = _source_provenance()
    del source["fields"]["NgayQDKT"]
    with pytest.raises(RuntimeError, match="source provenance missing field: NgayQDKT"):
        build_business_semantics(source)
