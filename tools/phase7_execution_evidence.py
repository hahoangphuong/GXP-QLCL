from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "artifacts" / "phase7" / "cutover_execution_checklist.template.json"


class Phase7ExecutionEvidenceError(RuntimeError):
    """Raised when an operational tool cannot use explicit external evidence."""


@dataclass(frozen=True)
class Phase7ExecutionEvidencePaths:
    evidence_dir: Path

    @property
    def checklist_path(self) -> Path:
        return self.evidence_dir / "cutover_execution_checklist.json"

    @property
    def readiness_json_path(self) -> Path:
        return self.evidence_dir / "cutover_readiness.json"

    @property
    def readiness_markdown_path(self) -> Path:
        return self.evidence_dir / "cutover_readiness.md"

    @property
    def checklist_summary_json_path(self) -> Path:
        return self.evidence_dir / "cutover_checklist_summary.json"

    @property
    def checklist_summary_markdown_path(self) -> Path:
        return self.evidence_dir / "cutover_checklist_summary.md"

    @property
    def operational_pack_json_path(self) -> Path:
        return self.evidence_dir / "cutover_operational_pack.json"

    @property
    def operational_pack_csv_path(self) -> Path:
        return self.evidence_dir / "cutover_operational_pack.csv"

    @property
    def operational_pack_markdown_path(self) -> Path:
        return self.evidence_dir / "cutover_operational_pack.md"

    @property
    def final_closeout_json_path(self) -> Path:
        return self.evidence_dir / "phase7_final_closeout.json"

    @property
    def final_closeout_markdown_path(self) -> Path:
        return self.evidence_dir / "phase7_final_closeout.md"


def resolve_execution_evidence_paths(evidence_dir: Path) -> Phase7ExecutionEvidencePaths:
    if not evidence_dir.is_absolute():
        raise Phase7ExecutionEvidenceError("Phase 7 execution evidence directory must be an absolute path.")
    resolved = evidence_dir.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise Phase7ExecutionEvidenceError(
            "Phase 7 execution evidence directory must be external to the immutable release tree."
        )
    return Phase7ExecutionEvidencePaths(evidence_dir=resolved)


def require_execution_evidence(evidence_dir: Path) -> Phase7ExecutionEvidencePaths:
    paths = resolve_execution_evidence_paths(evidence_dir)
    if not paths.evidence_dir.is_dir():
        raise Phase7ExecutionEvidenceError(
            f"Phase 7 execution evidence directory is missing: {paths.evidence_dir}"
        )
    if not paths.checklist_path.is_file():
        raise Phase7ExecutionEvidenceError(
            f"Phase 7 execution checklist is missing: {paths.checklist_path}. "
            "Initialize it with tools/init_phase7_execution.py."
        )
    return paths
