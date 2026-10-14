"""Read-only classification of original ĐĐK GxP reference observations.

NOT an approval engine. A legacy ID, matching GxP type and same Site do not
establish historical DDK version ownership or a valid canonical link.
The original 4-group cells and reference tokens remain unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate,
    BusinessEligibilityCertificateLink,
    BusinessEligibilityGxpReferenceEvidence,
    BusinessEligibilityGxpSourceGroup,
    Certificate,
    Site,
)
from tools.apply_ddk_gxp_provenance_rehearsal import checked_rehearsal_url
from tools.audit_ddk_idcc_physical import (
    MissingPhysicalEvidence, split_idcc_references,
)
from backend.app.domain.phase2_import import parse_int
from tools.env_utils import parse_env_file
from tools.plan_ddk_gxp_provenance_load import _source_value_digest
from tools.preflight_ddk_gxp_rehearsal import EXPECTED_DB, EXPECTED_REVISION


REPORT_SCHEMA = "GXP_DDK_CANONICAL_SOURCE_CANDIDATE_AUDIT_V1"
ROLE_COLUMNS = {"GMP": 15, "GLP": 19, "GSP": 23, "GDP": 27}
EXPECTED_WORKBOOK_SHA256 = "c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d"


class CandidateAuditBlocked(ValueError):
    """Unexpected source/model identity; cannot publish a plausible audit."""


def _require(ok: bool, msg: str) -> None:
    if not ok:
        raise CandidateAuditBlocked(msg)


def classify_candidates(
    session: Session,
    *,
    expected_workbook_sha256: str,
    expected_source_groups: int,
    expected_tokens: int,
) -> dict[str, Any]:
    """Pure SQL SELECT-based classification; accepts SQLite session for tests.

    A report never contains approved/eligible links. Per-token candidate UUIDs
    are *observations* only. The caller controls whether details are written
    privately, not sent to console or Git.
    """
    groups = list(session.scalars(
        select(BusinessEligibilityGxpSourceGroup).order_by(
            BusinessEligibilityGxpSourceGroup.source_row_number,
            BusinessEligibilityGxpSourceGroup.id_cc_excel_column,
        )
    ))
    refs = list(session.scalars(select(BusinessEligibilityGxpReferenceEvidence)))
    _require(
        len(groups) == expected_source_groups and len(refs) == expected_tokens,
        "Imported provenance population changed",
    )
    _require(
        all(g.source_workbook_sha256 == expected_workbook_sha256
            and g.source_sheet_name == "db.dkkd" for g in groups),
        "Source workbook identity/sheet drift",
    )

    by_ddk: dict[int, list[BusinessEligibilityGxpSourceGroup]] = defaultdict(list)
    by_group: dict[str, list[BusinessEligibilityGxpReferenceEvidence]] = defaultdict(list)
    for g in groups:
        _require(type(g.legacy_dkkd_id) is int and g.legacy_dkkd_id > 0,
                 "Source DDK identity missing")
        col = ROLE_COLUMNS.get(g.source_group)
        _require(col is not None and g.id_cc_excel_column == col
                 and (g.certificate_scope_excel_column,
                      g.applicable_standard_excel_column,
                      g.business_activity_excel_column) == (col + 1, col + 2, col + 3),
                 "Source GxP group physical column identity changed")
        values = [g.id_cc_raw, g.certificate_scope_raw, g.applicable_standard_raw,
                  g.business_activity_raw]
        _require(all(isinstance(x, str) for x in values)
                 and _source_value_digest(values) == g.source_values_sha256,
                 "Original source four-cell digest changed")
        by_ddk[g.legacy_dkkd_id].append(g)
    by_id = {g.id: g for g in groups}
    _require(len(by_id) == len(groups), "Duplicate source group UUID")
    for r in refs:
        _require(r.source_group_id in by_id and type(r.token_index) is int
                 and r.token_index > 0, "Orphan/invalid source token")
        by_group[r.source_group_id].append(r)
    for g in groups:
        tokens = sorted(by_group[g.id], key=lambda r: r.token_index)
        expected_raw_tokens = (
            list(split_idcc_references(g.id_cc_raw)) if g.id_cc_raw.strip() else []
        )
        _require(
            [r.token_index for r in tokens] == list(range(1, len(tokens) + 1))
            and [r.raw_token for r in tokens] == expected_raw_tokens
            and all(r.parsed_legacy_certificate_id == parse_int(r.raw_token)
                    for r in tokens),
            "Source ID CC token ordinal/text changed",
        )

    for ddk_id, items in by_ddk.items():
        _require(
            len(items) == 4
            and {x.source_group for x in items} == ROLE_COLUMNS.keys()
            and len({x.source_row_number for x in items}) == 1,
            "One DDK source ID has ambiguous or missing physical source groups",
        )

    canonical_ddks = {
        x.legacy_dkkd_id: x for x in session.scalars(
            select(BusinessEligibilityCertificate)
        ) if x.legacy_dkkd_id is not None
    }
    canonical_gxp = {
        x.legacy_certificate_id: x for x in session.scalars(
            select(Certificate)
        ) if x.legacy_certificate_id is not None
    }
    sites = {x.id: x for x in session.scalars(select(Site))}
    stored_links = session.scalar(
        select(func.count()).select_from(BusinessEligibilityCertificateLink)
    )
    counters: Counter[str] = Counter()
    details = []
    ids_seen: Counter[int] = Counter()
    for ddk_id, items in sorted(by_ddk.items()):
        ddk = canonical_ddks.get(ddk_id)
        if ddk is None:
            counters["source_ddk_canonical_missing"] += 1
        else:
            counters["source_ddk_canonical_present"] += 1
            owner_site = sites.get(ddk.site_id)
            if owner_site is None:
                counters["source_ddk_site_missing"] += 1
            elif owner_site.company_id != ddk.company_id:
                counters["ddk_site_company_mismatch"] += 1
            else:
                counters["ddk_site_company_consistent"] += 1

        for g in sorted(items, key=lambda x: x.id_cc_excel_column):
            for r in sorted(by_group[g.id], key=lambda x: x.token_index):
                role = g.source_group
                candidate_id = r.parsed_legacy_certificate_id
                candidate = canonical_gxp.get(candidate_id)
                flags = ["SOURCE_OBSERVATION_NOT_APPROVED"]
                if ddk is None:
                    flags.append("DDK_CANONICAL_MISSING")
                else:
                    site = sites.get(ddk.site_id)
                    if site is None:
                        flags.append("DDK_SITE_MISSING")
                    elif site.company_id != ddk.company_id:
                        flags.append("DDK_SITE_COMPANY_MISMATCH")
                if candidate_id is None:
                    flags.append("UNPARSED_SOURCE_ID_CC")
                    counters["id_cc_unparsed"] += 1
                elif candidate is None:
                    flags.append("CERTIFICATE_CANONICAL_MISSING")
                    counters["candidate_certificate_missing"] += 1
                else:
                    counters["candidate_certificate_found"] += 1
                    if candidate.certificate_type == role:
                        counters["certificate_type_exact"] += 1
                    else:
                        flags.append("CERTIFICATE_GXP_TYPE_DIFFERENT")
                        counters["certificate_type_different"] += 1
                    if ddk is not None:
                        if candidate.site_id == ddk.site_id:
                            counters["candidate_same_site"] += 1
                        else:
                            flags.append("CERTIFICATE_SITE_DIFFERENT")
                            counters["candidate_different_site"] += 1
                            cert_site = sites.get(candidate.site_id)
                            if cert_site is not None:
                                if cert_site.company_id == ddk.company_id:
                                    counters["cross_site_same_ddk_company_observed"] += 1
                                else:
                                    counters["cross_site_different_company_observed"] += 1
                ids_seen[candidate_id] += 1 if candidate_id is not None else 0
                for flag in flags[1:]:
                    counters["flag_" + flag] += 1
                counters["role_" + role] += 1
                details.append({
                    "legacy_dkkd_id": ddk_id,
                    "source_row_number": g.source_row_number,
                    "source_role": role,
                    "id_cc_excel_column": g.id_cc_excel_column,
                    "token_index": r.token_index,
                    "source_reference_id": r.id,
                    "parsed_legacy_certificate_id": candidate_id,
                    "observed_candidate_certificate_id": candidate.id if candidate else None,
                    "flags": flags,
                    "link_approval": "NOT_APPROVED",
                })
    _require(len(details) == len(refs), "Token conservation audit failure")
    duplicates = sum(n - 1 for n in ids_seen.values() if n > 1)
    return {
        "schema": REPORT_SCHEMA,
        "status": "SOURCE_CANDIDATE_OBSERVATIONS_ONLY_NO_LINK_APPROVAL",
        "approval_status": "NOT_APPROVED",
        "source_workbook_sha256": expected_workbook_sha256,
        "source_groups": len(groups),
        "source_tokens": len(refs),
        "source_ddk_ids": len(by_ddk),
        "recorded_canonical_gxp_link_rows_before": stored_links,
        "canonical_links_created": 0,
        "database_writes": 0,
        "repeated_candidate_id_extra_occurrences": duplicates,
        "counts": dict(sorted(counters.items())),
        "candidate_observations": details,
        "limitations": [
            "Matches are observations by raw legacy ID, not approved links",
            "Same Site and exact type do not prove business grant, coverage or version ownership",
            "No source token maps automatically to a CertificateVersion",
            "DDK issuance text cannot manufacture persisted BusinessEligibilityVersion history",
            "Original XLSB read uses accepted pyxlsb cached cells; Excel COM validation waived",
        ],
    }


def audit_rehearsal_db(database_url: str, *, sha: str,
                       expected_groups: int, expected_tokens: int) -> dict[str, Any]:
    # Fail closed on a non-local or alternate role/DB: callers must pass
    # checked_rehearsal_url from the pinned rehearsal runtime env.
    engine = create_engine(
        database_url, poolclass=NullPool,
        connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=30000"},
    )
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.exec_driver_sql("SET TRANSACTION READ ONLY")
                if conn.execute(text("SELECT current_database()")).scalar_one() != EXPECTED_DB:
                    raise CandidateAuditBlocked("Unexpected database name")
                if conn.execute(text("SHOW transaction_read_only")).scalar_one() != "on":
                    raise CandidateAuditBlocked("Server transaction is not read-only")
                revisions = list(conn.execute(
                    text("SELECT version_num FROM public.alembic_version")
                ).scalars())
                if revisions != [EXPECTED_REVISION]:
                    raise CandidateAuditBlocked("Unexpected Alembic revision")
                with Session(bind=conn) as session:
                    result = classify_candidates(
                        session, expected_workbook_sha256=sha,
                        expected_source_groups=expected_groups,
                        expected_tokens=expected_tokens,
                    )
                result["database_name"] = EXPECTED_DB
                result["alembic_revision"] = EXPECTED_REVISION
                result["transaction_read_only"] = True
                return result
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-env", type=Path, default=Path("/etc/gxp/runtime.env"))
    parser.add_argument("--expected-workbook-sha256", required=True)
    parser.add_argument("--expected-groups", type=int, required=True)
    parser.add_argument("--expected-tokens", type=int, required=True)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.expected_workbook_sha256 != EXPECTED_WORKBOOK_SHA256:
            raise CandidateAuditBlocked("Unexpected workbook identity")
        if (args.expected_groups, args.expected_tokens) != (3120, 861):
            raise CandidateAuditBlocked("Unexpected source population")
        url = checked_rehearsal_url(parse_env_file(args.runtime_env))
        report = audit_rehearsal_db(
            url, sha=args.expected_workbook_sha256,
            expected_groups=args.expected_groups,
            expected_tokens=args.expected_tokens,
        )
        if args.output_json is not None:
            if args.output_json.exists():
                raise CandidateAuditBlocked("Refuse to overwrite an existing private report")
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(args.output_json, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
        # Never emit raw source cells or private row-level identifiers to logs.
        safe = {k: v for k, v in report.items() if k != "candidate_observations"}
        print(json.dumps(safe, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        # Do not leak source values, DSN credentials or SQL error contents.
        if isinstance(exc, KeyboardInterrupt):
            raise
        print("DDK_CANDIDATE_AUDIT_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
