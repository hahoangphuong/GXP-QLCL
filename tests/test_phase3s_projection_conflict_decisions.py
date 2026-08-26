import json
from hashlib import sha256
from pathlib import Path

from tools import validate_phase3s_projection_conflict_decisions as phase3s


DECISION_PATH = Path("artifacts/phase3s/current_projection_conflict_decisions.template.json")
PHASE3P_PATH = Path("artifacts/phase3p/current_projection_conflicts.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_validate_decisions_accepts_well_formed_winner():
    phase3p_index = {
        "db.cc::GMP-1": {
            "candidate_legacy_ids": ["10", "11"],
            "projection_type": "current_certificate_projection",
            "source_sheet": "db.cc",
            "classification": "blank_ma_dc_non_case_backed_multi_current",
        }
    }
    errors = phase3s.validate_decisions(
        [
            {
                "conflict_key": "db.cc::GMP-1",
                "candidate_legacy_ids": ["10", "11"],
                "projection_type": "current_certificate_projection",
                "source_sheet": "db.cc",
                "classification": "blank_ma_dc_non_case_backed_multi_current",
                "decision_type": "winner",
                "decision_action": "winner",
                "selected_candidate_legacy_id": "10",
                "reviewer": "business_owner",
                "reviewed_on": "2026-08-16",
                "decision_status": "owner_approved",
                "decision_rationale": "Chosen by evidence.",
            }
        ],
        phase3p_index=phase3p_index,
    )

    assert errors == []


def test_validate_decisions_rejects_invalid_no_winner_payload():
    phase3p_index = {
        "db.ktra::GMP-1": {
            "candidate_legacy_ids": ["10", "11"],
            "projection_type": "current_case_projection",
            "source_sheet": "db.ktra",
            "classification": "completed_plus_pending_both_current",
        }
    }
    errors = phase3s.validate_decisions(
        [
            {
                "conflict_key": "db.ktra::GMP-1",
                "candidate_legacy_ids": ["10", "11"],
                "projection_type": "current_case_projection",
                "source_sheet": "db.ktra",
                "classification": "completed_plus_pending_both_current",
                "decision_type": "no_winner",
                "decision_action": "no_winner",
                "selected_candidate_legacy_id": None,
                "reviewer": "business_owner",
                "reviewed_on": "2026-08-16",
                "decision_status": "owner_approved",
                "decision_rationale": "No winner.",
            }
        ],
        phase3p_index=phase3p_index,
    )

    assert any("no_winner is only approved for db.cc conflicts" in error for error in errors)


def test_real_decision_contract_matches_owner_adjudications():
    payload = _load(DECISION_PATH)
    decisions = {row["conflict_key"]: row for row in payload["decisions"]}

    assert payload["source_conflict_count"] == 14
    assert payload["owner_approved_by"] == "business_owner"
    assert payload["owner_approved_on"] == "2026-08-16"

    expected_winners = {
        "db.ktra::GMP-103C": "1194",
        "db.ktra::GMP-310A": "1160",
        "db.ktra::GMP-52A": "1509",
        "db.ktra::GMP-75B": "1460",
    }
    for conflict_key, winner in expected_winners.items():
        assert decisions[conflict_key]["decision_type"] == "winner"
        assert decisions[conflict_key]["selected_candidate_legacy_id"] == winner

    no_winner_keys = {
        "db.cc::GMP-104",
        "db.cc::GMP-128",
        "db.cc::GMP-129",
        "db.cc::GMP-144",
        "db.cc::GMP-2",
        "db.cc::GMP-24",
        "db.cc::GMP-264",
        "db.cc::GMP-337",
        "db.cc::GMP-50",
        "db.cc::GMP-69",
    }
    assert {key for key, row in decisions.items() if row["decision_type"] == "no_winner"} == no_winner_keys


def test_real_decision_summary_reconciles_exact_phase3p_key_set():
    summary = phase3s.build_summary()

    assert summary["overall_status"] == "ready"
    assert summary["source_conflict_count"] == 14
    assert summary["decision_count"] == 14
    assert summary["resolved_count"] == 14
    assert summary["unresolved_count"] == 0
    assert summary["action_counts"] == {"no_winner": 10, "winner": 4}
    assert summary["missing_conflict_keys"] == []
    assert summary["extra_decision_keys"] == []
    assert summary["key_set_matches_phase3p"] is True
    assert summary["source_phase3p_sha256"] == sha256(PHASE3P_PATH.read_bytes()).hexdigest()


def test_build_summary_fails_closed_when_phase3p_sha_is_stale(tmp_path: Path):
    decision_payload = _load(DECISION_PATH)
    decision_payload["source_conflict_sha256"] = "deadbeef"
    decision_path = tmp_path / "decisions.json"
    decision_path.write_text(json.dumps(decision_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = phase3s.build_summary(decision_path=decision_path, phase3p_path=PHASE3P_PATH)

    assert summary["overall_status"] == "invalid"
    assert any("source_conflict_sha256 does not match actual Phase 3p artifact bytes" in error for error in summary["validation_errors"])


def test_build_summary_fails_closed_when_decision_is_missing(tmp_path: Path):
    decision_payload = _load(DECISION_PATH)
    decision_payload["decisions"] = decision_payload["decisions"][:-1]
    decision_path = tmp_path / "decisions.json"
    decision_path.write_text(json.dumps(decision_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = phase3s.build_summary(decision_path=decision_path, phase3p_path=PHASE3P_PATH)

    assert summary["overall_status"] == "invalid"
    assert summary["missing_conflict_keys"]


def test_build_summary_fails_closed_when_extra_decision_exists(tmp_path: Path):
    decision_payload = _load(DECISION_PATH)
    decision_payload["decisions"].append(
        {
            **decision_payload["decisions"][0],
            "conflict_key": "db.cc::GMP-extra",
        }
    )
    decision_path = tmp_path / "decisions.json"
    decision_path.write_text(json.dumps(decision_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = phase3s.build_summary(decision_path=decision_path, phase3p_path=PHASE3P_PATH)

    assert summary["overall_status"] == "invalid"
    assert summary["extra_decision_keys"] == ["db.cc::GMP-extra"]
