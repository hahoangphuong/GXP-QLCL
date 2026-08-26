from pathlib import Path
import json

from tools import build_phase7_cutover_readiness as readiness
from tools.validate_phase7_cutover_checklist import validate_rows


def test_validate_rows_accepts_known_statuses():
    errors = validate_rows(
        [
            {"item_id": "a", "status": "pass"},
            {"item_id": "b", "status": "blocked"},
            {"item_id": "c", "status": "pending"},
            {"item_id": "d", "status": "not_started"},
        ]
    )

    assert errors == []


def test_validate_rows_rejects_duplicate_ids_and_unknown_status():
    errors = validate_rows(
        [
            {"item_id": "dup", "status": "pass"},
            {"item_id": "dup", "status": "mystery"},
        ]
    )

    assert any("duplicate item_id: dup" in error for error in errors)
    assert any("dup: invalid status 'mystery'" in error for error in errors)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _patch_phase7_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(readiness, "PHASE3_PATH", tmp_path / "phase3r.json")
    monkeypatch.setattr(readiness, "PHASE4_PATH", tmp_path / "phase4.json")
    monkeypatch.setattr(readiness, "PHASE5_PATH", tmp_path / "phase5.json")
    monkeypatch.setattr(readiness, "PHASE6_PATH", tmp_path / "phase6.json")
    monkeypatch.setattr(readiness, "PHASE3P_PATH", tmp_path / "phase3p.json")
    monkeypatch.setattr(readiness, "PHASE3S_PATH", tmp_path / "phase3s.json")


def _write_valid_phase7_artifacts(tmp_path: Path, *, conflict_count: int = 0) -> None:
    _write_json(tmp_path / "phase3r.json", {"phase3_status": "closed"})
    _write_json(tmp_path / "phase4.json", {"phase4_status": "closed"})
    _write_json(tmp_path / "phase5.json", {"phase5_status": "closed"})
    _write_json(tmp_path / "phase6.json", {"phase6_status": "closed", "required_outstanding": []})
    _write_json(tmp_path / "phase3p.json", {"conflict_count": conflict_count, "manual_review_count": conflict_count})


def _write_valid_phase3s_summary(tmp_path: Path, *, phase3p_sha256: str, conflict_count: int) -> None:
    _write_json(
        tmp_path / "phase3s.json",
        {
            "overall_status": "ready",
            "resolved_count": conflict_count,
            "unresolved_count": 0,
            "source_conflict_count": conflict_count,
            "source_phase3p_sha256": phase3p_sha256,
            "action_counts": {"winner": 4, "no_winner": max(conflict_count - 4, 0)},
            "missing_conflict_keys": [],
            "extra_decision_keys": [],
            "validation_errors": [],
        },
    )


def test_build_readiness_blocks_when_phase3_artifact_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    (tmp_path / "phase3r.json").unlink()

    report = readiness.build_readiness()

    gate = report["gates"]["structured_data_baseline"]
    assert report["phase7_status"] == "blocked"
    assert gate["status"] == "blocked"
    assert "Phase 3 closeout artifact is missing" in gate["reason"]


def test_build_readiness_blocks_when_phase4_artifact_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    (tmp_path / "phase4.json").unlink()

    report = readiness.build_readiness()

    gate = report["gates"]["storage_contract_baseline"]
    assert gate["status"] == "blocked"
    assert "Phase 4 closeout artifact is missing" in gate["reason"]


def test_build_readiness_blocks_when_phase5_artifact_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    (tmp_path / "phase5.json").unlink()

    report = readiness.build_readiness()

    gate = report["gates"]["document_contract_baseline"]
    assert gate["status"] == "blocked"
    assert "Phase 5 closeout artifact is missing" in gate["reason"]


def test_build_readiness_blocks_when_phase6_artifact_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    (tmp_path / "phase6.json").unlink()

    report = readiness.build_readiness()

    gate = report["gates"]["desktop_private_share_validation"]
    assert gate["status"] == "blocked"
    assert "Phase 6 closeout artifact is missing" in gate["reason"]


def test_build_readiness_blocks_when_phase3p_artifact_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    (tmp_path / "phase3p.json").unlink()

    report = readiness.build_readiness()

    gate = report["gates"]["current_projection_conflicts"]
    assert gate["status"] == "blocked"
    assert "current projection conflict artifact is missing" in gate["reason"]


def test_build_readiness_blocks_when_artifact_json_is_invalid(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    (tmp_path / "phase3r.json").write_text("{invalid", encoding="utf-8")

    report = readiness.build_readiness()

    gate = report["gates"]["structured_data_baseline"]
    assert gate["status"] == "blocked"
    assert "invalid JSON" in gate["reason"]


def test_build_readiness_preserves_valid_existing_behavior(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    phase3p_sha256 = readiness.safe_load_json(tmp_path / "phase3p.json", "phase3p").payload_sha256 or ""
    _write_valid_phase3s_summary(tmp_path, phase3p_sha256=phase3p_sha256, conflict_count=0)

    report = readiness.build_readiness()

    assert report["phase7_status"] == "pending"
    assert report["gates"]["structured_data_baseline"]["status"] == "pass"
    assert report["gates"]["storage_contract_baseline"]["status"] == "pass"
    assert report["gates"]["document_contract_baseline"]["status"] == "pass"
    assert report["gates"]["desktop_private_share_validation"]["status"] == "pass"
    assert report["gates"]["current_projection_conflicts"]["status"] == "pass"


def test_build_readiness_blocks_when_phase3s_summary_is_stale_relative_to_phase3p(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path, conflict_count=14)
    _write_valid_phase3s_summary(tmp_path, phase3p_sha256="deadbeef", conflict_count=14)

    report = readiness.build_readiness()

    gate = report["gates"]["current_projection_conflicts"]
    assert gate["status"] == "blocked"
    assert "stale relative to the current Phase 3p artifact" in gate["reason"]


def test_build_readiness_passes_when_phase3s_summary_validates_all_conflicts(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path, conflict_count=14)
    phase3p_sha256 = readiness.safe_load_json(tmp_path / "phase3p.json", "phase3p").payload_sha256 or ""
    _write_valid_phase3s_summary(tmp_path, phase3p_sha256=phase3p_sha256, conflict_count=14)

    report = readiness.build_readiness()

    gate = report["gates"]["current_projection_conflicts"]
    assert gate["status"] == "pass"
    assert gate["detail"]["resolved_count"] == 14
