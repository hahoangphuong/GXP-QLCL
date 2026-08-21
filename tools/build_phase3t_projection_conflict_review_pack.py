from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFLICT_PATH = ROOT / "artifacts" / "phase3p" / "current_projection_conflicts.json"
DECISION_PATH = ROOT / "artifacts" / "phase3s" / "current_projection_conflict_decisions.template.json"
DUPLICATE_PATH = ROOT / "artifacts" / "legacy_audit" / "duplicate_current_analysis.json"
OUT_DIR = ROOT / "artifacts" / "phase3t"
JSON_OUT = OUT_DIR / "current_projection_conflict_review_pack.json"
CSV_OUT = OUT_DIR / "current_projection_conflict_review_pack.csv"
MD_OUT = OUT_DIR / "current_projection_conflict_review_pack.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sanitize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())


def build_duplicate_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for sheet_key in ("db_cc", "db_ktra"):
        for group in payload.get(sheet_key, {}).get("groups", []):
            lookup_key = str(group.get("lookup_key", "")).strip()
            if lookup_key:
                index[f"{sheet_key}:{lookup_key}"] = group
    return index


def group_key_from_conflict(row: dict[str, Any]) -> str:
    source_sheet = str(row["source_sheet"]).strip()
    lookup_key = str(row["business_key"]).strip()
    if source_sheet == "db.cc":
        return f"db_cc:{lookup_key}"
    if source_sheet == "db.ktra":
        return f"db_ktra:{lookup_key}"
    raise ValueError(f"Unsupported source_sheet: {source_sheet}")


def build_review_focus(row: dict[str, Any]) -> str:
    classification = str(row["classification"])
    if classification == "blank_ma_dc_non_case_backed_multi_current":
        return "Chon mot current certificate winner hoac xac nhan khong co winner khi cac dong khong co inspection/case backing."
    if classification == "completed_plus_pending_both_current":
        return "Xac nhan dong current-case nao moi dung khi mot dong completed va mot dong pending cung dang current."
    if classification == "multiple_completed_both_current":
        return "Xac nhan dong current-case winner khi co nhieu dong completed cung dang current."
    return "Can review thu cong."


def build_decision_question(row: dict[str, Any]) -> str:
    if str(row["projection_type"]) == "current_certificate_projection":
        return "Legacy certificate row nao phai dai dien cho current certificate projection cua site nay?"
    return "Legacy inspection row nao phai dai dien cho current case projection cua inspection key nay?"


def build_evidence_summary(conflict: dict[str, Any], duplicate_group: dict[str, Any]) -> str:
    detail = conflict.get("detail", {})
    if conflict["projection_type"] == "current_certificate_projection":
        certs = ", ".join(sanitize_text(item) for item in detail.get("unique_certificate_nos", []))
        return (
            f"All candidate rows have blank ma_dc={detail.get('all_blank_ma_dc')} and blank inspection_id="
            f"{detail.get('all_blank_inspection_id')}; certificate_nos=[{certs}]"
        )
    progress_values = ", ".join(sanitize_text(item) for item in detail.get("progress_values", []))
    linked_certificate_ids = ", ".join(sanitize_text(item) for item in detail.get("linked_certificate_ids", []))
    candidate_rows = duplicate_group.get("rows", [])
    row_states = ", ".join(
        f"{sanitize_text(item.get('legacy_row_id'))}:{sanitize_text(item.get('progress', ''))}"
        for item in candidate_rows
    )
    return (
        f"Progress values=[{progress_values}]; linked_certificate_ids=[{linked_certificate_ids}]; "
        f"candidate_row_states=[{row_states}]"
    )


def build_candidate_detail_lines(duplicate_group: dict[str, Any], projection_type: str) -> list[str]:
    lines: list[str] = []
    for row in duplicate_group.get("rows", []):
        if projection_type == "current_certificate_projection":
            lines.append(
                f"- legacy_row_id={sanitize_text(row.get('legacy_row_id'))}; "
                f"certificate_no={sanitize_text(row.get('certificate_no'))}; "
                f"issue_date={sanitize_text(row.get('issue_date'))}; "
                f"expiry_date={sanitize_text(row.get('expiry_date'))}"
            )
        else:
            lines.append(
                f"- legacy_row_id={sanitize_text(row.get('legacy_row_id'))}; "
                f"progress={sanitize_text(row.get('progress'))}; "
                f"linked_certificate_id={sanitize_text(row.get('linked_certificate_id'))}"
            )
    return lines


def build_review_pack() -> dict[str, Any]:
    conflicts = load_json(CONFLICT_PATH)
    decisions = load_json(DECISION_PATH)
    duplicates = load_json(DUPLICATE_PATH)
    decision_index = {
        str(row["conflict_key"]): row for row in decisions.get("decisions", [])
    }
    duplicate_index = build_duplicate_index(duplicates)

    review_rows: list[dict[str, Any]] = []
    for conflict in conflicts.get("conflicts", []):
        conflict_key = str(conflict["conflict_key"])
        decision = decision_index[conflict_key]
        duplicate_group = duplicate_index[group_key_from_conflict(conflict)]
        review_rows.append(
            {
                "conflict_key": conflict_key,
                "projection_type": conflict["projection_type"],
                "source_sheet": conflict["source_sheet"],
                "business_key": conflict["business_key"],
                "classification": conflict["classification"],
                "candidate_count": conflict["candidate_count"],
                "candidate_legacy_ids": conflict["candidate_legacy_ids"],
                "current_decision_action": decision["decision_action"],
                "selected_candidate_legacy_id": decision["selected_candidate_legacy_id"],
                "review_focus": build_review_focus(conflict),
                "decision_question": build_decision_question(conflict),
                "resolution_rationale": conflict["resolution_rationale"],
                "evidence_summary": build_evidence_summary(conflict, duplicate_group),
                "candidate_details": build_candidate_detail_lines(
                    duplicate_group, conflict["projection_type"]
                ),
            }
        )

    return {
        "generated_on": "2026-08-14",
        "source_conflict_count": len(review_rows),
        "review_rows": review_rows,
    }


def write_csv(rows: list[dict[str, Any]]) -> None:
    with CSV_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "conflict_key",
                "projection_type",
                "source_sheet",
                "business_key",
                "classification",
                "candidate_count",
                "candidate_legacy_ids",
                "current_decision_action",
                "selected_candidate_legacy_id",
                "review_focus",
                "decision_question",
                "resolution_rationale",
                "evidence_summary",
                "candidate_details",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "candidate_legacy_ids": "; ".join(row["candidate_legacy_ids"]),
                    "candidate_details": " | ".join(row["candidate_details"]),
                }
            )


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Current Projection Conflict Review Pack",
        "",
        f"- Generated on: `{payload['generated_on']}`",
        f"- Conflict count: `{payload['source_conflict_count']}`",
        "",
    ]
    for row in payload["review_rows"]:
        lines.extend(
            [
                f"## {row['conflict_key']}",
                "",
                f"- Projection: `{row['projection_type']}`",
                f"- Source sheet: `{row['source_sheet']}`",
                f"- Business key: `{row['business_key']}`",
                f"- Classification: `{row['classification']}`",
                f"- Candidate legacy ids: `{', '.join(row['candidate_legacy_ids'])}`",
                f"- Current decision action: `{row['current_decision_action']}`",
                f"- Review focus: {row['review_focus']}",
                f"- Decision question: {row['decision_question']}",
                f"- Resolution rationale: {row['resolution_rationale']}",
                f"- Evidence summary: {row['evidence_summary']}",
                "",
                "### Candidate Details",
                "",
            ]
        )
        lines.extend(row["candidate_details"])
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_review_pack()
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(payload["review_rows"])
    MD_OUT.write_text(render_markdown(payload), encoding="utf-8")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
