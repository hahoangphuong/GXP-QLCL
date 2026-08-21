from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from backend.app.project_paths import phase_artifact_path
from backend.app.db.enums import DocumentVariantType
from backend.app.db.models.phase1 import TemplateBinding, TemplateDefinition


class TemplateSeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class TemplateSeedSummary:
    template_definitions_created: int
    template_definitions_updated: int
    template_bindings_created: int
    template_bindings_updated: int


def load_template_seed_artifact(path: Path) -> dict[str, list[dict[str, object]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TemplateSeedError("Template seed artifact must be a JSON object")
    template_definitions = payload.get("template_definitions")
    template_bindings = payload.get("template_bindings")
    if not isinstance(template_definitions, list) or not isinstance(template_bindings, list):
        raise TemplateSeedError("Template seed artifact must include list keys template_definitions and template_bindings")
    return {
        "template_definitions": template_definitions,
        "template_bindings": template_bindings,
    }


def _single_template_definition_match(session: Session, seed: dict[str, object]) -> TemplateDefinition | None:
    stmt: Select[tuple[TemplateDefinition]] = select(TemplateDefinition).where(
        TemplateDefinition.family_code == str(seed["family_code"]),
        TemplateDefinition.template_name == str(seed["template_name"]),
    )
    matches = list(session.execute(stmt).scalars())
    if len(matches) > 1:
        raise TemplateSeedError(
            "Ambiguous template_definition rows for "
            f"family_code={seed['family_code']!r}, template_name={seed['template_name']!r}"
        )
    return matches[0] if matches else None


def _apply_template_definition_fields(template_definition: TemplateDefinition, seed: dict[str, object]) -> bool:
    changed = False
    desired_values = {
        "document_type_code": str(seed["document_type_code"]),
        "source_application": str(seed["source_application"]),
        "storage_scope": str(seed["storage_scope"]),
        "legacy_host_procedure": str(seed["legacy_host_procedure"]) if seed["legacy_host_procedure"] is not None else None,
        "legacy_case_number": int(seed["legacy_case_number"]) if seed["legacy_case_number"] is not None else None,
        "variant_type": DocumentVariantType(str(seed["variant_type"])),
        "template_pattern": str(seed["template_pattern"]) if seed["template_pattern"] is not None else None,
        "bookmark_contract": str(seed["bookmark_contract_json"]) if seed["bookmark_contract_json"] is not None else None,
        "notes": str(seed["notes"]) if seed["notes"] is not None else None,
        "is_active": True,
    }
    for field_name, desired in desired_values.items():
        if getattr(template_definition, field_name) != desired:
            setattr(template_definition, field_name, desired)
            changed = True
    return changed


def upsert_template_definitions(session: Session, seeds: list[dict[str, object]]) -> tuple[int, int]:
    created = 0
    updated = 0
    for seed in seeds:
        existing = _single_template_definition_match(session, seed)
        if existing is None:
            template_definition = TemplateDefinition(
                family_code=str(seed["family_code"]),
                template_name=str(seed["template_name"]),
                document_type_code=str(seed["document_type_code"]),
                source_application=str(seed["source_application"]),
                storage_scope=str(seed["storage_scope"]),
                legacy_host_procedure=(
                    str(seed["legacy_host_procedure"]) if seed["legacy_host_procedure"] is not None else None
                ),
                legacy_case_number=int(seed["legacy_case_number"]) if seed["legacy_case_number"] is not None else None,
                variant_type=DocumentVariantType(str(seed["variant_type"])),
                template_pattern=str(seed["template_pattern"]) if seed["template_pattern"] is not None else None,
                bookmark_contract=(
                    str(seed["bookmark_contract_json"]) if seed["bookmark_contract_json"] is not None else None
                ),
                notes=str(seed["notes"]) if seed["notes"] is not None else None,
                is_active=True,
            )
            session.add(template_definition)
            session.flush()
            created += 1
            continue
        if _apply_template_definition_fields(existing, seed):
            session.flush()
            updated += 1
    return created, updated


def _template_binding_match(
    session: Session,
    *,
    template_definition_id: str,
    seed: dict[str, object],
) -> TemplateBinding | None:
    stmt: Select[tuple[TemplateBinding]] = select(TemplateBinding).where(
        TemplateBinding.family_code == str(seed["family_code"]),
        TemplateBinding.template_definition_id == template_definition_id,
        TemplateBinding.storage_scope == str(seed["storage_scope"]),
    )
    if seed["gxp_type"] is None:
        stmt = stmt.where(TemplateBinding.gxp_type.is_(None))
    else:
        stmt = stmt.where(TemplateBinding.gxp_type == str(seed["gxp_type"]))
    if seed["legacy_mode"] is None:
        stmt = stmt.where(TemplateBinding.legacy_mode.is_(None))
    else:
        stmt = stmt.where(TemplateBinding.legacy_mode == str(seed["legacy_mode"]))
    matches = list(session.execute(stmt).scalars())
    if len(matches) > 1:
        raise TemplateSeedError(
            "Ambiguous template_binding rows for "
            f"family_code={seed['family_code']!r}, template_name={seed['template_name']!r}"
        )
    return matches[0] if matches else None


def _apply_template_binding_fields(template_binding: TemplateBinding, seed: dict[str, object]) -> bool:
    changed = False
    desired_values = {
        "is_active": True,
    }
    for field_name, desired in desired_values.items():
        if getattr(template_binding, field_name) != desired:
            setattr(template_binding, field_name, desired)
            changed = True
    return changed


def upsert_template_bindings(session: Session, seeds: list[dict[str, object]]) -> tuple[int, int]:
    created = 0
    updated = 0
    for seed in seeds:
        template_definition = _single_template_definition_match(
            session,
            {
                "family_code": seed["family_code"],
                "template_name": seed["template_name"],
            },
        )
        if template_definition is None:
            raise TemplateSeedError(
                "Template binding seed references missing template_definition for "
                f"family_code={seed['family_code']!r}, template_name={seed['template_name']!r}"
            )
        existing = _template_binding_match(
            session,
            template_definition_id=template_definition.id,
            seed=seed,
        )
        if existing is None:
            template_binding = TemplateBinding(
                family_code=str(seed["family_code"]),
                template_definition_id=template_definition.id,
                gxp_type=str(seed["gxp_type"]) if seed["gxp_type"] is not None else None,
                legacy_mode=str(seed["legacy_mode"]) if seed["legacy_mode"] is not None else None,
                storage_scope=str(seed["storage_scope"]),
                is_active=True,
            )
            session.add(template_binding)
            session.flush()
            created += 1
            continue
        if _apply_template_binding_fields(existing, seed):
            session.flush()
            updated += 1
    return created, updated


def seed_template_metadata(
    session: Session,
    artifact_payload: dict[str, list[dict[str, object]]],
) -> TemplateSeedSummary:
    definition_created, definition_updated = upsert_template_definitions(
        session,
        artifact_payload["template_definitions"],
    )
    binding_created, binding_updated = upsert_template_bindings(
        session,
        artifact_payload["template_bindings"],
    )
    return TemplateSeedSummary(
        template_definitions_created=definition_created,
        template_definitions_updated=definition_updated,
        template_bindings_created=binding_created,
        template_bindings_updated=binding_updated,
    )


def seed_default_template_metadata(session: Session) -> TemplateSeedSummary:
    payload = load_template_seed_artifact(phase_artifact_path("phase5", "template_seed.curated.json"))
    return seed_template_metadata(session, payload)
