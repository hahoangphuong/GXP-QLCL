from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.enums import DocumentVariantType
from backend.app.db.models.phase1 import TemplateBinding, TemplateDefinition
from backend.app.document.seed_runtime import (
    TemplateSeedError,
    TemplateSeedSummary,
    load_template_seed_artifact,
    seed_default_template_metadata,
)
from backend.app.project_paths import phase_artifact_path


class TemplateMetadataReadinessError(RuntimeError):
    """Raised when the canonical Phase 5 metadata subset is absent or drifted."""


@dataclass(frozen=True)
class TemplateMetadataReadinessSummary:
    canonical_template_definitions: int
    canonical_template_bindings: int


def _canonical_payload() -> dict[str, list[dict[str, object]]]:
    return load_template_seed_artifact(phase_artifact_path("phase5", "template_seed.curated.json"))


def _unique_definition(session: Session, seed: dict[str, object]) -> TemplateDefinition:
    rows = list(
        session.scalars(
            select(TemplateDefinition).where(
                TemplateDefinition.family_code == str(seed["family_code"]),
                TemplateDefinition.template_name == str(seed["template_name"]),
            )
        )
    )
    if len(rows) != 1:
        raise TemplateMetadataReadinessError(
            "Canonical template_definition must exist exactly once for "
            f"family_code={seed['family_code']!r}, template_name={seed['template_name']!r}; found {len(rows)}."
        )
    return rows[0]


def _assert_definition_matches(definition: TemplateDefinition, seed: dict[str, object]) -> None:
    expected = {
        "document_type_code": str(seed["document_type_code"]),
        "source_application": str(seed["source_application"]),
        "storage_scope": str(seed["storage_scope"]),
        "legacy_host_procedure": str(seed["legacy_host_procedure"]) if seed["legacy_host_procedure"] is not None else None,
        "legacy_case_number": int(seed["legacy_case_number"]) if seed["legacy_case_number"] is not None else None,
        "variant_type": DocumentVariantType(str(seed["variant_type"])),
        "template_pattern": str(seed["template_pattern"]) if seed["template_pattern"] is not None else None,
        "bookmark_contract": str(seed["bookmark_contract_json"]) if seed["bookmark_contract_json"] is not None else None,
        "is_active": True,
    }
    mismatches = [field_name for field_name, value in expected.items() if getattr(definition, field_name) != value]
    if mismatches:
        raise TemplateMetadataReadinessError(
            "Canonical template_definition does not match curated metadata for "
            f"family_code={seed['family_code']!r}, template_name={seed['template_name']!r}: "
            + ", ".join(mismatches)
        )


def _unique_binding(session: Session, definition: TemplateDefinition, seed: dict[str, object]) -> TemplateBinding:
    statement = select(TemplateBinding).where(
        TemplateBinding.family_code == str(seed["family_code"]),
        TemplateBinding.template_definition_id == definition.id,
        TemplateBinding.storage_scope == str(seed["storage_scope"]),
    )
    statement = statement.where(
        TemplateBinding.gxp_type.is_(None)
        if seed["gxp_type"] is None
        else TemplateBinding.gxp_type == str(seed["gxp_type"])
    )
    statement = statement.where(
        TemplateBinding.legacy_mode.is_(None)
        if seed["legacy_mode"] is None
        else TemplateBinding.legacy_mode == str(seed["legacy_mode"])
    )
    rows = list(session.scalars(statement))
    if len(rows) != 1:
        raise TemplateMetadataReadinessError(
            "Canonical template_binding must exist exactly once for "
            f"family_code={seed['family_code']!r}, template_name={seed['template_name']!r}; found {len(rows)}."
        )
    return rows[0]


def verify_default_template_metadata(session: Session) -> TemplateMetadataReadinessSummary:
    """Read-only verification of the canonical subset; runtime extensions are allowed."""
    payload = _canonical_payload()
    definitions_by_key: dict[tuple[str, str], TemplateDefinition] = {}
    for seed in payload["template_definitions"]:
        definition = _unique_definition(session, seed)
        _assert_definition_matches(definition, seed)
        definitions_by_key[(str(seed["family_code"]), str(seed["template_name"]))] = definition

    for seed in payload["template_bindings"]:
        key = (str(seed["family_code"]), str(seed["template_name"]))
        definition = definitions_by_key.get(key)
        if definition is None:
            raise TemplateMetadataReadinessError(
                "Canonical template_binding references a definition missing from the curated seed artifact for "
                f"family_code={seed['family_code']!r}, template_name={seed['template_name']!r}."
            )
        binding = _unique_binding(session, definition, seed)
        if not binding.is_active:
            raise TemplateMetadataReadinessError(
                "Canonical template_binding is inactive for "
                f"family_code={seed['family_code']!r}, template_name={seed['template_name']!r}."
            )

    return TemplateMetadataReadinessSummary(
        canonical_template_definitions=len(payload["template_definitions"]),
        canonical_template_bindings=len(payload["template_bindings"]),
    )


def bootstrap_default_template_metadata(session: Session) -> tuple[TemplateSeedSummary, TemplateMetadataReadinessSummary]:
    """Seed the canonical subset, then prove it before the caller commits the transaction."""
    try:
        seed_summary = seed_default_template_metadata(session)
    except TemplateSeedError:
        raise
    readiness_summary = verify_default_template_metadata(session)
    return seed_summary, readiness_summary
