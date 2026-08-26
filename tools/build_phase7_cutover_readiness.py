from __future__ import annotations

import json
from hashlib import sha256
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PHASE3_PATH = ROOT / "artifacts" / "phase3r" / "phase3_final_closeout.json"
PHASE4_PATH = ROOT / "artifacts" / "phase4" / "phase4_final_closeout.json"
PHASE5_PATH = ROOT / "artifacts" / "phase5" / "phase5_final_closeout.json"
PHASE6_PATH = ROOT / "artifacts" / "phase6" / "phase6_final_closeout.json"
PHASE6_SUMMARY_PATH = ROOT / "artifacts" / "phase6" / "desktop_validation_summary.json"
PHASE3P_PATH = ROOT / "artifacts" / "phase3p" / "current_projection_conflicts.json"
PHASE3S_PATH = ROOT / "artifacts" / "phase3s" / "current_projection_conflict_decisions.summary.json"
OUT_DIR = ROOT / "artifacts" / "phase7"
JSON_OUT = OUT_DIR / "cutover_readiness.json"
MD_OUT = OUT_DIR / "cutover_readiness.md"


@dataclass(frozen=True)
class ArtifactLoadResult:
    path: Path
    artifact_label: str
    required: bool
    ok: bool
    payload_sha256: str | None = None
    payload: dict[str, Any] | None = None
    error_reason: str | None = None


def gate(status: str, reason: str, *, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "detail": detail or {},
    }


def safe_load_json(path: Path, artifact_label: str, *, required: bool = True) -> ArtifactLoadResult:
    if not path.exists():
        if required:
            return ArtifactLoadResult(
                path=path,
                artifact_label=artifact_label,
                required=required,
                ok=False,
                error_reason=f"Required {artifact_label} artifact is missing: {path}",
            )
        return ArtifactLoadResult(path=path, artifact_label=artifact_label, required=required, ok=False)

    try:
        payload_bytes = path.read_bytes()
        payload = json.loads(payload_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        return ArtifactLoadResult(
            path=path,
            artifact_label=artifact_label,
            required=required,
            ok=False,
            error_reason=f"Required {artifact_label} artifact is invalid JSON: {path}: {exc}",
        )
    except OSError as exc:
        return ArtifactLoadResult(
            path=path,
            artifact_label=artifact_label,
            required=required,
            ok=False,
            error_reason=f"Required {artifact_label} artifact could not be read: {path}: {exc}",
        )

    if not isinstance(payload, dict):
        return ArtifactLoadResult(
            path=path,
            artifact_label=artifact_label,
            required=required,
            ok=False,
            error_reason=f"Required {artifact_label} artifact must be a JSON object: {path}",
        )

    return ArtifactLoadResult(
        path=path,
        artifact_label=artifact_label,
        required=required,
        ok=True,
        payload_sha256=sha256(payload_bytes).hexdigest(),
        payload=payload,
    )


def _blocked_artifact_gate(reason: str) -> dict[str, Any]:
    return gate("blocked", reason)


def build_current_projection_gate(
    phase3p_result: ArtifactLoadResult,
    phase3s_result: ArtifactLoadResult,
) -> dict[str, Any]:
    if not phase3p_result.ok:
        return _blocked_artifact_gate(
            phase3p_result.error_reason or "Current projection conflict artifact is unavailable."
        )

    if phase3s_result.ok:
        phase3s = phase3s_result.payload or {}
        reported_phase3p_sha256 = str(phase3s.get("source_phase3p_sha256", "")).strip()
        actual_phase3p_sha256 = phase3p_result.payload_sha256 or ""
        if reported_phase3p_sha256 != actual_phase3p_sha256:
            return gate(
                "blocked",
                "Phase 3s adjudication summary is stale relative to the current Phase 3p artifact.",
                detail={
                    "reported_phase3p_sha256": reported_phase3p_sha256,
                    "actual_phase3p_sha256": actual_phase3p_sha256,
                },
            )
        unresolved_count = int(phase3s.get("unresolved_count", 0))
        overall_status = str(phase3s.get("overall_status", ""))
        if (
            overall_status == "ready"
            and unresolved_count == 0
            and not phase3s.get("validation_errors", [])
            and not phase3s.get("missing_conflict_keys", [])
            and not phase3s.get("extra_decision_keys", [])
            and int(phase3s.get("source_conflict_count", 0)) == int((phase3p_result.payload or {}).get("conflict_count", 0))
        ):
            return gate(
                "pass",
                "Current-projection conflicts were adjudicated in Phase 3s.",
                detail={
                    "resolved_count": phase3s.get("resolved_count", 0),
                    "winner_count": phase3s.get("action_counts", {}).get("winner", 0),
                    "no_winner_count": phase3s.get("action_counts", {}).get("no_winner", 0),
                },
            )
        return gate(
            "blocked",
            "Current-projection conflicts still require adjudication or have unresolved decisions in Phase 3s.",
            detail={
                "overall_status": overall_status,
                "unresolved_count": unresolved_count,
                "missing_conflict_keys": phase3s.get("missing_conflict_keys", []),
                "extra_decision_keys": phase3s.get("extra_decision_keys", []),
                "validation_errors": phase3s.get("validation_errors", []),
            },
        )

    if phase3s_result.error_reason is not None:
        return _blocked_artifact_gate(phase3s_result.error_reason)

    phase3p = phase3p_result.payload or {}
    conflict_count = int(phase3p.get("conflict_count", 0))
    return (
        gate("pass", "No current-projection conflicts remain.")
        if conflict_count == 0
        else gate(
            "blocked",
            "Current-projection conflicts still require adjudication outside the structured-import baseline.",
            detail={
                "conflict_count": conflict_count,
                "manual_review_count": phase3p.get("manual_review_count", 0),
            },
        )
    )


def _baseline_gate(
    result: ArtifactLoadResult,
    *,
    expected_key: str,
    pass_reason: str,
    blocked_reason: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not result.ok:
        return _blocked_artifact_gate(result.error_reason or f"{result.artifact_label} artifact is unavailable.")
    payload = result.payload or {}
    if payload.get(expected_key) == "closed":
        return gate("pass", pass_reason)
    return gate("blocked", blocked_reason, detail=detail or {})


def build_phase6_gate(
    phase6_result: ArtifactLoadResult,
    phase6_summary_result: ArtifactLoadResult,
) -> dict[str, Any]:
    if not phase6_result.ok:
        return _blocked_artifact_gate(
            phase6_result.error_reason or "Phase 6 closeout artifact is unavailable."
        )
    if not phase6_summary_result.ok:
        return _blocked_artifact_gate(
            phase6_summary_result.error_reason or "Phase 6 desktop validation summary is unavailable."
        )
    phase6 = phase6_result.payload or {}
    phase6_summary = phase6_summary_result.payload or {}
    reported_summary_sha256 = str(phase6.get("summary_sha256", "")).strip()
    actual_summary_sha256 = phase6_summary_result.payload_sha256 or ""
    if reported_summary_sha256 != actual_summary_sha256:
        return gate(
            "blocked",
            "Phase 6 closeout is stale relative to the current desktop validation summary.",
            detail={
                "reported_summary_sha256": reported_summary_sha256,
                "actual_summary_sha256": actual_summary_sha256,
            },
        )
    if (
        phase6.get("phase6_status") == "closed"
        and phase6_summary.get("overall_status") == "closed"
        and not phase6_summary.get("validation_errors", [])
        and not phase6_summary.get("required_outstanding", [])
    ):
        return gate(
            "pass",
            "Phase 6 desktop/private-share evidence is complete.",
            detail={"required_outstanding": []},
        )
    return gate(
        "blocked",
        "Phase 6 desktop/private-share evidence is not closed.",
        detail={"required_outstanding": phase6_summary.get("required_outstanding", [])},
    )


def build_readiness() -> dict[str, Any]:
    phase3 = safe_load_json(PHASE3_PATH, "Phase 3 closeout")
    phase4 = safe_load_json(PHASE4_PATH, "Phase 4 closeout")
    phase5 = safe_load_json(PHASE5_PATH, "Phase 5 closeout")
    phase6 = safe_load_json(PHASE6_PATH, "Phase 6 closeout")
    phase6_summary = safe_load_json(PHASE6_SUMMARY_PATH, "Phase 6 desktop validation summary")
    phase3p = safe_load_json(PHASE3P_PATH, "current projection conflict")
    phase3s = safe_load_json(PHASE3S_PATH, "Phase 3s projection conflict decision summary", required=False)

    gates: dict[str, dict[str, Any]] = {}
    gates["structured_data_baseline"] = _baseline_gate(
        phase3,
        expected_key="phase3_status",
        pass_reason="Phase 3 structured migration baseline is closed.",
        blocked_reason="Phase 3 structured migration baseline is not closed.",
    )
    gates["storage_contract_baseline"] = _baseline_gate(
        phase4,
        expected_key="phase4_status",
        pass_reason="Phase 4 storage contract/tooling baseline is closed.",
        blocked_reason="Phase 4 storage contract/tooling baseline is not closed.",
    )
    gates["document_contract_baseline"] = _baseline_gate(
        phase5,
        expected_key="phase5_status",
        pass_reason="Phase 5 document/runtime baseline is closed.",
        blocked_reason="Phase 5 document/runtime baseline is not closed.",
    )
    gates["desktop_private_share_validation"] = build_phase6_gate(phase6, phase6_summary)

    gates["current_projection_conflicts"] = build_current_projection_gate(phase3p, phase3s)

    gates["legacy_write_freeze_execution"] = gate(
        "pending",
        "Legacy write freeze cannot be executed until desktop/private-share evidence and cutover window approval are complete.",
    )
    gates["rollback_window_execution"] = gate(
        "pending",
        "Rollback execution remains pending until production cutover window is approved.",
    )

    statuses = [payload["status"] for payload in gates.values()]
    if any(status == "blocked" for status in statuses):
        overall_status = "blocked"
    elif any(status == "pending" for status in statuses):
        overall_status = "pending"
    else:
        overall_status = "ready"

    return {
        "generated_on": "2026-08-26",
        "phase7_status": overall_status,
        "gates": gates,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 7 Cutover Readiness",
        "",
        "Generated by `tools/build_phase7_cutover_readiness.py`.",
        "",
        f"- Overall cutover status: `{report['phase7_status']}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reason |",
        "|---|---|---|",
    ]
    for gate_name, payload in report["gates"].items():
        lines.append(f"| `{gate_name}` | `{payload['status']}` | {payload['reason']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_readiness()
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    MD_OUT.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
