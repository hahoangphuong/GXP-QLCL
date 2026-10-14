"""Read-only, bounded SMB folder-identity probe for private DDK GxP exceptions.

Only directly calls StorageService.resolve_dkkd_folder and
StorageService.resolve_inspection_folder. No binding lookup/service, SQL,
file reads, file writes to NAS, or approval. Local private output optional.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

from backend.app.db.enums import StorageResolutionStatus
from backend.app.storage.factory import create_storage_service_from_env
from backend.app.storage.smb import SmbStorageService
from tools.audit_ddk_gxp_canonical_candidates_readonly import _write_private_json
from tools.audit_ddk_gxp_storage_identity_readiness import SCHEMA as READINESS_SCHEMA
from tools.build_ddk_gxp_manual_review_queue import _private_input, build_review_queue
from tools.env_utils import parse_env_file


SCHEMA = "GXP_DDK_SMB_READONLY_FOLDER_IDENTITY_PILOT_V1"
_ALLOWED = {e.value for e in StorageResolutionStatus}


class SmbProbeBlocked(ValueError):
    """Fail closed without leaking confidential SMB paths or credentials."""


def _require(ok: bool, why: str) -> None:
    if not ok:
        raise SmbProbeBlocked(why)


def verified_lookup_targets(queue: dict[str, Any], readiness: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """Cross-check that every private lookup identity belongs to its original review.

    Accepts only persisted positive source keys; no display-name or folder
    guesses. Returns deduplicated DDK parent IDs and originating Case IDs.
    """
    _require(
        queue.get("status") == "PRIVATE_REVIEW_ONLY_NOT_APPROVED"
        and queue.get("link_approval") == "NOT_APPROVED"
        and queue.get("manual_review_status") == "PENDING_INDEPENDENT_EVIDENCE"
        and readiness.get("schema") == READINESS_SCHEMA
        and readiness.get("status") == "INPUT_IDENTITIES_ONLY_NO_STORAGE_PROBE"
        and readiness.get("approval_status") == "NOT_APPROVED"
        and readiness.get("database_writes") == 0
        and readiness.get("canonical_links_created") == 0
        and readiness.get("storage_roots_accessed") is False,
        "Source or lookup identity lacks read-only provenance",
    )
    reviews = queue["source_token_reviews"] + queue["ddk_company_reviews"]
    observed = readiness.get("private_lookup_input_evidence")
    _require(isinstance(observed, list) and len(reviews) == len(observed)
             and len(observed) == readiness.get("review_records"),
             "Private original review identity population changed")
    observed_by_key = {r["review_key"]: r for r in observed}
    _require(len(observed_by_key) == len(observed), "Duplicate lookup review")
    ddk: dict[str, dict] = {}
    cases: dict[str, dict] = {}
    for review in reviews:
        key = review["review_key"]
        record = observed_by_key.get(key)
        _require(record is not None
                 and record.get("link_approval") == "NOT_APPROVED"
                 and record.get("review_status") == "PENDING_INDEPENDENT_EVIDENCE",
                 "Missing original token lookup record")
        token = review.get("original_exception_evidence")
        company = review.get("original_company_exception_evidence")
        _require((token is None) != (company is None),
                 "Ambiguous original source review identity")
        source = token if token is not None else company
        ddk_info = record["ddk"]
        _require(
            ddk_info.get("site_id") == source.get("ddk_site_id")
            and isinstance(ddk_info.get("canonical_id"), str)
            and len(ddk_info["canonical_id"]) > 0,
            "DDK parent identity changed",
        )
        if company is not None:
            _require(ddk_info["canonical_id"] == company.get(
                "canonical_business_eligibility_certificate_id"),
                "DDK Company review canonical identity drift")
        existing_ddk = ddk.get(ddk_info["canonical_id"])
        if existing_ddk is not None:
            _require(existing_ddk == ddk_info, "Conflicting DDK lookup identity")
        else:
            ddk[ddk_info["canonical_id"]] = ddk_info

        cert_info = record.get("certificate_reference")
        case_info = record.get("originating_case_reference")
        if token is None:
            _require(cert_info is None and case_info is None,
                     "Company owner review may not infer Certificate or Case")
            continue
        _require(
            isinstance(cert_info, dict)
            and cert_info.get("certificate_id") == token.get("observed_certificate_id")
            and cert_info.get("certificate_site_id") == token.get("certificate_site_id")
            and cert_info.get("folder_resolution_contract") == "NOT_ASSIGNED_TO_CERTIFICATE",
            "Certificate was assigned a guessed folder or identity",
        )
        if token.get("certificate_case_id") is None:
            _require(case_info is None, "Case folder invented for administrative Certificate")
            continue
        _require(
            isinstance(case_info, dict)
            and case_info.get("case_id") == token["certificate_case_id"]
            and case_info.get("case_site_id") == token.get("case_site_id"),
            "Originating Case folder identity does not match original token",
        )
        old_case = cases.get(case_info["case_id"])
        if old_case is not None:
            _require(old_case == case_info, "Conflicting Case folder identity")
        else:
            cases[case_info["case_id"]] = case_info
    _require(len(ddk) == readiness.get("unique_ddk_count")
             and len(cases) == readiness.get("unique_originating_case_count"),
             "Distinct lookup parent counts changed")

    ddk_targets = []
    for id, value in sorted(ddk.items()):
        if value.get("lookup_input_classification") == (
            "DDK_SITE_IDENTITY_INPUT_AVAILABLE_UNPROBED"
        ):
            sid = value.get("site_legacy_id")
            _require(type(sid) is int and sid > 0, "Invalid DDK site key")
            ddk_targets.append({"parent_id": id, "site_legacy_id": sid})
    case_targets = []
    for id, value in sorted(cases.items()):
        if value.get("lookup_input_classification") == "CASE_LOOKUP_INPUT_AVAILABLE_UNPROBED":
            sid = value.get("case_site_legacy_id")
            year = value.get("source_year_observed")
            code = value.get("case_legacy_inspection_code")
            _require(type(sid) is int and sid > 0
                     and type(year) is int and 1900 <= year <= 2100
                     and isinstance(code, str) and code.strip()
                     and value.get("anchor_classification") in {
                         "REGISTRATION_SOURCE_YEAR_USABLE",
                         "INSPECTION_SOURCE_YEAR_PRESENT_REGISTRATION_UNAVAILABLE",
                     }, "Invalid originating Case source keys")
            case_targets.append({
                "parent_id": id, "site_legacy_id": sid, "year": year,
                "inspection_legacy_code": code,
            })
    return ddk_targets, case_targets


def run_bounded_probes(
    storage: SmbStorageService,
    ddk: list[dict], cases: list[dict],
    *, max_ddk: int, max_cases: int,
) -> dict[str, Any]:
    """Only the two named read-only adapter resolver methods are invoked."""
    _require(type(max_ddk) is int and 0 <= max_ddk <= 8
             and type(max_cases) is int and 0 <= max_cases <= 6
             and max_ddk + max_cases > 0,
             "Probe budget must be bounded and positive")
    _require(isinstance(storage, SmbStorageService), "Only approved SMB adapter")
    counts = Counter()
    private = []
    for item in ddk[:max_ddk]:
        result = storage.resolve_dkkd_folder(site_legacy_id=item["site_legacy_id"])
        status = result.status.value
        _require(status in _ALLOWED, "Unexpected DDK folder lookup status")
        counts["DDK_" + status.upper()] += 1
        private.append({
            "parent_type": "DDK", "parent_id": item["parent_id"],
            "lookup_input": {"site_legacy_id": item["site_legacy_id"]},
            "status": status, "candidate_count": result.candidate_count,
            "relative_path_private_unverified": result.relative_path,
            "source": "DIRECT_SMB_ADAPTER_NO_DB",
            "legal_approval": "NOT_APPROVED",
        })
    for item in cases[:max_cases]:
        result = storage.resolve_inspection_folder(
            year=item["year"], site_legacy_id=item["site_legacy_id"],
            inspection_legacy_code=item["inspection_legacy_code"],
        )
        status = result.status.value
        _require(status in _ALLOWED, "Unexpected Case folder lookup status")
        counts["CASE_" + status.upper()] += 1
        private.append({
            "parent_type": "ORIGINATING_CASE", "parent_id": item["parent_id"],
            "lookup_input": {
                "site_legacy_id": item["site_legacy_id"],
                "source_year": item["year"],
                "inspection_legacy_code": item["inspection_legacy_code"],
            },
            "status": status, "candidate_count": result.candidate_count,
            "relative_path_private_unverified": result.relative_path,
            "source": "DIRECT_SMB_ADAPTER_NO_DB",
            "legal_approval": "NOT_APPROVED",
        })
    return {
        "schema": SCHEMA,
        "status": "SMB_FOLDER_IDENTITY_OBSERVATIONS_UNVERIFIED",
        "approval_status": "NOT_APPROVED",
        "adapter_class": "synology_smb",
        "total_ddk_targets": len(ddk),
        "total_case_targets": len(cases),
        "ddk_lookups_attempted": min(len(ddk), max_ddk),
        "case_lookups_attempted": min(len(cases), max_cases),
        "ddk_not_probed": max(len(ddk) - max_ddk, 0),
        "case_not_probed": max(len(cases) - max_cases, 0),
        "counts": dict(sorted(counts.items())),
        "storage_folder_names_observed_only": True,
        "storage_file_contents_accessed": False,
        "storage_writes": 0,
        "database_connected": False,
        "database_writes": 0,
        "canonical_links_created": 0,
        "private_folder_observations": private,
        "limitations": [
            "A matching legacy folder name is not evidence of regulatory validity",
            "NOT_FOUND indicates only the inspected configured SMB root, not all archives",
            "A failed SMB transport aborts; never converted into NOT_FOUND",
            "No Certificate-specific folder mapping or historical coverage inferred",
            "Results not probed do not claim absence or presence of any storage item",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier-json", type=Path, required=True)
    parser.add_argument("--queue-json", type=Path, required=True)
    parser.add_argument("--readiness-json", type=Path, required=True)
    parser.add_argument("--runtime-env", type=Path, default=Path("/etc/gxp/runtime.env"))
    parser.add_argument("--max-ddk", type=int, default=1)
    parser.add_argument("--max-cases", type=int, default=1)
    parser.add_argument("--details-json", type=Path)
    args = parser.parse_args(argv)
    try:
        paths = [args.dossier_json, args.queue_json, args.readiness_json]
        if args.details_json:
            paths.append(args.details_json)
        _require(len({p.resolve() for p in paths}) == len(paths)
                 and len({p.parent.resolve() for p in paths}) == 1,
                 "Inputs and output must be distinct in the same protected folder")
        dossier = json.loads(_private_input(args.dossier_json))
        queue = json.loads(_private_input(args.queue_json))
        readiness_bytes = _private_input(args.readiness_json)
        readiness = json.loads(readiness_bytes)
        _require(queue == build_review_queue(dossier), "Private queue differs from original dossier")
        _require(queue.get("source_tokens_checked") == 861
                 and queue.get("source_exception_token_records") == 8
                 and queue.get("ddk_company_review_records") == 1,
                 "Unexpected source population")
        ddk, cases = verified_lookup_targets(queue, readiness)
        _require(len(ddk) == 8 and len(cases) == 6,
                 "Unexpected eligible storage lookup parent identities")
        _require(type(args.max_ddk) is int and 0 <= args.max_ddk <= 8
                 and type(args.max_cases) is int and 0 <= args.max_cases <= 6
                 and args.max_ddk + args.max_cases > 0,
                 "Invalid bounded SMB probe budget")
        if args.details_json:
            _require(not args.details_json.exists() and not args.details_json.is_symlink(),
                     "Refuse to overwrite private SMB report")
        env = parse_env_file(args.runtime_env)
        _require(env.get("STORAGE_CLASS", "").strip() == "synology_smb"
                 and bool(env.get("STORAGE_INSPECTION_ROOT", "").strip())
                 and bool(env.get("STORAGE_DKKD_ROOT", "").strip())
                 and bool(env.get("SMB_USERNAME", "").strip())
                 and bool(env.get("SMB_PASSWORD", "").strip()),
                 "Expected configured private direct Synology SMB storage")
        # Factory is the real production adapter, but we invoke ONLY the two
        # *read-only* resolver methods. No BindingLookupService or Session.
        storage = create_storage_service_from_env(env)
        _require(isinstance(storage, SmbStorageService), "Storage adapter mismatch")
        report = run_bounded_probes(
            storage, ddk, cases, max_ddk=args.max_ddk, max_cases=args.max_cases
        )
        if args.details_json:
            _write_private_json(args.details_json, report)
        safe = {k: v for k, v in report.items()
                if k not in {"private_folder_observations", "limitations"}}
        safe["readiness_report_sha256"] = sha256(readiness_bytes).hexdigest()
        print(json.dumps(safe, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        # Never leak UNC path, token, SMB user, credentials or original tokens
        # through a raw traceback; retain error class only.
        print("DDK_SMB_READONLY_PROBE_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
