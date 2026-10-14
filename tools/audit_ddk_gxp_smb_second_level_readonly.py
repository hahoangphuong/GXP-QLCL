"""Source-bound, metadata-only DDK SMB second-level directory shape audit.

The configured DDK root has 274 direct directories and no direct numeric
parenthesized site tokens. Inspect only their *immediate* subdirectories.
No subtree recursion, alternate routing, file content, DB or NAS mutations.
Every first-level directory must be checked within explicit scan budgets.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Callable, Iterable

from backend.app.storage.factory import create_storage_service_from_env
from backend.app.storage.smb import SmbStorageService, smbclient
from backend.app.storage.types import matches_dkkd_identity
from tools.audit_ddk_gxp_canonical_candidates_readonly import _write_private_json
from tools.audit_ddk_gxp_smb_readonly_folder_pilot import check_configured_roots_readonly
from tools.audit_ddk_gxp_smb_readonly_root_shape import (
    SCHEMA as ROOT_SHAPE_SCHEMA,
    _EXACT_LEGACY_TOKEN, _NUMERIC_PAREN,
    summarize_root_direct_children, validate_source_and_full_report,
)
from tools.build_ddk_gxp_manual_review_queue import _private_input, build_review_queue
from tools.env_utils import parse_env_file


SCHEMA = "GXP_DDK_SMB_SECOND_LEVEL_SHAPE_READONLY_V1"
ROOT_ENTRY_BUDGET = 1000
PARENT_BUDGET = 500
NESTED_ENTRY_BUDGET = 20000


class DdkSecondLevelBlocked(ValueError):
    pass


def _require(ok: bool, why: str) -> None:
    if not ok:
        raise DdkSecondLevelBlocked(why)


def summarize_second_level(
    root_entries: Iterable[Any],
    ddk_targets: list[dict[str, Any]],
    scandir: Callable[[str], Iterable[Any]],
    *,
    root_budget: int = ROOT_ENTRY_BUDGET,
    parent_budget: int = PARENT_BUDGET,
    nested_budget: int = NESTED_ENTRY_BUDGET,
) -> tuple[dict[str, int], dict[str, int]]:
    """Count complete directory contents only; never return names or paths."""
    _require(len(ddk_targets) == 8
             and all(type(t["site_legacy_id"]) is int and t["site_legacy_id"] > 0
                     for t in ddk_targets)
             and 1 <= root_budget <= ROOT_ENTRY_BUDGET
             and 1 <= parent_budget <= PARENT_BUDGET
             and 1 <= nested_budget <= NESTED_ENTRY_BUDGET,
             "Invalid bounds or distinct source identity count")
    root: list[Any] = []
    iterator = iter(root_entries)
    try:
        for index, entry in enumerate(iterator):
            if index >= root_budget:
                raise DdkSecondLevelBlocked("Root metadata entry budget exceeded")
            root.append(entry)
    finally:
        closer = getattr(iterator, "close", None)
        if callable(closer):
            closer()

    direct = summarize_root_direct_children(
        root, [t["site_legacy_id"] for t in ddk_targets],
        max_entries=root_budget,
    )
    parents = [entry for entry in root if entry.is_dir()]
    _require(len(parents) <= parent_budget, "Too many parent folders for bounded scan")
    counts: Counter[str] = Counter()
    matched_by_site_id = {t["site_legacy_id"]: 0 for t in ddk_targets}
    for parent in parents:
        _require(isinstance(parent.path, str) and bool(parent.path),
                 "Missing entry-owned SMB folder path")
        children = iter(scandir(parent.path))
        try:
            for item in children:
                if counts["second_level_entries"] >= nested_budget:
                    raise DdkSecondLevelBlocked("Second-level metadata budget exceeded")
                counts["second_level_entries"] += 1
                if not item.is_dir():
                    counts["second_level_files_or_other"] += 1
                    continue
                counts["second_level_directories"] += 1
                label = item.name
                _require(isinstance(label, str), "Unexpected SMB directory label")
                if _EXACT_LEGACY_TOKEN.search(label):
                    counts["second_level_directories_with_legacy_numeric_token_shape"] += 1
                elif _NUMERIC_PAREN.search(label):
                    counts["second_level_directories_with_other_numeric_parentheses"] += 1
                else:
                    counts["second_level_directories_without_numeric_parentheses"] += 1
                for site_id in matched_by_site_id:
                    if matches_dkkd_identity(label, site_legacy_id=site_id):
                        matched_by_site_id[site_id] += 1
        finally:
            closer = getattr(children, "close", None)
            if callable(closer):
                closer()
        counts["first_level_parent_directories_scanned"] += 1

    counts["distinct_site_keys_without_second_level_name_match"] = sum(
        n == 0 for n in matched_by_site_id.values()
    )
    counts["distinct_site_keys_with_one_second_level_name_match"] = sum(
        n == 1 for n in matched_by_site_id.values()
    )
    counts["distinct_site_keys_with_multiple_second_level_name_matches"] = sum(
        n > 1 for n in matched_by_site_id.values()
    )
    counts["ddk_parents_with_any_second_level_name_match"] = sum(
        matched_by_site_id[t["site_legacy_id"]] > 0 for t in ddk_targets
    )
    return direct, dict(sorted(counts.items()))


def run_second_level_readonly(
    storage: SmbStorageService, targets: list[dict],
    recorded_shape: dict[str, Any],
) -> dict[str, Any]:
    _require(isinstance(storage, SmbStorageService)
             and storage.dkkd_root is not None and smbclient is not None,
             "Expected configured read-only SMB adapter")
    direct, counts = summarize_second_level(
        smbclient.scandir(storage.dkkd_root),
        targets,
        smbclient.scandir,
    )
    _require(recorded_shape.get("counts") == direct,
             "Configured DDK root direct-child structure drifted since prior audit")
    return {
        "schema": SCHEMA,
        "status": "COMPLETE_SECOND_LEVEL_METADATA_ONLY_NO_STORAGE_RESOLUTION",
        "approval_status": "NOT_APPROVED",
        "adapter_class": "synology_smb",
        "original_ddk_parent_count": len(targets),
        "distinct_source_site_keys": len({t["site_legacy_id"] for t in targets}),
        "root_direct_child_counts_verified": direct,
        "second_level_counts": counts,
        "root_entry_budget": ROOT_ENTRY_BUDGET,
        "parent_budget": PARENT_BUDGET,
        "second_level_entry_budget": NESTED_ENTRY_BUDGET,
        "complete_within_budgets": True,
        "folders_below_second_level_traversed": False,
        "file_contents_accessed": False,
        "database_connected": False,
        "database_writes": 0,
        "storage_writes": 0,
        "canonical_links_created": 0,
        "limitations": [
            "Second-level same-name shape is unverified folder metadata, not a binding or GxP legal source",
            "No folder path or other descriptive name is used as alternate identity key",
            "If exact token is absent here, deeper archives are NOT declared absent",
            "Incomplete or changed root aborts without partial root absence claims",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dossier-json", type=Path, required=True)
    ap.add_argument("--queue-json", type=Path, required=True)
    ap.add_argument("--readiness-json", type=Path, required=True)
    ap.add_argument("--full-probe-json", type=Path, required=True)
    ap.add_argument("--root-shape-json", type=Path, required=True)
    ap.add_argument("--runtime-env", type=Path, default=Path("/etc/gxp/runtime.env"))
    ap.add_argument("--details-json", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        paths = [args.dossier_json, args.queue_json, args.readiness_json,
                 args.full_probe_json, args.root_shape_json, args.details_json]
        _require(len({str(p.absolute()) for p in paths}) == 6
                 and len({p.parent.resolve() for p in paths}) == 1
                 and not args.details_json.exists()
                 and not args.details_json.is_symlink(),
                 "Protected source and new output must be distinct and in one directory")
        dossier = json.loads(_private_input(args.dossier_json))
        queue = json.loads(_private_input(args.queue_json))
        ready_bytes = _private_input(args.readiness_json)
        readiness = json.loads(ready_bytes)
        full_bytes = _private_input(args.full_probe_json)
        full = json.loads(full_bytes)
        shape_bytes = _private_input(args.root_shape_json)
        shape = json.loads(shape_bytes)
        _require(queue == build_review_queue(dossier), "Original source evidence changed")
        targets = validate_source_and_full_report(queue, readiness, full)
        _require(
            shape.get("schema") == ROOT_SHAPE_SCHEMA
            and shape.get("status") == "ROOT_DIRECT_CHILD_SHAPE_METADATA_ONLY"
            and shape.get("approval_status") == "NOT_APPROVED"
            and shape.get("adapter_class") == "synology_smb"
            and shape.get("original_source_ddk_parent_count") == 8
            and shape.get("source_readiness_sha256") == sha256(ready_bytes).hexdigest()
            and shape.get("prior_full_probe_sha256") == sha256(full_bytes).hexdigest()
            and shape.get("scan_complete_within_budget") is True
            and shape.get("database_connected") is False
            and shape.get("database_writes") == 0
            and shape.get("storage_writes") == 0
            and shape.get("storage_file_contents_accessed") is False
            and shape.get("canonical_links_created") == 0,
            "Prior protected root-shape observation invalid",
        )
        env = parse_env_file(args.runtime_env)
        _require(
            env.get("STORAGE_CLASS", "").strip() == "synology_smb"
            and bool(env.get("STORAGE_DKKD_ROOT", "").strip())
            and bool(env.get("STORAGE_INSPECTION_ROOT", "").strip())
            and bool(env.get("SMB_USERNAME", "").strip())
            and bool(env.get("SMB_PASSWORD", "").strip()),
            "Expected configured direct Synology adapter",
        )
        storage = create_storage_service_from_env(env)
        check_configured_roots_readonly(storage)
        report = run_second_level_readonly(storage, targets, shape)
        report["source_readiness_sha256"] = sha256(ready_bytes).hexdigest()
        report["prior_root_shape_sha256"] = sha256(shape_bytes).hexdigest()
        _write_private_json(args.details_json, report)
        public = {k: v for k, v in report.items() if k != "limitations"}
        print(json.dumps(public, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print("DDK_SMB_SECOND_LEVEL_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
