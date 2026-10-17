"""Read-only canonical-state projection used by B6H planning only."""
from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import Case, Certificate, ProductionLine, ProductionLineTransformation, Site
from backend.app.domain.production_line_population import (
    CANONICAL_STATE_SCHEMA_VERSION,
    SUPPORTED_ALEMBIC_REVISIONS,
    ProductionLinePlanningError,
    canonical_artifact_bytes,
    canonical_json_bytes,
)


REQUIRED_ALEMBIC_REVISION = "20260929_0017"
PROTECTED_DATABASE_NAMES = frozenset({"gxp_qlcl"})


def canonical_state_digest_pair(state: dict[str, Any]) -> tuple[str, str]:
    """Return semantic provenance SHA first, then exact serialized-file SHA."""
    return (
        sha256(canonical_json_bytes(state)).hexdigest(),
        sha256(canonical_artifact_bytes(state)).hexdigest(),
    )


def _value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def export_canonical_state(session: Session, *, require_read_only: bool = True) -> dict[str, Any]:
    """Project all B6H state using one semantic representation owner.

    B6J's guarded writer uses ``require_read_only=False`` only while it holds
    the target rows for an imminent all-or-nothing transaction.
    """
    database_name = session.execute(text("SELECT current_database()")).scalar_one()
    if not isinstance(database_name, str) or database_name in PROTECTED_DATABASE_NAMES:
        raise ProductionLinePlanningError("B6H canonical-state exporter refuses protected or invalid database")
    revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if revision not in SUPPORTED_ALEMBIC_REVISIONS:
        raise ProductionLinePlanningError("B6H canonical-state exporter requires an explicitly supported Alembic revision")
    read_only = session.execute(text("SHOW transaction_read_only")).scalar_one()
    if require_read_only and read_only != "on":
        raise ProductionLinePlanningError("B6H canonical-state exporter requires a PostgreSQL READ ONLY transaction")

    sites = [{"id": row.id, "legacy_site_id": row.legacy_site_id} for row in session.scalars(select(Site).order_by(Site.legacy_site_id, Site.id))]
    lines = [{"id": row.id, "site_id": row.site_id, "code": row.code, "effective_from": _value(row.effective_from), "effective_to": _value(row.effective_to), "row_version": row.row_version} for row in session.scalars(select(ProductionLine).order_by(ProductionLine.site_id, ProductionLine.code, ProductionLine.id))]
    cases = [{"id": row.id, "legacy_inspection_id": row.legacy_inspection_id, "site_id": row.site_id, "scope_code_raw": row.scope_code, "production_line_id": row.production_line_id, "row_version": row.row_version} for row in session.scalars(select(Case).where(Case.legacy_inspection_id.is_not(None)).order_by(Case.legacy_inspection_id))]
    certificates = [{"id": row.id, "legacy_certificate_id": row.legacy_certificate_id, "case_id": row.case_id, "site_id": row.site_id, "line_code_raw": row.line_code, "production_line_id": row.production_line_id, "row_version": row.row_version} for row in session.scalars(select(Certificate).where(Certificate.legacy_certificate_id.is_not(None)).order_by(Certificate.legacy_certificate_id))]
    transformations = [{"id": row.id, "site_id": row.site_id, "transformation_type": row.transformation_type, "effective_on": _value(row.effective_on), "row_version": row.row_version} for row in session.scalars(select(ProductionLineTransformation).order_by(ProductionLineTransformation.site_id, ProductionLineTransformation.effective_on, ProductionLineTransformation.id))]
    state = {
        "schema_version": CANONICAL_STATE_SCHEMA_VERSION,
        "exported_at": None,
        "source_database_identity": {"database_name": database_name, "dialect": "postgresql"},
        "source_alembic_revision": revision,
        "sites": sites,
        "existing_production_lines": lines,
        "cases": cases,
        "certificates": certificates,
        "physical_line_evidence": [],
        "transformations": transformations,
    }
    state["source_state_fingerprint"] = sha256(canonical_json_bytes(state)).hexdigest()
    return state
