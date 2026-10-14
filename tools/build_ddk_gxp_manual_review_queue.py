"""Build a private, evidence-only review queue from an existing DDK ID CC dossier.

Offline JSON consumer: no database, web service or workbook access. Every
candidate remains NOT_APPROVED, regardless of matching original identifiers.
The queue preserves separate workbook-token and owning-Company case identities.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

from tools.audit_ddk_gxp_canonical_candidates_readonly import _write_private_json
from tools.summarize_ddk_gxp_exception_overlap import summarize_dossier


SCHEMA = "GXP_DDK_EXCEPTION_MANUAL_REVIEW_QUEUE_V1"
REVIEW_STATUS = "PENDING_INDEPENDENT_EVIDENCE"


class QueueBlocked(ValueError):
    """The private dossier or output location cannot be trusted."""


def build_review_queue(dossier: dict[str, Any]) -> dict[str, Any]:
    """Pure transformation, always calls the existing full aggregate validator."""
    summary = summarize_dossier(dossier)
    repeats = {
        row["parsed_legacy_certificate_id"]: row
        for row in dossier["repeated_candidate_id_details"]
    }
    queue = []
    for token in dossier["exception_token_details"]:
        flags = set(token["flags"])
        if "CERTIFICATE_SITE_DIFFERENT" in flags:
            required = ["VERIFY_ORIGINAL_CERTIFICATE_SITE_AND_STATED_COVERAGE"]
        else:
            required = []
        if "CERTIFICATE_CASE_SITE_DIFFERENT" in flags:
            required.append("VERIFY_ORIGINATING_CASE_AND_CERTIFICATE_SITE_IDENTITY")
        if "DDK_SITE_COMPANY_MISMATCH" in flags:
            required.append("VERIFY_DDK_COMPANY_AGAINST_SOURCE_AND_SITE_OWNER")
        if not required:
            required.append("REVIEW_OTHER_RECORDED_IDENTITY_EXCEPTION")
        original = deepcopy(token)
        repeat = repeats.get(original["parsed_legacy_certificate_id"])
        queue.append({
            "kind": "SOURCE_TOKEN_REVIEW",
            "review_key": "SOURCE_TOKEN:" + original["source_reference_id"],
            "review_status": REVIEW_STATUS,
            "link_approval": "NOT_APPROVED",
            "required_independent_evidence_checks": required,
            "observed_reference_frequency": (
                {
                    "source_occurrences": repeat["occurrence_count"],
                    "distinct_source_ddk_count": repeat["distinct_source_ddk_count"],
                } if repeat else {"source_occurrences": 1, "distinct_source_ddk_count": 1}
            ),
            "original_exception_evidence": original,
        })
    queue.sort(key=lambda item: (
        item["original_exception_evidence"]["legacy_dkkd_id"],
        item["original_exception_evidence"]["source_row_number"],
        item["original_exception_evidence"]["id_cc_excel_column"],
        item["original_exception_evidence"]["token_index"],
        item["review_key"],
    ))
    companies = []
    for company in dossier["ddk_company_exception_details"]:
        companies.append({
            "kind": "DDK_COMPANY_OWNERSHIP_REVIEW",
            "review_key": "DDK_COMPANY:" + str(company["legacy_dkkd_id"]),
            "review_status": REVIEW_STATUS,
            "link_approval": "NOT_APPROVED",
            "required_independent_evidence_checks": [
                "VERIFY_ORIGINAL_DDK_APPLICANT_COMPANY",
                "VERIFY_CANONICAL_SITE_OWNING_COMPANY_AND_HISTORICAL_IDENTITY",
            ],
            "original_company_exception_evidence": deepcopy(company),
        })
    companies.sort(key=lambda item: item["original_company_exception_evidence"]["legacy_dkkd_id"])
    site_keys = [
        x for x in queue if "CERTIFICATE_SITE_DIFFERENT" in
        x["original_exception_evidence"]["flags"]
        or "CERTIFICATE_CASE_SITE_DIFFERENT" in
        x["original_exception_evidence"]["flags"]
    ]
    if (
        len(site_keys) != (summary["cross_site_only"] + summary["case_site_only"]
                           + summary["cross_site_and_case_site_overlap"])
        or len(queue) != (len(dossier["exception_token_details"]))
        or len(companies) != summary["ddk_company_mismatch_count"]
        or summary["canonical_links_created"] != 0
    ):
        raise QueueBlocked("Review queue cardinalities differ from validated private dossier")
    return {
        "schema": SCHEMA,
        "status": "PRIVATE_REVIEW_ONLY_NOT_APPROVED",
        "source_workbook_sha256": dossier["source_workbook_sha256"],
        "source_dossier_schema": dossier["schema"],
        "source_tokens_checked": summary["source_tokens_checked"],
        "source_exception_token_records": len(queue),
        "site_or_case_exception_token_records": len(site_keys),
        "ddk_company_review_records": len(companies),
        "cross_site_only": summary["cross_site_only"],
        "case_site_only": summary["case_site_only"],
        "both_site_and_case_flags": summary["cross_site_and_case_site_overlap"],
        "original_canonical_links_before": summary["recorded_canonical_link_rows_before"],
        "canonical_links_created": 0,
        "database_writes": 0,
        "link_approval": "NOT_APPROVED",
        "manual_review_status": REVIEW_STATUS,
        "source_token_reviews": queue,
        "ddk_company_reviews": companies,
        "limitations": [
            "Original Excel ID CC observations are not approved Certificate links",
            "One source token with two flags is one token review, not two",
            "One DDK Company conflict is a separate ownership review, not a synthetic token",
            "Version/scope evidence is descriptive, not proof of grant or Site coverage",
            "Repeated IDs across different DDKs are context, not automatic exceptions",
        ],
    }


def _private_input(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise QueueBlocked("Private dossier must be a regular non-symlink file")
    info = path.stat()
    if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.geteuid():
        raise QueueBlocked("Private dossier must be owned by caller and mode 0600")
    return path.read_bytes()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dossier-json", type=Path, required=True)
    p.add_argument("--queue-json", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        input_path, output_path = args.dossier_json, args.queue_json
        if input_path.resolve() == output_path.resolve():
            raise QueueBlocked("Must not overwrite original private dossier")
        if input_path.parent.resolve() != output_path.parent.resolve():
            raise QueueBlocked("Private output must share dossier's protected directory")
        parent_stat = output_path.parent.stat()
        if (parent_stat.st_uid != os.geteuid()
                or stat.S_IMODE(parent_stat.st_mode) & 0o077):
            raise QueueBlocked("Output directory is not private")
        if output_path.exists() or output_path.is_symlink():
            raise QueueBlocked("Refuse to replace prior private review queue")
        raw = _private_input(input_path)
        queue = build_review_queue(json.loads(raw))
        _write_private_json(output_path, queue)
        safe = {
            key: queue[key] for key in (
                "schema", "status", "source_tokens_checked",
                "source_exception_token_records", "site_or_case_exception_token_records",
                "ddk_company_review_records", "cross_site_only", "case_site_only",
                "both_site_and_case_flags", "canonical_links_created", "database_writes",
                "link_approval", "manual_review_status",
            )
        }
        safe["input_dossier_sha256"] = sha256(raw).hexdigest()
        print(json.dumps(safe, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print("DDK_PRIVATE_REVIEW_QUEUE_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
