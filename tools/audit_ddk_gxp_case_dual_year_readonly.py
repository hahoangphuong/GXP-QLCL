"""Verify both db.ktra source years for flagged originating Cases, read-only.

Uses the same source-year policy as StorageBindingService, with direct SMB
adapter metadata-only calls. Does not invoke binding service resolution, open
file streams, mutate DB/NAS, infer Certificate folders or approve any links.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.app.db.enums import StorageResolutionStatus
from backend.app.db.models.phase1 import LegacyInspectionStorageAnchor
from backend.app.storage.binding_service import StorageBindingService
from backend.app.storage.factory import create_storage_service_from_env
from backend.app.storage.smb import SmbStorageService, smbclient, smbpath
from backend.app.storage.types import matches_inspection_identity
from tools.apply_ddk_gxp_provenance_rehearsal import checked_rehearsal_url
from tools.audit_ddk_gxp_canonical_candidates_readonly import _write_private_json
from tools.audit_ddk_gxp_smb_readonly_folder_pilot import (
    check_configured_roots_readonly, verified_lookup_targets,
)
from tools.audit_ddk_gxp_storage_identity_readiness import profile_storage_lookup_inputs
from tools.build_ddk_gxp_manual_review_queue import _private_input, build_review_queue
from tools.env_utils import parse_env_file
from tools.preflight_ddk_gxp_rehearsal import EXPECTED_DB, EXPECTED_REVISION


SCHEMA = "GXP_DDK_CASE_DUAL_SOURCE_YEAR_SMB_READONLY_V1"


class DualYearCaseAuditBlocked(ValueError):
    pass


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise DualYearCaseAuditBlocked(message)


def read_source_verified_years(
    database_url: str, queue: dict[str, Any], readiness: dict[str, Any],
) -> list[dict[str, Any]]:
    """Read independent db.ktra H/M evidence with exact known parent identities."""
    expected_ddk, cases = verified_lookup_targets(queue, readiness)
    _require(len(expected_ddk) == 8 and len(cases) == 6,
             "Unexpected source case population")
    root = {
        record["originating_case_reference"]["case_id"]:
        record["originating_case_reference"]
        for record in readiness["private_lookup_input_evidence"]
        if record["originating_case_reference"] is not None
    }
    engine = create_engine(database_url, poolclass=NullPool, connect_args={
        "options": "-c default_transaction_read_only=on -c statement_timeout=30000",
    })
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.exec_driver_sql(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                )
                _require(
                    conn.execute(text("SELECT current_database()")).scalar_one() == EXPECTED_DB
                    and conn.execute(text("SHOW transaction_read_only")).scalar_one() == "on"
                    and conn.execute(text("SHOW transaction_isolation")).scalar_one() == "repeatable read"
                    and list(conn.execute(text(
                        "SELECT version_num FROM public.alembic_version"
                    )).scalars()) == [EXPECTED_REVISION],
                    "Not a guarded read-only rehearsal DB",
                )
                with Session(bind=conn, autoflush=False) as session:
                    actual = profile_storage_lookup_inputs(session, queue)
                    _require(actual == readiness,
                             "Canonical Case source identities drifted since readiness audit")
                    anchor_map = {
                        x.case_id: x for x in session.scalars(
                            select(LegacyInspectionStorageAnchor).where(
                                LegacyInspectionStorageAnchor.case_id.in_(
                                    [case["parent_id"] for case in cases]
                                )
                            )
                        )
                    }
                    out: list[dict[str, Any]] = []
                    for case in cases:
                        expected = root[case["parent_id"]]
                        anchor = anchor_map.get(case["parent_id"])
                        years = StorageBindingService._anchor_years(anchor)
                        _require(
                            bool(years) and years[0] == expected["source_year_observed"]
                            and len(years) <= 2
                            and case["year"] == years[0]
                            and anchor is not None,
                            "Missing, malformed or changed original source-year evidence",
                        )
                        labels = []
                        if anchor.registration_submission_status == "usable":
                            labels.append(("submission", anchor.registration_submission_year))
                        if anchor.inspection_year_status == "usable":
                            labels.append(("inspection", anchor.inspection_year))
                        _require(
                            tuple(dict.fromkeys(year for _, year in labels)) == years,
                            "Unexpected source year derivation",
                        )
                        out.append({
                            **case,
                            "source_years": [
                                {
                                    "year": year,
                                    "provenance": [
                                        label for label, value in labels if value == year
                                    ],
                                }
                                for year in years
                            ],
                        })
                    return out
    finally:
        engine.dispose()


def probe_source_years_readonly(
    storage: SmbStorageService, cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Probe exactly H/M-derived candidate years, never increment or infer."""
    _require(isinstance(storage, SmbStorageService) and len(cases) == 6,
             "Not an approved bounded Synology probe")
    counts: Counter[str] = Counter()
    private = []
    for case in cases:
        choices = case["source_years"]
        _require(1 <= len(choices) <= 2, "Unbounded source year inputs")
        observed = []
        for source in choices:
            res = storage.resolve_inspection_folder(
                year=source["year"],
                site_legacy_id=case["site_legacy_id"],
                inspection_legacy_code=case["inspection_legacy_code"],
            )
            _require(res.status in StorageResolutionStatus,
                     "Unexpected storage resolution status")
            observed.append({
                "source_year": source["year"],
                "provenance": source["provenance"],
                "status": res.status.value,
                "candidate_count": res.candidate_count,
                "relative_path_private_unverified": res.relative_path,
            })
            counts["SOURCE_YEAR_LOOKUPS_ATTEMPTED"] += 1
        matches = [r for r in observed if r["status"] == "resolved"]
        if any(r["status"] == "invalid" for r in observed):
            status = "INVALID"
        elif any(r["status"] == "ambiguous" for r in observed) or len(matches) > 1:
            status = "AMBIGUOUS"
        elif len(matches) == 1:
            status = "RESOLVED"
            for label in matches[0]["provenance"]:
                counts["RESOLVED_BY_" + label.upper() + "_YEAR"] += 1
        else:
            status = "NOT_FOUND"
        counts["CASE_" + status] += 1
        if len(choices) == 2:
            counts["CASE_WITH_TWO_DISTINCT_SOURCE_YEARS"] += 1
        private.append({
            "originating_case_id": case["parent_id"],
            "final_status": status,
            "year_specific_observations": observed,
            "legal_approval": "NOT_APPROVED",
        })
    return {
        "schema": SCHEMA,
        "status": "BOTH_ORIGINAL_SOURCE_YEARS_CHECKED_NO_APPROVAL",
        "approval_status": "NOT_APPROVED",
        "case_parents_checked": len(cases),
        "year_specific_lookups": counts["SOURCE_YEAR_LOOKUPS_ATTEMPTED"],
        "counts": dict(sorted(counts.items())),
        "storage_adapter": "synology_smb",
        "storage_binaries_read": False,
        "storage_writes": 0,
        "database_access": "REHEARSAL_READ_ONLY",
        "database_writes": 0,
        "canonical_links_created": 0,
        "private_case_observations": private,
        "limitations": [
            "Each year is physically recorded in db.ktra H/M, no year+1 fallback",
            "Matching Case folders do not establish Certificate or DDK coverage",
            "Two independent matching years are ambiguous, not auto-approved",
            "A NOT_FOUND is scoped to configured inspection root and source years",
        ],
    }



def classify_unresolved_case_year_roots_readonly(
    storage: SmbStorageService,
    missing_cases: list[dict[str, Any]],
    *,
    max_entries_per_root: int = 3000,
    max_entries_total: int = 12000,
) -> dict[str, Any]:
    """Explain prior NOT_FOUND for source-bound Case/year probes, metadata only.

    Requires three independently source-bound Cases and four *previously*
    NOT_FOUND year observations. Only their physical source years are read;
    no alternate root, year, key, deep recursion or content read is allowed.
    Reports aggregate classes, NEVER a year, Site, Case, filename or path.
    """
    _require(
        isinstance(storage, SmbStorageService)
        and bool(storage.inspection_root)
        and smbclient is not None and smbpath is not None,
        "Expected the approved direct SMB adapter",
    )
    _require(
        type(max_entries_per_root) is int and 1 <= max_entries_per_root <= 3000
        and type(max_entries_total) is int and 1 <= max_entries_total <= 12000
        and isinstance(missing_cases, list) and len(missing_cases) == 3,
        "Unexpected source-bound diagnostic budget/population",
    )
    _require(
        len({item.get("parent_id") for item in missing_cases}) == 3,
        "Duplicate Case source identity",
    )

    validated: list[tuple[int, int, str]] = []
    for case in missing_cases:
        sid = case.get("site_legacy_id")
        code = case.get("inspection_legacy_code")
        observations = case.get("year_specific_observations")
        _require(
            type(sid) is int and sid > 0 and isinstance(code, str)
            and bool(code.strip()) and isinstance(observations, list)
            and 1 <= len(observations) <= 2,
            "Invalid Case identity or original source years",
        )
        years: set[int] = set()
        for observation in observations:
            year = observation.get("source_year")
            _require(
                type(year) is int and 1900 <= year <= 2100
                and year not in years
                and observation.get("status") == "not_found"
                and observation.get("candidate_count") == 0
                and observation.get("relative_path_private_unverified") is None
                and isinstance(observation.get("provenance"), list)
                and bool(observation["provenance"])
                and set(observation["provenance"]) <= {"submission", "inspection"},
                "Not an original unresolved source-year observation",
            )
            years.add(year)
            validated.append((year, sid, code))
    _require(len(validated) == 4 and len({y for y, _, _ in validated}) <= 4,
             "Unexpected source-year lookup count")

    # Read each exact year root once, including the same root shared by Cases.
    # A budget overrun or SMB error fails closed without a partial absence claim.
    root_names: dict[int, list[str] | None] = {}
    entries_total = 0
    for year in sorted({y for y, _, _ in validated}):
        year_root = storage._join_root(storage.inspection_root, str(year))
        if not smbpath.exists(year_root):
            root_names[year] = None
            continue
        _require(bool(smbpath.isdir(year_root)),
                 "Source-year SMB entry is not a directory")
        names: list[str] = []
        entries_this_root = 0
        for entry in smbclient.scandir(year_root):
            entries_this_root += 1
            entries_total += 1
            _require(
                entries_this_root <= max_entries_per_root
                and entries_total <= max_entries_total,
                "Bounded source-year metadata scan exceeded budget",
            )
            if entry.is_dir():
                names.append(entry.name)
        root_names[year] = names

    counts: Counter[str] = Counter()
    for year, sid, code in validated:
        names = root_names[year]
        if names is None:
            label = "YEAR_ROOT_NOT_FOUND"
        else:
            # Use the same literal matcher and token case rules as the SMB
            # inspection resolver; partial matches are observations, not keys.
            site_token = f"(ID-{sid})".lower()
            code_token = f"({code.strip()})".lower()
            site = any(site_token in name.lower() for name in names)
            inspection = any(code_token in name.lower() for name in names)
            _require(
                not any(
                    matches_inspection_identity(
                        name, site_legacy_id=sid,
                        inspection_legacy_code=code,
                    ) for name in names
                ),
                "Previous NOT_FOUND observation no longer matches direct year folder",
            )
            if site and inspection:
                label = "SPLIT_TOKENS_DIFFERENT_FOLDERS"
            elif site:
                label = "SITE_TOKEN_ONLY"
            elif inspection:
                label = "INSPECTION_CODE_ONLY"
            else:
                label = "NO_EXACT_TOKEN"
        counts[label] += 1

    _require(sum(counts.values()) == 4, "Incomplete year observation classification")
    return {
        "status": "ORIGINAL_NOT_FOUND_YEAR_ROOT_METADATA_CLASSIFIED",
        "approval_status": "NOT_APPROVED",
        "missing_case_parents_checked": 3,
        "source_year_observations_checked": 4,
        "distinct_source_year_roots_checked": len(root_names),
        "year_root_entries_scanned": entries_total,
        "classification_counts": dict(sorted(counts.items())),
        "scope": "EXACT_PRIOR_SOURCE_YEARS_DIRECT_CHILD_METADATA_ONLY",
        "database_connected": False,
        "database_writes": 0,
        "storage_file_contents_accessed": False,
        "storage_writes": 0,
        "canonical_links_created": 0,
    }



def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dossier-json", type=Path, required=True)
    ap.add_argument("--queue-json", type=Path, required=True)
    ap.add_argument("--readiness-json", type=Path, required=True)
    ap.add_argument("--runtime-env", type=Path, default=Path("/etc/gxp/runtime.env"))
    ap.add_argument("--details-json", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        paths = [args.dossier_json, args.queue_json, args.readiness_json, args.details_json]
        _require(
            len({p.resolve() for p in paths}) == 4
            and len({p.parent.resolve() for p in paths}) == 1
            and not args.details_json.exists()
            and not args.details_json.is_symlink(),
            "Private inputs/output must be distinct and confined",
        )
        dossier = json.loads(_private_input(args.dossier_json))
        queue = json.loads(_private_input(args.queue_json))
        readiness_bytes = _private_input(args.readiness_json)
        readiness = json.loads(readiness_bytes)
        _require(
            queue == build_review_queue(dossier)
            and queue.get("source_tokens_checked") == 861
            and queue.get("source_exception_token_records") == 8
            and queue.get("ddk_company_review_records") == 1,
            "Original source evidence changed",
        )
        env = parse_env_file(args.runtime_env)
        _require(
            env.get("STORAGE_CLASS", "").strip() == "synology_smb"
            and bool(env.get("STORAGE_INSPECTION_ROOT", "").strip())
            and bool(env.get("STORAGE_DKKD_ROOT", "").strip())
            and bool(env.get("SMB_USERNAME", "").strip())
            and bool(env.get("SMB_PASSWORD", "").strip()),
            "Configured Synology SMB connection unavailable",
        )
        years = read_source_verified_years(checked_rehearsal_url(env), queue, readiness)
        # Database connections are disposed *before* any SMB requests.
        storage = create_storage_service_from_env(env)
        check_configured_roots_readonly(storage)
        report = probe_source_years_readonly(storage, years)
        report["readiness_sha256"] = sha256(readiness_bytes).hexdigest()
        _write_private_json(args.details_json, report)
        safe = {key: value for key, value in report.items()
                if key not in {"private_case_observations", "limitations"}}
        print(json.dumps(safe, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print("DDK_CASE_DUAL_YEAR_SMB_AUDIT_BLOCKED: " + type(exc).__name__,
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
