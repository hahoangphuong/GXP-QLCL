from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_REGISTRY_PATH = ROOT / "artifacts/phase5/payload_builder_registry.json"
TEMPLATE_AUDIT_PATH = ROOT / "artifacts/phase5/template_compatibility_audit.json"
OUTPUT_JSON = ROOT / "artifacts/phase5/template_contract_reconciled.json"
OUTPUT_MD = ROOT / "artifacts/phase5/template_contract_reconciled.md"


@dataclass(frozen=True)
class FieldResolution:
    field_name: str
    resolution_type: str
    target_bookmarks: tuple[str, ...]
    evidence: str


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def bookmark_signature(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def numbered_variant_prefix(value: str) -> str:
    prefix = value
    while prefix and prefix[-1].isdigit():
        prefix = prefix[:-1]
    return prefix


def build_payload_index(payload_registry: dict) -> dict[str, dict]:
    return {
        item["family_code"]: item
        for item in payload_registry["payload_builders"]
    }


def resolve_field(field_name: str, actual_bookmarks: list[str]) -> FieldResolution:
    actual_set = set(actual_bookmarks)
    if field_name in actual_set:
        return FieldResolution(
            field_name=field_name,
            resolution_type="exact",
            target_bookmarks=(field_name,),
            evidence="Exact bookmark name present in real template.",
        )

    lower_matches = sorted(
        [bookmark for bookmark in actual_bookmarks if bookmark.lower() == field_name.lower()],
        key=str.lower,
    )
    if lower_matches:
        return FieldResolution(
            field_name=field_name,
            resolution_type="case_insensitive_exact",
            target_bookmarks=tuple(lower_matches),
            evidence="Only case differs between payload registry and real template bookmark.",
        )

    expected_signature = bookmark_signature(field_name)
    signature_matches = sorted(
        [
            bookmark
            for bookmark in actual_bookmarks
            if bookmark_signature(bookmark) == expected_signature
        ],
        key=str.lower,
    )
    if signature_matches:
        return FieldResolution(
            field_name=field_name,
            resolution_type="signature_exact",
            target_bookmarks=tuple(signature_matches),
            evidence="Bookmark matches after removing punctuation differences.",
        )

    variant_prefix = numbered_variant_prefix(field_name)
    if len(bookmark_signature(variant_prefix)) >= 5:
        prefix_matches = sorted(
            [
                bookmark
                for bookmark in actual_bookmarks
                if bookmark.lower().startswith(variant_prefix.lower())
            ],
            key=str.lower,
        )
        if prefix_matches:
            return FieldResolution(
                field_name=field_name,
                resolution_type="prefix_variant_group",
                target_bookmarks=tuple(prefix_matches),
                evidence="Real template exposes numbered or suffixed variants sharing the same bookmark stem.",
            )

    return FieldResolution(
        field_name=field_name,
        resolution_type="unresolved",
        target_bookmarks=(),
        evidence="No safe automatic reconciliation from curated payload field to real template bookmark.",
    )


def build_reconciliation() -> dict:
    payload_registry = load_json(PAYLOAD_REGISTRY_PATH)
    audit = load_json(TEMPLATE_AUDIT_PATH)
    payload_index = build_payload_index(payload_registry)

    families: list[dict] = []
    for family in audit["family_reports"]:
        payload_entry = payload_index.get(family["family_code"])
        payload_fields = []
        if payload_entry is not None:
            payload_fields = [field["field_name"] for field in payload_entry["fields"]]
        actual_bookmarks = sorted(
            {
                bookmark
                for matched_file in family["matched_files"]
                for bookmark in matched_file["bookmarks"]
            },
            key=str.lower,
        )
        resolutions = [resolve_field(field_name, actual_bookmarks) for field_name in payload_fields]
        resolved_targets = {
            bookmark
            for resolution in resolutions
            for bookmark in resolution.target_bookmarks
        }
        unresolved_fields = [resolution.field_name for resolution in resolutions if resolution.resolution_type == "unresolved"]
        families.append(
            {
                "family_code": family["family_code"],
                "logical_name": family["logical_name"],
                "compatibility_status": family["compatibility_status"],
                "matched_file_names": [item["name"] for item in family["matched_files"]],
                "payload_registry_field_count": len(payload_fields),
                "real_bookmark_count": len(actual_bookmarks),
                "copy_forward_dependencies": family["copy_forward_dependencies"],
                "field_resolutions": [
                    {
                        "field_name": resolution.field_name,
                        "resolution_type": resolution.resolution_type,
                        "target_bookmarks": list(resolution.target_bookmarks),
                        "evidence": resolution.evidence,
                    }
                    for resolution in resolutions
                ],
                "unresolved_fields": unresolved_fields,
                "unmatched_real_bookmarks": [
                    bookmark for bookmark in actual_bookmarks if bookmark not in resolved_targets
                ],
            }
        )
    return {"families": families}


def render_markdown(reconciliation: dict) -> str:
    lines = [
        "# Phase 5 Template Contract Reconciliation",
        "",
        "## Scope",
        "- Input 1: curated payload registry from VBA-derived bookmark evidence.",
        "- Input 2: real active template bookmark audit from `legacy/Templates`.",
        "- Goal: produce a safe reconciliation layer before any runtime aliasing is introduced.",
        "",
        "## Families",
    ]
    for family in reconciliation["families"]:
        resolution_counts: dict[str, int] = {}
        for resolution in family["field_resolutions"]:
            resolution_counts[resolution["resolution_type"]] = resolution_counts.get(resolution["resolution_type"], 0) + 1
        counts = ", ".join(f"{key}={value}" for key, value in sorted(resolution_counts.items()))
        files = ", ".join(f"`{name}`" for name in family["matched_file_names"]) or "none"
        lines.append(
            f"- `{family['family_code']}` | status=`{family['compatibility_status']}` "
            f"| payload_fields={family['payload_registry_field_count']} | real_bookmarks={family['real_bookmark_count']} "
            f"| resolutions={counts}"
        )
        lines.append(f"  files: {files}")
        if family["unresolved_fields"]:
            lines.append(
                "  unresolved fields: "
                + ", ".join(f"`{field}`" for field in family["unresolved_fields"][:20])
            )
        if family["unmatched_real_bookmarks"]:
            lines.append(
                "  unmatched real bookmarks: "
                + ", ".join(f"`{field}`" for field in family["unmatched_real_bookmarks"][:20])
            )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    reconciliation = build_reconciliation()
    OUTPUT_JSON.write_text(json.dumps(reconciliation, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_MD.write_text(render_markdown(reconciliation), encoding="utf-8")


if __name__ == "__main__":
    main()
