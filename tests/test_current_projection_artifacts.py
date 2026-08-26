import json
from hashlib import sha256
from pathlib import Path

import pytest

from tools import analyze_duplicate_current_keys as duplicate_current
from tools import build_phase3p_current_projection_conflicts as phase3p


SNAPSHOT_PATH = Path("artifacts/phase3c/legacy_snapshot.json")
DUPLICATE_ANALYSIS_PATH = Path("artifacts/legacy_audit/duplicate_current_analysis.json")
PHASE3P_PATH = Path("artifacts/phase3p/current_projection_conflicts.json")


def test_current_projection_artifacts_are_tracked_in_repository_checkout() -> None:
    assert SNAPSHOT_PATH.exists()
    assert DUPLICATE_ANALYSIS_PATH.exists()
    assert PHASE3P_PATH.exists()


def test_real_duplicate_current_analysis_is_reproducible_from_tracked_snapshot() -> None:
    tracked = json.loads(DUPLICATE_ANALYSIS_PATH.read_text(encoding="utf-8"))

    report = duplicate_current.build_report(snapshot_path=SNAPSHOT_PATH)

    assert report == tracked
    assert report["generated_from"]["snapshot_path"] == "artifacts/phase3c/legacy_snapshot.json"
    assert report["generated_from"]["snapshot_sha256"] == sha256(SNAPSHOT_PATH.read_bytes()).hexdigest()
    assert report["generated_from"]["analysis_strategy"] == "snapshot_only"
    assert report["db_cc"]["duplicate_group_count"] == 10
    assert report["db_ktra"]["duplicate_group_count"] == 4


def test_real_phase3p_conflicts_are_reproducible_from_tracked_duplicate_analysis() -> None:
    tracked = json.loads(PHASE3P_PATH.read_text(encoding="utf-8"))

    report = phase3p.build_summary(input_path=DUPLICATE_ANALYSIS_PATH)

    assert report == tracked
    assert report["input_sha256"] == sha256(DUPLICATE_ANALYSIS_PATH.read_bytes()).hexdigest()
    assert report["input_path"] == "artifacts/legacy_audit/duplicate_current_analysis.json"
    assert report["snapshot_path"] == "artifacts/phase3c/legacy_snapshot.json"
    assert report["snapshot_sha256"] == sha256(SNAPSHOT_PATH.read_bytes()).hexdigest()
    assert report["conflict_count"] == 14
    assert report["manual_review_count"] == 14
    assert report["resolution_policy_counts"] == {"manual_review_required": 14}


def test_duplicate_current_analysis_fails_closed_when_snapshot_is_missing(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Required legacy snapshot artifact is missing"):
        duplicate_current.build_report(snapshot_path=tmp_path / "missing_snapshot.json")


def test_phase3p_builder_fails_closed_when_duplicate_analysis_is_missing(tmp_path: Path) -> None:
    with pytest.raises(
        RuntimeError,
        match="Required duplicate-current analysis artifact is missing",
    ):
        phase3p.build_summary(input_path=tmp_path / "missing_duplicate_current_analysis.json")


def test_phase3p_builder_fails_closed_when_snapshot_provenance_mismatches(tmp_path: Path) -> None:
    analysis_path = tmp_path / "duplicate_current_analysis.json"
    analysis_path.write_text(
        json.dumps(
            {
                "generated_from": {
                    "snapshot_path": SNAPSHOT_PATH.as_posix(),
                    "snapshot_sha256": "deadbeef",
                    "analysis_strategy": "snapshot_only",
                },
                "db_cc": {"groups": [], "duplicate_group_count": 0, "classification_counts": {}},
                "db_ktra": {"groups": [], "duplicate_group_count": 0, "classification_counts": {}},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(RuntimeError, match="snapshot provenance mismatch"):
        phase3p.build_summary(input_path=analysis_path)
