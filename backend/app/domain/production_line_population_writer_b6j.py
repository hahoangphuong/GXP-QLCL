"""Guarded, all-or-nothing B6J ProductionLine plan writer.

This owner deliberately accepts only a sealed B6J plan.  It has no inference,
upsert, resume, or force mode: a second application is stale by design.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import Case, Certificate, ProductionLine, Site
from backend.app.domain.production_line_canonical_state import PROTECTED_DATABASE_NAMES, SUPPORTED_ALEMBIC_REVISIONS, canonical_state_digest_pair, export_canonical_state
from backend.app.domain.production_line_population_b6j import PLAN_SCHEMA_VERSION, REQUIRED_ALEMBIC_REVISION, plan_digest

REHEARSAL_DATABASE_NAME = "gxp_legacy_rehearsal"
REHEARSAL_ADVISORY_LOCK_NAME = "gxp:b6j:production-line-population:rehearsal-apply:v1"


class ProductionLinePopulationApplyError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProductionLinePopulationApplyError(message)


def _require_clean_session(session: Session) -> None:
    _require(not session.new and not session.dirty and not session.deleted, "B6J writer requires a clean SQLAlchemy Session")


def _validate_plan(plan: Mapping[str, Any]) -> None:
    _require(plan.get("schema_version") == PLAN_SCHEMA_VERSION, "B6J writer received an unsupported plan schema")
    _require(plan.get("plan_sha256") == plan_digest(plan), "B6J writer plan SHA256 does not match plan content")
    _require(plan.get("source_alembic_revision") in SUPPORTED_ALEMBIC_REVISIONS, "B6J writer plan has an unsupported Alembic revision")
    for field in ("legacy_snapshot_sha256", "canonical_state_sha256", "candidate_set_sha256"):
        _require(isinstance(plan.get(field), str) and len(plan[field]) == 64, f"B6J writer plan has invalid {field}")
    for field in (
        "candidate_set_roster_sha256",
        "candidate_set_roster_content_sha256",
        "candidate_set_roster_schema_version",
        "candidate_set_roster_artifact_kind",
        "candidate_set_roster_planner_version",
    ):
        _require(isinstance(plan.get(field), str) and plan[field], f"B6J writer plan lacks immutable {field}")
    _require(plan.get("candidate_set_roster_content_sha256_verified") is True, "B6J writer plan has unverified roster content")
    _require(isinstance(plan.get("candidate_set_roster_item_count"), int) and plan["candidate_set_roster_item_count"] > 0 and plan["candidate_set_roster_item_count"] == len(plan.get("candidates", [])), "B6J writer roster cardinality differs from sealed candidates")
    _require(not plan.get("transformation_actions"), "B6J writer refuses ProductionLine transformations")
    _require(not plan.get("scope_actions"), "B6J writer refuses scope lifecycle writes")
    _require(not plan.get("certificate_relationship_actions"), "B6J writer refuses CertificateRelationship writes")

    # A self-consistent digest is not an authorization to redirect a link to
    # a different line. Reconcile every writable link with its sealed candidate.
    items = plan.get("candidates")
    _require(isinstance(items, list) and all(isinstance(item, Mapping) for item in items), "B6J plan candidate records are invalid")
    candidates = {item.get("candidate_key"): item for item in items}
    _require(len(candidates) == len(items) and None not in candidates, "B6J plan candidate identities are duplicate or missing")
    for field, source_field in (("case_links", "source_case_ids"), ("certificate_links", "source_certificate_ids")):
        records = plan.get(field)
        _require(isinstance(records, list), f"B6J plan {field} records are invalid")
        for record in records:
            _require(isinstance(record, Mapping), f"B6J plan {field} record is invalid")
            classification = record.get("classification")
            if classification not in {"LINK_TO_NEW_LINE", "LINK_TO_EXISTING_LINE"}:
                continue
            candidate = candidates.get(record.get("candidate_key"))
            _require(candidate is not None, "B6J writer link candidate is missing")
            required_class = "CREATE_NEW_PRODUCTION_LINE" if classification == "LINK_TO_NEW_LINE" else "MAP_TO_EXISTING_PRODUCTION_LINE"
            _require(candidate.get("classification") == required_class, "B6J link and candidate classifications disagree")
            _require(record.get("expected_site_id") == candidate.get("canonical_site_id") and record.get("expected_site_id") is not None, "B6J link crosses candidate Site")
            _require(record.get("canonical_line_code") == candidate.get("canonical_line_code"), "B6J link code differs from candidate")
            _require(record.get("legacy_id") in (candidate.get(source_field) or []), "B6J link source is absent from candidate evidence")
            destination = candidate.get("proposed_production_line_id") if classification == "LINK_TO_NEW_LINE" else candidate.get("existing_production_line_id")
            _require(destination is not None and record.get("planned_production_line_id") == destination, "B6J link target differs from sealed candidate")



def _validate_target_mode(
    plan: Mapping[str, Any], *, expected_database_name: str, apply: bool, allow_rehearsal_dry_run: bool,
    allow_rehearsal_apply: bool = False,
) -> None:
    """Permit the protected rehearsal target only for an explicit rollback path."""
    _require(isinstance(apply, bool), "B6J writer apply flag must be boolean")
    _require(isinstance(allow_rehearsal_dry_run, bool), "B6J writer rehearsal dry-run flag must be boolean")
    _require(isinstance(allow_rehearsal_apply, bool), "B6J writer rehearsal apply flag must be boolean")
    _require(not (allow_rehearsal_dry_run and allow_rehearsal_apply), "B6J rehearsal overrides are mutually exclusive")
    _require(isinstance(expected_database_name, str) and expected_database_name.strip(), "B6J expected database name is required")
    identity = plan.get("source_database_identity")
    _require(isinstance(identity, Mapping), "B6J plan has no source database identity")
    if expected_database_name == REHEARSAL_DATABASE_NAME:
        _require((apply and allow_rehearsal_apply) or (not apply and allow_rehearsal_dry_run), "B6J rehearsal operation lacks its explicit authorization")
        _require(expected_database_name == REHEARSAL_DATABASE_NAME, "B6J rehearsal override requires the exact rehearsal database")
        _require(identity.get("database_name") == REHEARSAL_DATABASE_NAME and identity.get("dialect") == "postgresql", "B6J rehearsal plan database identity differs from target")
        return
    _require(not allow_rehearsal_dry_run and not allow_rehearsal_apply, "B6J rehearsal override requires the exact rehearsal database")
    _require(expected_database_name not in PROTECTED_DATABASE_NAMES | {"postgres", REHEARSAL_DATABASE_NAME}, "B6J writer refuses protected database")
    if apply:
        _require(
            expected_database_name.startswith(("gxp_b6j_test_", "gxp_b6c_test_")),
            "B6J non-rehearsal apply is limited to a disposable gxp_b6j_test_ or gxp_b6c_test_ database",
        )


def _validate_authoritative_rehearsal_plan(plan: Mapping[str, Any]) -> None:
    identity = plan.get("source_database_identity")
    _require(plan.get("candidate_set_roster_item_count") == 386 and len(plan.get("candidates", [])) == 386, "B6J rehearsal plan must bind exactly 386 candidates")
    _require(isinstance(identity, Mapping) and identity.get("database_name") == REHEARSAL_DATABASE_NAME and identity.get("dialect") == "postgresql", "B6J rehearsal plan database identity differs from target")
    _require(plan.get("source_alembic_revision") == REQUIRED_ALEMBIC_REVISION, "B6J protected rehearsal remains pinned to exact Alembic 20260929_0017")


def _verify_target(session: Session, *, expected_database_name: str, expected_revision: str) -> None:
    _require(isinstance(expected_database_name, str) and expected_database_name.strip(), "B6J expected database name is required")
    _require(session.bind is not None and session.bind.dialect.name == "postgresql", "B6J writer requires PostgreSQL")
    _require(session.execute(text("SELECT current_database()")).scalar_one() == expected_database_name, "B6J writer connected to an unexpected database")
    _require(expected_revision in SUPPORTED_ALEMBIC_REVISIONS, "B6J writer plan revision is not supported")
    _require(session.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none() == expected_revision, "B6J writer target Alembic revision differs from sealed plan")


def _lock_link_target(session: Session, record: Mapping[str, Any], *, certificate: bool) -> Case | Certificate:
    model = Certificate if certificate else Case
    row = session.scalar(select(model).where(model.id == record["canonical_record_id"]).with_for_update())
    _require(row is not None, "B6J writer target record disappeared")
    _require(row.site_id == record["expected_site_id"], "B6J writer target Site changed")
    _require(row.production_line_id == record["expected_production_line_id"], "B6J writer target ProductionLine link changed")
    _require(row.row_version == record["expected_row_version"], "B6J writer target version changed")
    raw = row.line_code if certificate else row.scope_code
    _require(raw == record["expected_canonical_raw_line_code"], "B6J writer compatibility line source changed")
    return row


def _prepared(session: Session, plan: Mapping[str, Any], *, expected_database_name: str, apply: bool, allow_rehearsal_dry_run: bool, allow_rehearsal_apply: bool) -> tuple[list[Mapping[str, Any]], list[tuple[Mapping[str, Any], Case | Certificate, bool]]]:
    _require_clean_session(session)
    _validate_plan(plan)
    _validate_target_mode(plan, expected_database_name=expected_database_name, apply=apply, allow_rehearsal_dry_run=allow_rehearsal_dry_run, allow_rehearsal_apply=allow_rehearsal_apply)
    if expected_database_name == REHEARSAL_DATABASE_NAME:
        _validate_authoritative_rehearsal_plan(plan)
    _verify_target(session, expected_database_name=expected_database_name, expected_revision=plan["source_alembic_revision"])
    identity = plan.get("source_database_identity")
    _require(isinstance(identity, Mapping) and identity.get("database_name") == expected_database_name, "B6J plan database identity differs from target")
    current_state = export_canonical_state(session, require_read_only=False)
    current_semantic_sha, _ = canonical_state_digest_pair(current_state)
    _require(current_semantic_sha == plan["canonical_state_sha256"], "B6J writer global canonical state changed")
    creates = [item for item in plan.get("candidates", []) if item.get("classification") == "CREATE_NEW_PRODUCTION_LINE"]
    links = [(item, False) for item in plan.get("case_links", []) if item.get("classification") in {"LINK_TO_NEW_LINE", "LINK_TO_EXISTING_LINE"}]
    links.extend((item, True) for item in plan.get("certificate_links", []) if item.get("classification") in {"LINK_TO_NEW_LINE", "LINK_TO_EXISTING_LINE"})
    candidates = {item.get("candidate_key"): item for item in plan.get("candidates", [])}
    prepared_links: list[tuple[Mapping[str, Any], Case | Certificate, bool]] = []
    deduplicated: dict[tuple[bool, object], tuple[Mapping[str, Any], bool]] = {}
    for record, certificate in links:
        candidate = candidates.get(record.get("candidate_key"))
        _require(candidate is not None, "B6J writer link candidate is missing")
        target_key = (certificate, record.get("canonical_record_id"))
        previous = deduplicated.get(target_key)
        if previous is not None:
            _require(previous[0].get("planned_production_line_id") == record.get("planned_production_line_id") and previous[0].get("expected_site_id") == record.get("expected_site_id"), "B6J writer has conflicting duplicate canonical write targets")
            continue
        deduplicated[target_key] = (record, certificate)
    for record, certificate in deduplicated.values():
        target = _lock_link_target(session, record, certificate=certificate)
        prepared_links.append((record, target, certificate))
    for candidate in candidates.values():
        if candidate.get("classification") != "MAP_TO_EXISTING_PRODUCTION_LINE":
            continue
        existing = session.scalar(
            select(ProductionLine).where(ProductionLine.id == candidate.get("existing_production_line_id")).with_for_update()
        )
        _require(
            existing is not None and existing.site_id == candidate.get("canonical_site_id")
            and existing.code == candidate.get("canonical_line_code"),
            "B6J existing ProductionLine identity or Site changed",
        )
    for item in creates:
        _require(item.get("canonical_site_id") and item.get("proposed_production_line_id") and item.get("effective_from"), "B6J writer create candidate is incomplete")
        _require(session.scalar(select(Site.id).where(Site.id == item["canonical_site_id"]).with_for_update()) is not None, "B6J writer candidate Site disappeared")
        _require(session.get(ProductionLine, item["proposed_production_line_id"]) is None, "B6J writer plan was already applied or ProductionLine UUID is occupied")
        _require(session.scalar(select(ProductionLine.id).where(ProductionLine.site_id == item["canonical_site_id"], ProductionLine.code == item["canonical_line_code"])) is None, "B6J writer unexpected same-Site ProductionLine appeared")
    return creates, prepared_links


def _write_prepared(session: Session, plan: Mapping[str, Any], creates: list[Mapping[str, Any]], links: list[tuple[Mapping[str, Any], Case | Certificate, bool]], *, apply: bool) -> dict[str, Any]:
    """Run the shared real write path; caller owns rollback or commit."""
    created: dict[str, ProductionLine] = {}
    for item in creates:
        line = ProductionLine(id=item["proposed_production_line_id"], site_id=item["canonical_site_id"], code=item["canonical_line_code"], effective_from=date.fromisoformat(item["effective_from"]))
        session.add(line); created[item["candidate_key"]] = line
    session.flush()
    case_links = certificate_links = 0
    for record, target, certificate in links:
        candidate_id = record["planned_production_line_id"]
        _require(candidate_id is not None, "B6J writer link has no ProductionLine target")
        target.production_line_id = candidate_id
        if certificate: certificate_links += 1
        else: case_links += 1
    session.flush()
    return {"status": "APPLIED" if apply else "DRY_RUN", "created_production_lines": len(creates), "linked_cases": case_links, "linked_certificates": certificate_links, "blocked_candidates": sum(item.get("classification", "").startswith("BLOCKED_") for item in plan.get("candidates", [])), "blocked_cases": sum(item.get("classification", "").startswith("BLOCKED_") for item in plan.get("case_links", [])), "blocked_certificates": sum(item.get("classification", "").startswith("BLOCKED_") for item in plan.get("certificate_links", []))}


def _verify_protected_precommit(session: Session, plan: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    """Audit actual in-transaction state; never trust iteration counters alone."""
    for records, model in ((plan["case_links"], Case), (plan["certificate_links"], Certificate)):
        for record in records:
            if record.get("classification", "").startswith("BLOCKED_") or record.get("classification") == "NOT_APPLICABLE":
                row = session.get(model, record.get("canonical_record_id")) if record.get("canonical_record_id") else None
                if row is not None:
                    _require(row.production_line_id == record.get("expected_production_line_id"), "B6J protected apply changed a blocked record")


_OUT_OF_SCOPE_TABLES = (
    "production_line_transformation", "production_line_transformation_member",
    "case_scope_phase", "case_scope_revision", "case_scope_revision_block",
    "case_scope_revision_selection", "case_scope_revision_unkeyed_entry",
    "certificate_relationship",
)


def _database_audit_counts(session: Session) -> dict[str, Any]:
    return {
        "production_lines": session.scalar(select(func.count()).select_from(ProductionLine)),
        "linked_cases": session.scalar(select(func.count()).select_from(Case).where(Case.production_line_id.is_not(None))),
        "linked_certificates": session.scalar(select(func.count()).select_from(Certificate).where(Certificate.production_line_id.is_not(None))),
        "out_of_scope": {name: session.execute(text(f"SELECT count(*) FROM {name}")).scalar_one() for name in _OUT_OF_SCOPE_TABLES},
    }


def _verify_database_audit(session: Session, plan: Mapping[str, Any], before: Mapping[str, Any], *, precommit: bool) -> dict[str, Any]:
    after = _database_audit_counts(session)
    creates = [item for item in plan["candidates"] if item.get("classification") == "CREATE_NEW_PRODUCTION_LINE"]
    expected_case = {item["canonical_record_id"]: item["planned_production_line_id"] for item in plan["case_links"] if item.get("classification", "").startswith("LINK_")}
    expected_certificate = {item["canonical_record_id"]: item["planned_production_line_id"] for item in plan["certificate_links"] if item.get("classification", "").startswith("LINK_")}
    for label, expected, model in (("Case", expected_case, Case), ("Certificate", expected_certificate, Certificate)):
        for target_id, line_id in expected.items():
            row = session.get(model, target_id)
            _require(row is not None and row.production_line_id == line_id, f"B6J {label} target audit differs from plan")
    for item in creates:
        row = session.get(ProductionLine, item["proposed_production_line_id"])
        _require(row is not None and row.site_id == item["canonical_site_id"] and row.code == item["canonical_line_code"] and row.effective_from == date.fromisoformat(item["effective_from"]), "B6J ProductionLine target audit differs from plan")
    _verify_protected_precommit(session, plan, {})
    _require(after["production_lines"] - before["production_lines"] == len(creates), "B6J ProductionLine database delta differs from plan")
    _require(after["linked_cases"] - before["linked_cases"] == len(expected_case), "B6J Case database delta differs from plan")
    _require(after["linked_certificates"] - before["linked_certificates"] == len(expected_certificate), "B6J Certificate database delta differs from plan")
    _require(after["out_of_scope"] == before["out_of_scope"], "B6J protected apply changed an out-of-scope table")
    return {"expected_created_production_lines": len(creates), "actual_created_production_lines_delta": after["production_lines"] - before["production_lines"], "expected_case_links": len(expected_case), "actual_case_links_delta": after["linked_cases"] - before["linked_cases"], "expected_certificate_links": len(expected_certificate), "actual_certificate_links_delta": after["linked_certificates"] - before["linked_certificates"], "planned_line_rows_verified": len(creates), "planned_case_targets_verified": len(expected_case), "planned_certificate_targets_verified": len(expected_certificate), "out_of_scope_unchanged": True, "phase": "precommit" if precommit else "postcommit"}


def _protected_rehearsal_apply(session: Session, plan: Mapping[str, Any], *, expected_database_name: str) -> dict[str, Any]:
    _require_clean_session(session)
    with session.begin():
        session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
        _require(session.execute(text("SHOW transaction_isolation")).scalar_one().lower() == "serializable", "B6J rehearsal apply requires SERIALIZABLE isolation")
        session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": REHEARSAL_ADVISORY_LOCK_NAME})
        creates, links = _prepared(session, plan, expected_database_name=expected_database_name, apply=True, allow_rehearsal_dry_run=False, allow_rehearsal_apply=True)
        before = _database_audit_counts(session)
        pre_state = export_canonical_state(session, require_read_only=False)
        pre_semantic_sha, pre_artifact_sha = canonical_state_digest_pair(pre_state)
        result = _write_prepared(session, plan, creates, links, apply=True)
        result["precommit_audit"] = _verify_database_audit(session, plan, before, precommit=True)
    try:
        with Session(session.bind) as audit_session:
            result["postcommit_audit"] = _verify_database_audit(audit_session, plan, before, precommit=False)
            state = export_canonical_state(audit_session, require_read_only=False)
            semantic_sha, artifact_sha = canonical_state_digest_pair(state)
            result.update({"pre_apply_canonical_state_sha256": pre_semantic_sha, "pre_apply_canonical_artifact_sha256": pre_artifact_sha, "post_apply_canonical_state_sha256": semantic_sha, "post_apply_canonical_artifact_sha256": artifact_sha, "target_database": expected_database_name})
    except Exception as exc:
        return {**result, "status": "APPLIED_POST_AUDIT_FAILED", "post_apply_audit_error": str(exc), "target_database": expected_database_name}
    return result


def guarded_apply(session: Session, plan: Mapping[str, Any], *, expected_database_name: str, apply: bool, allow_rehearsal_dry_run: bool = False, allow_rehearsal_apply: bool = False) -> dict[str, Any]:
    """Exercise the actual path, rolling it back unless explicit ``apply`` is true."""
    if expected_database_name == REHEARSAL_DATABASE_NAME and apply:
        _validate_plan(plan)
        _validate_target_mode(plan, expected_database_name=expected_database_name, apply=apply, allow_rehearsal_dry_run=allow_rehearsal_dry_run, allow_rehearsal_apply=allow_rehearsal_apply)
        return _protected_rehearsal_apply(session, plan, expected_database_name=expected_database_name)
    _require_clean_session(session)
    with session.begin_nested() as transaction:
        creates, links = _prepared(session, plan, expected_database_name=expected_database_name, apply=apply, allow_rehearsal_dry_run=allow_rehearsal_dry_run, allow_rehearsal_apply=allow_rehearsal_apply)
        result = _write_prepared(session, plan, creates, links, apply=apply)
        result["would_create_production_lines"] = result["created_production_lines"]
        result["would_link_cases"] = result["linked_cases"]
        result["would_link_certificates"] = result["linked_certificates"]
        if not apply:
            transaction.rollback()
        return result
