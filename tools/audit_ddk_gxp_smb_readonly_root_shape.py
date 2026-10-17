"""Bounded, aggregate-only read-only diagnosis of the configured DDK SMB root.

Diagnoses why eight original-source-key DDK site folders were NOT_FOUND.
No DB, file content, mutation, path guessing, alternative resolution or approval.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any

from backend.app.storage.factory import create_storage_service_from_env
from backend.app.storage.smb import SmbStorageService, smbclient
from backend.app.storage.types import matches_dkkd_identity
from tools.audit_ddk_gxp_canonical_candidates_readonly import _write_private_json
from tools.audit_ddk_gxp_smb_readonly_folder_pilot import (
    SCHEMA as FULL_PROBE_SCHEMA, check_configured_roots_readonly,
    verified_lookup_targets,
)
from tools.build_ddk_gxp_manual_review_queue import _private_input, build_review_queue
from tools.env_utils import parse_env_file

SCHEMA = "GXP_DDK_SMB_ROOT_SHAPE_READONLY_V1"
# Metadata observation only; NOT accepted alternative folder identities.
_NUMERIC_PAREN = re.compile(r"(?<!\d)\(\d+\)")
_EXACT_LEGACY_TOKEN = re.compile(r" \(\d+\)")
ENTRY_BUDGET = 10000


class RootShapeBlocked(ValueError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise RootShapeBlocked(reason)


def validate_source_and_full_report(
    queue: dict[str, Any], readiness: dict[str, Any], full: dict[str, Any],
) -> list[dict[str, Any]]:
    ddks, cases = verified_lookup_targets(queue, readiness)
    _require(len(ddks) == 8 and len(cases) == 6,
             "Distinct source lookup targets changed")
    _require(
        full.get("schema") == FULL_PROBE_SCHEMA
        and full.get("status") == "SMB_FOLDER_IDENTITY_OBSERVATIONS_UNVERIFIED"
        and full.get("approval_status") == "NOT_APPROVED"
        and full.get("adapter_class") == "synology_smb"
        and full.get("total_ddk_targets") == 8
        and full.get("total_case_targets") == 6
        and full.get("ddk_lookups_attempted") == 8
        and full.get("case_lookups_attempted") == 6
        and full.get("ddk_not_probed") == 0
        and full.get("case_not_probed") == 0
        and full.get("database_connected") is False
        and full.get("database_writes") == 0
        and full.get("storage_writes") == 0
        and full.get("storage_file_contents_accessed") is False
        and full.get("canonical_links_created") == 0,
        "Full private report was incomplete or not read-only",
    )
    counts = full.get("counts")
    _require(isinstance(counts, dict)
             and counts.get("DDK_NOT_FOUND") == 8
             and sum(v for k, v in counts.items() if k.startswith("DDK_")) == 8,
             "Source DDK missing-folder population changed")
    observations = full.get("private_folder_observations")
    _require(isinstance(observations, list) and len(observations) == 14,
             "Unexpected private parent-level evidence")
    expected = {t["parent_id"]: t["site_legacy_id"] for t in ddks}
    recorded: dict[str, int] = {}
    for row in observations:
        if row.get("parent_type") != "DDK":
            continue
        parent_id = row.get("parent_id")
        sid = row.get("lookup_input", {}).get("site_legacy_id")
        _require(
            isinstance(parent_id, str) and parent_id in expected
            and parent_id not in recorded
            and type(sid) is int and sid == expected[parent_id]
            and row.get("status") == "not_found"
            and row.get("candidate_count") == 0
            and row.get("relative_path_private_unverified") is None
            and row.get("legal_approval") == "NOT_APPROVED",
            "Private DDK NOT_FOUND observation does not match the original source",
        )
        recorded[parent_id] = sid
    _require(recorded == expected, "Missing or changed DDK source identity")
    return ddks


def summarize_root_direct_children(
    entries: Any, target_site_ids: list[int], *, max_entries: int = ENTRY_BUDGET,
) -> dict[str, Any]:
    """Inspect only names/types of root's direct entries; no paths are returned."""
    _require(type(max_entries) is int and 0 < max_entries <= ENTRY_BUDGET,
             "Invalid SMB metadata scan budget")
    _require(len(target_site_ids) == 8
             and all(type(x) is int and x > 0 for x in target_site_ids),
             "Invalid original DDK site identities")
    counts: Counter[str] = Counter()
    target_matches = {site_id: 0 for site_id in target_site_ids}
    iterator = iter(entries)
    try:
        for index, entry in enumerate(iterator):
            if index >= max_entries:
                raise RootShapeBlocked("Root direct-child metadata budget exceeded")
            counts["direct_entries"] += 1
            if not entry.is_dir():
                counts["files_or_other_direct_entries"] += 1
                continue
            counts["direct_child_directories"] += 1
            label = entry.name
            _require(isinstance(label, str), "Unexpected storage entry name")
            if _EXACT_LEGACY_TOKEN.search(label):
                counts["folders_with_legacy_numeric_token_shape"] += 1
            elif _NUMERIC_PAREN.search(label):
                counts["folders_with_numeric_parentheses_but_no_legacy_space_token"] += 1
            else:
                counts["folders_without_numeric_parenthesis_token"] += 1
            for sid in target_matches:
                if matches_dkkd_identity(label, site_legacy_id=sid):
                    target_matches[sid] += 1
    finally:
        closer = getattr(iterator, "close", None)
        if callable(closer):
            closer()

    counts["target_sites_with_zero_name_matches"] = sum(n == 0 for n in target_matches.values())
    counts["target_sites_with_one_name_match"] = sum(n == 1 for n in target_matches.values())
    counts["target_sites_with_multiple_name_matches"] = sum(n > 1 for n in target_matches.values())
    return dict(sorted(counts.items()))


def run_root_shape_readonly(storage: SmbStorageService, ddks: list[dict]) -> dict[str, Any]:
    _require(isinstance(storage, SmbStorageService)
             and storage.dkkd_root is not None and smbclient is not None,
             "Expected read-only Synology SMB root")
    counts = summarize_root_direct_children(
        smbclient.scandir(storage.dkkd_root),
        [x["site_legacy_id"] for x in ddks],
    )
    return {
        "schema": SCHEMA,
        "status": "ROOT_DIRECT_CHILD_SHAPE_METADATA_ONLY",
        "approval_status": "NOT_APPROVED",
        "adapter_class": "synology_smb",
        "original_source_ddk_parent_count": len(ddks),
        "scan_complete_within_budget": True,
        "direct_child_scan_budget": ENTRY_BUDGET,
        "counts": counts,
        "storage_root": "DDK_CONFIGURED_ROOT_ONLY",
        "storage_subdirectories_traversed": False,
        "storage_file_contents_accessed": False,
        "storage_writes": 0,
        "database_connected": False,
        "database_writes": 0,
        "canonical_links_created": 0,
        "limitations": [
            "Original NOT_FOUND classification remains unchanged by this diagnostic",
            "Numeric token-shape observations are not accepted alternative identity keys",
            "Only direct children of configured DDK root were enumerated",
            "Root mismatch is a hypothesis, not a proven missing source document",
            "No path, file binary or legal grant was verified",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dossier-json", required=True, type=Path)
    ap.add_argument("--queue-json", required=True, type=Path)
    ap.add_argument("--readiness-json", required=True, type=Path)
    ap.add_argument("--full-probe-json", required=True, type=Path)
    ap.add_argument("--runtime-env", type=Path, default=Path("/etc/gxp/runtime.env"))
    ap.add_argument("--details-json", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        paths = [args.dossier_json, args.queue_json, args.readiness_json,
                 args.full_probe_json, args.details_json]
        _require(len({str(p.absolute()) for p in paths}) == len(paths)
                 and len({p.parent.resolve() for p in paths}) == 1
                 and not args.details_json.exists()
                 and not args.details_json.is_symlink(),
                 "Protected evidence must be distinct with new output")
        dossier = json.loads(_private_input(args.dossier_json))
        queue = json.loads(_private_input(args.queue_json))
        readiness_bytes = _private_input(args.readiness_json)
        readiness = json.loads(readiness_bytes)
        prior_bytes = _private_input(args.full_probe_json)
        full = json.loads(prior_bytes)
        _require(queue == build_review_queue(dossier), "Original source evidence changed")
        _require(queue.get("source_tokens_checked") == 861
                 and queue.get("source_exception_token_records") == 8
                 and queue.get("ddk_company_review_records") == 1,
                 "Original source corpus changed")
        ddks = validate_source_and_full_report(queue, readiness, full)
        env = parse_env_file(args.runtime_env)
        _require(env.get("STORAGE_CLASS", "").strip() == "synology_smb"
                 and bool(env.get("STORAGE_DKKD_ROOT", "").strip())
                 and bool(env.get("STORAGE_INSPECTION_ROOT", "").strip())
                 and bool(env.get("SMB_USERNAME", "").strip())
                 and bool(env.get("SMB_PASSWORD", "").strip()),
                 "Configured Synology SMB connection unavailable")
        storage = create_storage_service_from_env(env)
        check_configured_roots_readonly(storage)
        report = run_root_shape_readonly(storage, ddks)
        report["source_readiness_sha256"] = sha256(readiness_bytes).hexdigest()
        report["prior_full_probe_sha256"] = sha256(prior_bytes).hexdigest()
        _write_private_json(args.details_json, report)
        public = {k: v for k, v in report.items() if k != "limitations"}
        print(json.dumps(public, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        # No raw SMB exceptions, UNC paths, private site IDs, or credentials.
        print("DDK_SMB_ROOT_SHAPE_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
