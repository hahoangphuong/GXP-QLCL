"""Source-evidenced DDKD SMB root *configuration* identity diagnostic.

No SMB or PostgreSQL connections. Never returns configured UNC paths,
credentials or source Site/Case identifiers. The legacy DDKD folder basename
was proven by FILE_STORAGE_CONTRACT.md and LEGACY_SYSTEM_MAP.md:
ActiveWorkbook.Path\Chứng nhận ĐĐKKDD.
A basename comparison is observational, NOT an authorized root correction.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import unicodedata
from typing import Any

from tools.audit_ddk_gxp_canonical_candidates_readonly import _write_private_json
from tools.audit_ddk_gxp_smb_readonly_root_shape import (
    SCHEMA as ROOT_SHAPE_SCHEMA,
    validate_source_and_full_report,
)
from tools.audit_ddk_gxp_smb_second_level_readonly import SCHEMA as SECOND_LEVEL_SCHEMA
from tools.build_ddk_gxp_manual_review_queue import _private_input, build_review_queue
from tools.env_utils import parse_env_file

SCHEMA = "GXP_DDK_SMB_CONFIGURED_ROOT_PROVENANCE_READONLY_V1"
LEGACY_DDKD_LEAF = "Chứng nhận ĐĐKKDD"


class RootProvenanceBlocked(ValueError):
    pass


def _require(ok: bool, why: str) -> None:
    if not ok:
        raise RootProvenanceBlocked(why)


def _fold(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def unc_components(value: str) -> tuple[str, ...]:
    _require(isinstance(value, str) and value.startswith("\\\\"),
             "Expected UNC storage root")
    value = value.rstrip("\\/")
    _require(not "/" in value, "Unsupported root separator")
    parts = value[2:].split("\\")
    _require(len(parts) >= 2
             and all(p and p not in (".", "..") for p in parts),
             "Expected UNC host/share and normalized relative components")
    return tuple(_fold(part) for part in parts)


def assess_configured_roots(env: dict[str, str]) -> dict[str, Any]:
    """Return boolean shape only; never log or persist source UNC strings."""
    _require(env.get("STORAGE_CLASS", "").strip() == "synology_smb",
             "Adapter class mismatch")
    ddk = unc_components(env.get("STORAGE_DKKD_ROOT", ""))
    inspection = unc_components(env.get("STORAGE_INSPECTION_ROOT", ""))
    _require(bool(env.get("SMB_USERNAME", "").strip())
             and bool(env.get("SMB_PASSWORD", "").strip()),
             "Missing configured transport identity")
    template_raw = env.get("STORAGE_TEMPLATE_ROOT", "").strip()
    template = unc_components(template_raw) if template_raw else None
    expected = _fold(LEGACY_DDKD_LEAF)
    return {
        "ddk_root_leaf_matches_legacy_ddkd_directory": ddk[-1] == expected,
        "ddk_root_contains_legacy_ddkd_directory": expected in ddk[2:],
        "ddk_root_same_host_and_share_as_inspection": ddk[:2] == inspection[:2],
        "ddk_root_equals_inspection_root": ddk == inspection,
        "ddk_root_nested_under_inspection_root": (
            len(ddk) > len(inspection) and ddk[:len(inspection)] == inspection
        ),
        "inspection_root_nested_under_ddk_root": (
            len(inspection) > len(ddk) and inspection[:len(ddk)] == ddk
        ),
        "template_root_configured": template is not None,
        "ddk_root_equals_template_root": template is not None and ddk == template,
        "ddk_root_has_subdirectory_after_unc_share": len(ddk) >= 3,
    }


def verify_previous_source_evidence(
    dossier: dict[str, Any], queue: dict[str, Any], readiness: dict[str, Any],
    full: dict[str, Any], root: dict[str, Any], second: dict[str, Any],
    readiness_hash: str, full_hash: str, root_hash: str,
) -> None:
    _require(queue == build_review_queue(dossier), "Original source queue differs")
    targets = validate_source_and_full_report(queue, readiness, full)
    _require(len(targets) == 8, "Expected original DDK parent identities")
    _require(
        root.get("schema") == ROOT_SHAPE_SCHEMA
        and root.get("approval_status") == "NOT_APPROVED"
        and root.get("source_readiness_sha256") == readiness_hash
        and root.get("prior_full_probe_sha256") == full_hash
        and root.get("scan_complete_within_budget") is True
        and root.get("database_connected") is False
        and root.get("database_writes") == 0
        and root.get("storage_writes") == 0
        and root.get("canonical_links_created") == 0,
        "Original private root report differs",
    )
    first = root.get("counts")
    nested = second.get("second_level_counts")
    _require(
        isinstance(first, dict)
        and first.get("direct_child_directories") == 274
        and first.get("files_or_other_direct_entries") == 13
        and first.get("folders_without_numeric_parenthesis_token") == 274
        and isinstance(nested, dict)
        and nested.get("second_level_directories") == 657
        and nested.get("second_level_directories_without_numeric_parentheses") == 657
        and nested.get("first_level_parent_directories_scanned") == 274
        and second.get("schema") == SECOND_LEVEL_SCHEMA
        and second.get("status") == "COMPLETE_SECOND_LEVEL_METADATA_ONLY_NO_STORAGE_RESOLUTION"
        and second.get("root_direct_child_counts_verified") == first
        and second.get("prior_root_shape_sha256") == root_hash
        and second.get("source_readiness_sha256") == readiness_hash
        and second.get("approval_status") == "NOT_APPROVED"
        and second.get("complete_within_budgets") is True
        and second.get("file_contents_accessed") is False
        and second.get("database_connected") is False
        and second.get("database_writes") == 0
        and second.get("storage_writes") == 0
        and second.get("canonical_links_created") == 0,
        "Second-level protected shape differs",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dossier-json", type=Path, required=True)
    ap.add_argument("--queue-json", type=Path, required=True)
    ap.add_argument("--readiness-json", type=Path, required=True)
    ap.add_argument("--full-probe-json", type=Path, required=True)
    ap.add_argument("--root-shape-json", type=Path, required=True)
    ap.add_argument("--second-level-json", type=Path, required=True)
    ap.add_argument("--runtime-env", type=Path, default=Path("/etc/gxp/runtime.env"))
    ap.add_argument("--details-json", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        paths = [args.dossier_json, args.queue_json, args.readiness_json,
                 args.full_probe_json, args.root_shape_json,
                 args.second_level_json, args.details_json]
        _require(len({str(p.absolute()) for p in paths}) == 7
                 and len({p.parent.resolve() for p in paths}) == 1
                 and not args.details_json.exists()
                 and not args.details_json.is_symlink(),
                 "All protected source reports must differ from new private output")
        dossier = json.loads(_private_input(args.dossier_json))
        queue = json.loads(_private_input(args.queue_json))
        ready_bytes = _private_input(args.readiness_json)
        full_bytes = _private_input(args.full_probe_json)
        root_bytes = _private_input(args.root_shape_json)
        second_bytes = _private_input(args.second_level_json)
        verify_previous_source_evidence(
            dossier, queue, json.loads(ready_bytes), json.loads(full_bytes),
            json.loads(root_bytes), json.loads(second_bytes),
            sha256(ready_bytes).hexdigest(), sha256(full_bytes).hexdigest(),
            sha256(root_bytes).hexdigest(),
        )
        flags = assess_configured_roots(parse_env_file(args.runtime_env))
        report = {
            "schema": SCHEMA,
            "status": "DDK_CONFIGURED_ROOT_PROVENANCE_FLAGS_ONLY",
            "adapter_class": "synology_smb",
            "legacy_root_evidence": "FILE_STORAGE_CONTRACT_AND_LEGACY_SYSTEM_MAP",
            "original_ddk_parents": 8,
            "first_level_directories_without_legacy_tokens": 274,
            "second_level_directories_without_legacy_tokens": 657,
            "configured_root_flags": flags,
            "approval_status": "NOT_APPROVED",
            "root_config_changed": False,
            "database_connected": False,
            "storage_connected": False,
            "database_writes": 0,
            "storage_writes": 0,
            "canonical_links_created": 0,
            "limitations": [
                "Root basename match or mismatch is NOT proof of actual workbook deployment path",
                "Legacy root was relative to ActiveWorkbook.Path; workbook location not verified",
                "No UNC path, folder candidate, Site ID or alternative root can be inferred from these flags",
                "Do not auto-correct storage configuration or relax proven legacy resolver",
            ],
        }
        _write_private_json(args.details_json, report)
        print(json.dumps({k: v for k, v in report.items() if k != "limitations"},
                         ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print("DDK_ROOT_PROVENANCE_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
