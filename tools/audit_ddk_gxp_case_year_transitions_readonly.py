"""Compare private original-year and dual-year Case SMB observations, read-only.

Pure private JSON comparison. No DB/SMB access, no folder display name, Site ID
or Case UUID in stdout. Preserves source evidence and refuses a regression.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

from tools.audit_ddk_gxp_smb_readonly_folder_pilot import (
    SCHEMA as ORIGINAL_SCHEMA, verified_lookup_targets,
)
from tools.audit_ddk_gxp_case_dual_year_readonly import SCHEMA as DUAL_SCHEMA
from tools.build_ddk_gxp_manual_review_queue import _private_input, build_review_queue


SCHEMA = "GXP_DDK_CASE_SMB_YEAR_TRANSITIONS_READONLY_V1"
_EXPECTED_ORIGINAL = {"CASE_RESOLVED": 2, "CASE_NOT_FOUND": 4}
_EXPECTED_DUAL = {"CASE_RESOLVED": 3, "CASE_NOT_FOUND": 3}
_ALLOWED = {"RESOLVED", "NOT_FOUND", "AMBIGUOUS", "INVALID"}


class CaseTransitionBlocked(ValueError):
    pass


def _require(ok: bool, why: str) -> None:
    if not ok:
        raise CaseTransitionBlocked(why)


def compare_private_case_observations(
    old: dict[str, Any],
    dual: dict[str, Any],
    queue: dict[str, Any],
    readiness: dict[str, Any],
    readiness_sha256: str,
) -> dict[str, Any]:
    ddks, cases = verified_lookup_targets(queue, readiness)
    _require(len(ddks) == 8 and len(cases) == 6,
             "Original canonical source population differs")
    ids = {item["parent_id"] for item in cases}
    _require(
        old.get("schema") == ORIGINAL_SCHEMA
        and old.get("status") == "SMB_FOLDER_IDENTITY_OBSERVATIONS_UNVERIFIED"
        and old.get("approval_status") == "NOT_APPROVED"
        and old.get("adapter_class") == "synology_smb"
        and old.get("case_lookups_attempted") == 6
        and old.get("case_not_probed") == 0
        and old.get("total_case_targets") == 6
        and old.get("database_connected") is False
        and old.get("database_writes") == 0
        and old.get("storage_writes") == 0
        and old.get("storage_file_contents_accessed") is False
        and old.get("canonical_links_created") == 0
        and dual.get("schema") == DUAL_SCHEMA
        and dual.get("status") == "BOTH_ORIGINAL_SOURCE_YEARS_CHECKED_NO_APPROVAL"
        and dual.get("approval_status") == "NOT_APPROVED"
        and dual.get("storage_adapter") == "synology_smb"
        and dual.get("case_parents_checked") == 6
        and dual.get("database_access") == "REHEARSAL_READ_ONLY"
        and dual.get("database_writes") == 0
        and dual.get("storage_writes") == 0
        and dual.get("storage_binaries_read") is False
        and dual.get("canonical_links_created") == 0
        and dual.get("readiness_sha256") == readiness_sha256,
        "Private reports not fully sourced, complete or read-only",
    )
    _require(
        {k: v for k, v in old.get("counts", {}).items()
         if k.startswith("CASE_")} == _EXPECTED_ORIGINAL
        and dual.get("counts", {}).get("CASE_RESOLVED") == 3
        and dual.get("counts", {}).get("CASE_NOT_FOUND") == 3
        and dual.get("counts", {}).get("CASE_WITH_TWO_DISTINCT_SOURCE_YEARS") == 3
        and dual.get("year_specific_lookups") == 9,
        "Original and dual-year population aggregates drifted",
    )

    originals = old.get("private_folder_observations")
    updated = dual.get("private_case_observations")
    _require(isinstance(originals, list) and isinstance(updated, list),
             "Case details absent")
    original_rows = [r for r in originals
                     if isinstance(r, dict) and r.get("parent_type") == "ORIGINATING_CASE"]
    _require(len(original_rows) == len(updated) == 6,
             "Expected exactly six Case observations in both reports")

    by_old = {r["parent_id"]: r for r in original_rows}
    by_new = {r["originating_case_id"]: r for r in updated}
    _require(len(by_old) == len(by_new) == 6
             and set(by_old) == set(by_new) == ids,
             "Case identity or unique-parent population changed")
    expected_by_id = {r["parent_id"]: r for r in cases}
    counts: Counter[str] = Counter()
    year_checks = 0
    for id in sorted(ids):
        before, after = by_old[id], by_new[id]
        _require(before.get("legal_approval") == after.get("legal_approval") == "NOT_APPROVED",
                 "Unexpected approval status in private observation")
        lookup = before.get("lookup_input")
        _require(
            isinstance(lookup, dict)
            and lookup.get("site_legacy_id") == expected_by_id[id]["site_legacy_id"]
            and lookup.get("inspection_legacy_code") == expected_by_id[id]["inspection_legacy_code"]
            and lookup.get("source_year") == expected_by_id[id]["year"],
            "Original Case source key changed",
        )
        year = lookup["source_year"]
        original_status = before.get("status", "").upper()
        final_status = after.get("final_status")
        _require(original_status in _ALLOWED and final_status in _ALLOWED,
                 "Unrecognized Case resolution status")
        observations = after.get("year_specific_observations")
        _require(isinstance(observations, list) and 1 <= len(observations) <= 2,
                 "Invalid source year evidence")
        _require(all(type(row.get("source_year")) is int for row in observations),
                 "Non-integer original year")
        years = {row["source_year"]: row for row in observations}
        _require(len(years) == len(observations) and year in years,
                 "Original single-year evidence was not repeated")
        for row in observations:
            _require(row.get("status", "").upper() in _ALLOWED
                     and type(row.get("candidate_count")) is int
                     and row["candidate_count"] >= 0
                     and isinstance(row.get("provenance"), list),
                     "Invalid per-year observation")
        repeated = years[year]
        _require(
            repeated["status"].upper() == original_status
            and repeated["candidate_count"] == before.get("candidate_count")
            and repeated.get("relative_path_private_unverified")
                == before.get("relative_path_private_unverified"),
            "Original source-year SMB observation drifted",
        )
        resolved = [row for row in observations
                    if row["status"].upper() == "RESOLVED"]
        inferred = (
            "INVALID" if any(row["status"].upper() == "INVALID" for row in observations)
            else "AMBIGUOUS" if any(row["status"].upper() == "AMBIGUOUS" for row in observations)
                or len(resolved) > 1
            else "RESOLVED" if len(resolved) == 1 else "NOT_FOUND"
        )
        _require(final_status == inferred, "Final Case status contradicts original per-year results")
        _require(not (original_status == "RESOLVED" and final_status != "RESOLVED"),
                 "Previously resolved Case regressed")
        counts[f"{original_status}_TO_{final_status}"] += 1
        year_checks += len(observations)

    _require(year_checks == dual["year_specific_lookups"]
             and sum(counts.values()) == 6
             and sum(v for k, v in counts.items() if k.endswith("_TO_RESOLVED")) == 3,
             "Original Case transition aggregate mismatch")
    return {
        "schema": SCHEMA,
        "status": "PRIVATE_CANONICAL_CASE_TRANSITIONS_VERIFIED",
        "approval_status": "NOT_APPROVED",
        "case_parents_compared": 6,
        "original_year_observation_drift": 0,
        "resolved_case_regressions": 0,
        "year_specific_observations_checked": year_checks,
        "transitions": dict(sorted(counts.items())),
        "database_connected": False,
        "storage_connected": False,
        "database_writes": 0,
        "storage_writes": 0,
        "canonical_links_created": 0,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dossier-json", type=Path, required=True)
    ap.add_argument("--queue-json", type=Path, required=True)
    ap.add_argument("--readiness-json", type=Path, required=True)
    ap.add_argument("--original-smb-json", type=Path, required=True)
    ap.add_argument("--dual-year-smb-json", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        paths = [
            args.dossier_json, args.queue_json, args.readiness_json,
            args.original_smb_json, args.dual_year_smb_json,
        ]
        _require(len({str(p.resolve()) for p in paths}) == 5
                 and len({p.parent.resolve() for p in paths}) == 1,
                 "Protected inputs must be distinct and colocated")
        dossier = json.loads(_private_input(args.dossier_json))
        queue = json.loads(_private_input(args.queue_json))
        ready_bytes = _private_input(args.readiness_json)
        readiness = json.loads(ready_bytes)
        old = json.loads(_private_input(args.original_smb_json))
        dual = json.loads(_private_input(args.dual_year_smb_json))
        _require(queue == build_review_queue(dossier),
                 "Original source evidence changed")
        result = compare_private_case_observations(
            old, dual, queue, readiness, sha256(ready_bytes).hexdigest(),
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print("DDK_CASE_TRANSITIONS_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
