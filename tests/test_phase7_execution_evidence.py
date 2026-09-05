from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import build_phase7_cutover_readiness as readiness
from tools import build_phase7_final_closeout as final_closeout
from tools import build_phase7b_operational_pack as operational_pack
from tools import init_phase7_execution as initializer
from tools import validate_phase7_cutover_checklist as checklist_validator
from tools.phase7_execution_evidence import (
    TEMPLATE_PATH,
    Phase7ExecutionEvidenceError,
    require_execution_evidence,
    resolve_execution_evidence_paths,
)
from tools.validate_phase7_cutover_checklist import AUTHORITATIVE_ITEM_IDS


def _initialize(tmp_path: Path, name: str = "evidence") -> Path:
    evidence_dir = (tmp_path / name).resolve()
    assert initializer.main(["--output-dir", str(evidence_dir)]) == 0
    return evidence_dir


def test_initializer_copies_template_without_mutating_it_and_refuses_overwrite(tmp_path: Path) -> None:
    template_bytes = TEMPLATE_PATH.read_bytes()
    evidence_dir = _initialize(tmp_path)
    checklist_path = evidence_dir / "cutover_execution_checklist.json"

    assert checklist_path.read_bytes() == template_bytes
    assert TEMPLATE_PATH.read_bytes() == template_bytes
    assert initializer.main(["--output-dir", str(evidence_dir)]) == 1


def test_external_checklist_preserves_current_rows_and_authoritative_ids(tmp_path: Path) -> None:
    evidence_dir = _initialize(tmp_path)
    template_items = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))["items"]
    execution_items = json.loads((evidence_dir / "cutover_execution_checklist.json").read_text(encoding="utf-8"))["items"]

    assert execution_items == template_items
    assert {row["item_id"] for row in execution_items} == AUTHORITATIVE_ITEM_IDS


def test_evidence_dir_must_be_external_and_missing_or_malformed_checklist_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(Phase7ExecutionEvidenceError):
        resolve_execution_evidence_paths(Path("relative-evidence"))

    with pytest.raises(Phase7ExecutionEvidenceError):
        require_execution_evidence((Path(__file__).resolve().parents[1] / "artifacts" / "phase7").resolve())

    evidence_dir = (tmp_path / "missing").resolve()
    with pytest.raises(Phase7ExecutionEvidenceError):
        require_execution_evidence(evidence_dir)

    evidence_dir.mkdir()
    checklist_path = evidence_dir / "cutover_execution_checklist.json"
    checklist_path.write_text("{invalid", encoding="utf-8")
    assert checklist_validator.main(["--evidence-dir", str(evidence_dir)]) == 1

    non_directory = (tmp_path / "not-a-directory").resolve()
    non_directory.write_text("not a directory", encoding="utf-8")
    assert initializer.main(["--output-dir", str(non_directory)]) == 1


def test_final_closeout_requires_operational_pack_from_the_same_evidence_dir(tmp_path: Path) -> None:
    evidence_dir = _initialize(tmp_path)

    assert readiness.main(["--evidence-dir", str(evidence_dir)]) == 0
    assert checklist_validator.main(["--evidence-dir", str(evidence_dir)]) == 0
    assert final_closeout.main(["--evidence-dir", str(evidence_dir)]) == 1
    assert not (evidence_dir / "phase7_final_closeout.json").exists()


def test_two_execution_directories_are_isolated_and_template_changes_do_not_reset_evidence(tmp_path: Path) -> None:
    first = _initialize(tmp_path, "first")
    second = _initialize(tmp_path, "second")
    first_checklist = first / "cutover_execution_checklist.json"
    first_payload = json.loads(first_checklist.read_text(encoding="utf-8"))
    first_payload["items"][0]["status"] = "blocked"
    first_checklist.write_text(json.dumps(first_payload), encoding="utf-8")

    assert json.loads((second / "cutover_execution_checklist.json").read_text(encoding="utf-8"))["items"][0]["status"] != "blocked"
    assert json.loads(first_checklist.read_text(encoding="utf-8"))["items"][0]["status"] == "blocked"


def test_all_operational_outputs_are_written_only_to_external_evidence_dir(tmp_path: Path) -> None:
    evidence_dir = _initialize(tmp_path)
    template_bytes = TEMPLATE_PATH.read_bytes()

    assert readiness.main(["--evidence-dir", str(evidence_dir)]) == 0
    assert checklist_validator.main(["--evidence-dir", str(evidence_dir)]) == 0
    assert operational_pack.main(["--evidence-dir", str(evidence_dir)]) == 0
    assert final_closeout.main(["--evidence-dir", str(evidence_dir)]) == 0

    expected = {
        "cutover_execution_checklist.json",
        "cutover_readiness.json",
        "cutover_readiness.md",
        "cutover_checklist_summary.json",
        "cutover_checklist_summary.md",
        "cutover_operational_pack.json",
        "cutover_operational_pack.csv",
        "cutover_operational_pack.md",
        "phase7_final_closeout.json",
        "phase7_final_closeout.md",
    }
    assert expected <= {path.name for path in evidence_dir.iterdir()}
    assert TEMPLATE_PATH.read_bytes() == template_bytes
