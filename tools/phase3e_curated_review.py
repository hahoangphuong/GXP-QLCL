from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PHASE3D_QUEUE_PATH = ROOT / "artifacts" / "phase3d" / "manual_review_queue.json"
PHASE3D_OVERRIDES_PATH = ROOT / "artifacts" / "phase3d" / "high_confidence_overrides.json"
PHASE2_DB_PATH = ROOT / "artifacts" / "phase2" / "staging_readonly.db"

YEAR_RE = re.compile(r"(20\d{2})")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_years(text: str | None) -> list[int]:
    if not text:
        return []
    return [int(match) for match in YEAR_RE.findall(text)]


def fetch_case_timeline_years(con: sqlite3.Connection, legacy_case_id: int) -> list[int]:
    cur = con.cursor()
    cur.execute(
        """
        SELECT ca.submitted_on, cas.assessed_on, io.inspected_on
        FROM "case" c
        LEFT JOIN case_application ca ON ca.case_id = c.id
        LEFT JOIN case_assessment cas ON cas.case_id = c.id
        LEFT JOIN inspection_outcome io ON io.case_id = c.id
        WHERE c.legacy_inspection_id = ?
        """,
        (legacy_case_id,),
    )
    row = cur.fetchone()
    if row is None:
        return []
    years: set[int] = set()
    for value in row:
        if value:
            years.add(int(str(value)[:4]))
    return sorted(years)


def choose_curated_candidate(cert_year: int, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    same_year = [candidate for candidate in candidates if cert_year in candidate["timeline_years"]]
    if len(same_year) == 1:
        return {
            "matched_candidate": same_year[0],
            "match_kind": "same_year",
        }

    prev_year = [candidate for candidate in candidates if (cert_year - 1) in candidate["timeline_years"]]
    if not same_year and len(prev_year) == 1:
        return {
            "matched_candidate": prev_year[0],
            "match_kind": "previous_year",
        }

    return None


def build_phase3e_analysis() -> dict[str, Any]:
    queue = load_json(PHASE3D_QUEUE_PATH)
    phase3d_overrides = load_json(PHASE3D_OVERRIDES_PATH)

    curated_suggestions: list[dict[str, Any]] = []
    curated_overrides: dict[str, dict[str, dict[str, int]]] = {}

    con = sqlite3.connect(str(PHASE2_DB_PATH))
    try:
        for item in queue:
            if item["source_sheet"] != "db.cc":
                continue
            candidates = item.get("candidate_cases", [])
            if not (2 <= len(candidates) <= 3):
                continue

            cert_number = item.get("legacy_context", {}).get("certificate_number")
            cert_years = extract_years(cert_number)
            if not cert_years:
                continue
            cert_year = max(cert_years)

            enriched_candidates = []
            for candidate in candidates:
                timeline_years = fetch_case_timeline_years(con, int(candidate["legacy_case_id"]))
                enriched = dict(candidate)
                enriched["timeline_years"] = timeline_years
                enriched_candidates.append(enriched)

            choice = choose_curated_candidate(cert_year, enriched_candidates)
            if choice is None:
                continue

            matched_candidate = choice["matched_candidate"]
            suggestion = {
                "source_sheet": "db.cc",
                "legacy_row_id": item["legacy_row_id"],
                "override": {"case_legacy_id": int(matched_candidate["legacy_case_id"])},
                "rule": "certificate_year_timeline_match",
                "evidence": {
                    "certificate_number": cert_number,
                    "certificate_year": cert_year,
                    "match_kind": choice["match_kind"],
                    "matched_candidate": matched_candidate,
                    "all_candidates": enriched_candidates,
                    "legacy_context": item.get("legacy_context", {}),
                },
            }
            curated_suggestions.append(suggestion)
            curated_overrides.setdefault("db.cc", {})[item["legacy_row_id"]] = suggestion["override"]
    finally:
        con.close()

    merged_overrides = json.loads(json.dumps(phase3d_overrides))
    for sheet, rows in curated_overrides.items():
        merged_overrides.setdefault(sheet, {}).update(rows)

    curated_suggestions.sort(key=lambda item: int(item["legacy_row_id"]))

    return {
        "phase3d_override_count": sum(len(rows) for rows in phase3d_overrides.values()),
        "curated_suggestions": curated_suggestions,
        "curated_suggestion_count": len(curated_suggestions),
        "curated_overrides": curated_overrides,
        "merged_overrides": merged_overrides,
    }
