from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "artifacts" / "phase16"
JSON_OUT = OUT_DIR / "storage_strategy_report.json"
MD_OUT = OUT_DIR / "storage_strategy_report.md"


@dataclass(frozen=True)
class Criterion:
    key: str
    label: str
    weight: int


CRITERIA = (
    Criterion("cloud_run_fit", "Cloud Run fit", 3),
    Criterion("initial_tailscale_fit", "Initial Tailscale fit", 3),
    Criterion("vpn_swap_isolation", "VPN swap isolation", 3),
    Criterion("storage_transport_replaceability", "Storage transport replaceability", 3),
    Criterion("current_repo_readiness", "Current repo readiness", 2),
    Criterion("operational_simplicity", "Operational simplicity", 2),
    Criterion("security_isolation", "Security isolation", 3),
    Criterion("desktop_workflow_compat", "Desktop workflow compatibility", 2),
)


OPTION_ASSESSMENTS: dict[str, dict[str, Any]] = {
    "nfs_volume": {
        "label": "Cloud Run direct NFS volume",
        "scores": {
            "cloud_run_fit": 4,
            "initial_tailscale_fit": 1,
            "vpn_swap_isolation": 2,
            "storage_transport_replaceability": 2,
            "current_repo_readiness": 4,
            "operational_simplicity": 3,
            "security_isolation": 2,
            "desktop_workflow_compat": 5,
        },
        "pros": [
            "Uses Cloud Run's native NFS volume feature, so the app can keep file-system style StorageService operations.",
            "Matches the current filesystem-backed adapter shape with minimal application-layer redesign.",
            "Can read and write legacy-style folders directly once private networking and permissions are correct.",
        ],
        "cons": [
            "Requires Synology or an equivalent bridge to expose an NFS endpoint reachable from Cloud Run over private networking.",
            "Cloud Run NFS volumes do not support locking, which is a meaningful limitation for Word/desktop-era file semantics.",
            "Cold start and startup success now depend on live NFS connectivity within Cloud Run mount time limits.",
        ],
        "evidence": [
            "Cloud Run supports mounting an on-premises NFS server as a volume.",
            "Cloud Run requires VPC connectivity for that NFS server.",
            "Cloud Run mounts NFS in no-lock mode.",
        ],
    },
    "external_bridge": {
        "label": "Private storage bridge outside Cloud Run",
        "scores": {
            "cloud_run_fit": 3,
            "initial_tailscale_fit": 5,
            "vpn_swap_isolation": 5,
            "storage_transport_replaceability": 5,
            "current_repo_readiness": 2,
            "operational_simplicity": 2,
            "security_isolation": 4,
            "desktop_workflow_compat": 5,
        },
        "pros": [
            "Preserves the approved rule that business code stays independent from the transport used to reach Synology.",
            "Fits the existing 'Tailscale first, future VPN swappable' requirement better because the bridge can absorb network changes.",
            "Avoids forcing Cloud Run itself to own low-level NAS mount and lock behavior.",
        ],
        "cons": [
            "Needs a new adapter/service that is not yet implemented in the repo.",
            "Introduces another deployable component with its own auth, availability, and observability needs.",
            "Requires explicit API and binary-stream contracts rather than reusing raw filesystem semantics end to end.",
        ],
        "evidence": [
            "Cloud Run cannot use SMB/Tailscale in-container mounts as the storage path.",
            "Direct VPC egress is recommended for Cloud Run when private network access is needed.",
            "Keeping storage transport behind a bridge best matches the existing architecture rule that StorageService hides infrastructure details.",
        ],
    },
}


def _weighted_total(scores: dict[str, int]) -> int:
    return sum(scores[item.key] * item.weight for item in CRITERIA)


def build_report() -> dict[str, Any]:
    options: dict[str, Any] = {}
    for key, assessment in OPTION_ASSESSMENTS.items():
        weighted_total = _weighted_total(assessment["scores"])
        options[key] = {
            "label": assessment["label"],
            "weighted_total": weighted_total,
            "scores": assessment["scores"],
            "pros": assessment["pros"],
            "cons": assessment["cons"],
            "evidence": assessment["evidence"],
        }

    ranked = sorted(options.items(), key=lambda item: item[1]["weighted_total"], reverse=True)
    recommended_key = ranked[0][0]
    return {
        "generated_on": "2026-08-20",
        "planning_recommendation": recommended_key,
        "current_direct_storage_baseline": "nfs_volume",
        "options": options,
        "ranking": [
            {"option": key, "weighted_total": payload["weighted_total"]}
            for key, payload in ranked
        ],
        "decision_notes": [
            "The repo can currently validate and bootstrap the direct NFS path more concretely than the bridge path.",
            "The bridge path better matches the long-term transport-swappability requirement and the original Tailscale-first constraint.",
            "Therefore the planning recommendation can differ from the currently most executable bootstrap shape.",
        ],
        "blocking_questions": [
            "Can Synology DS115j or a controlled intermediary expose an NFS export with acceptable security and permissions for Cloud Run?",
            "Is NFS no-lock behavior acceptable for every backend file-touching operation that will run inside Cloud Run?",
            "If not, where should the storage bridge live: office network, Compute Engine VM, or another private runtime?",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 16 Storage Strategy Report",
        "",
        f"- Generated on: `{report['generated_on']}`",
        f"- Planning recommendation: `{report['planning_recommendation']}`",
        f"- Current direct-storage baseline: `{report['current_direct_storage_baseline']}`",
        "",
        "## Ranking",
        "",
    ]
    for item in report["ranking"]:
        lines.append(f"- `{item['option']}` => `{item['weighted_total']}`")
    lines.extend(["", "## Option Detail", ""])
    for key, option in report["options"].items():
        lines.append(f"### {key}")
        lines.append("")
        lines.append(f"- Label: `{option['label']}`")
        lines.append(f"- Weighted total: `{option['weighted_total']}`")
        lines.append("- Scores:")
        for criterion in CRITERIA:
            lines.append(
                f"  - `{criterion.key}` = `{option['scores'][criterion.key]}` (weight `{criterion.weight}`)"
            )
        lines.append("- Pros:")
        for item in option["pros"]:
            lines.append(f"  - {item}")
        lines.append("- Cons:")
        for item in option["cons"]:
            lines.append(f"  - {item}")
        lines.append("- Evidence basis:")
        for item in option["evidence"]:
            lines.append(f"  - {item}")
        lines.append("")
    lines.extend(["## Decision Notes", ""])
    for item in report["decision_notes"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Blocking Questions", ""])
    for item in report["blocking_questions"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
