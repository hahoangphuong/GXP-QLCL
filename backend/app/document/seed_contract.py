from __future__ import annotations

import json
from dataclasses import dataclass

from backend.app.db.enums import DocumentVariantType
from backend.app.document.registry import TemplateRegistryEntry


@dataclass(frozen=True)
class TemplateDefinitionSeed:
    family_code: str
    document_type_code: str
    source_application: str
    storage_scope: str
    legacy_host_procedure: str
    legacy_case_number: int | None
    variant_type: str
    template_name: str
    template_pattern: str
    bookmark_contract_json: str
    notes: str | None = None


@dataclass(frozen=True)
class TemplateBindingSeed:
    family_code: str
    template_name: str
    gxp_type: str | None
    legacy_mode: str | None
    storage_scope: str
    selection_notes: str | None = None


@dataclass(frozen=True)
class PayloadBuilderFieldSpec:
    field_name: str
    source_procedure: str
    sensitivity: str = "normal"


@dataclass(frozen=True)
class PayloadBuilderSpec:
    family_code: str
    source_procedures: tuple[str, ...]
    fields: tuple[PayloadBuilderFieldSpec, ...]
    copy_forward_required: bool
    notes: str | None = None


SENSITIVE_FIELD_PATTERNS = (
    "SoCMT",
    "NgaycapCMT",
    "NoicapCMT",
    "SoTK",
    "NganHang",
)


def derive_document_type_code(family_code: str) -> str:
    return family_code.lower()


def derive_variant_type(source_application: str) -> DocumentVariantType:
    if source_application == "Excel":
        return DocumentVariantType.EDITABLE_XLSX
    return DocumentVariantType.EDITABLE_DOCX


def normalize_template_name(template_pattern: str) -> str:
    if " / " in template_pattern:
        return template_pattern.split(" / ", 1)[0].strip()
    return template_pattern.strip()


def infer_gxp_type(template_pattern: str) -> str | None:
    if "{GP}" in template_pattern:
        return "{GP}"
    return None


def infer_legacy_mode(family_code: str, template_pattern: str) -> str | None:
    lowered = template_pattern.lower()
    if "moi/tai" in lowered:
        return "moi_or_tai"
    if "(moi)" in lowered:
        return "moi"
    if family_code == "STATUS_CONFIRMATION_LETTER":
        return "cho_kiem_tra_or_cho_cap_chung_chi"
    return None


def field_sensitivity(field_name: str) -> str:
    for pattern in SENSITIVE_FIELD_PATTERNS:
        if pattern.lower() in field_name.lower():
            return "sensitive"
    return "normal"


def build_template_definition_seeds(entries: tuple[TemplateRegistryEntry, ...]) -> tuple[TemplateDefinitionSeed, ...]:
    seeds: list[TemplateDefinitionSeed] = []
    for entry in entries:
        bookmark_contract = {
            "bookmarks": list(entry.bookmarks),
            "copy_forward_dependencies": [
                {
                    "source_family_code": dependency.source_family_code,
                    "condition": dependency.condition,
                    "source_bookmarks": list(dependency.source_bookmarks),
                }
                for dependency in entry.copy_forward_dependencies
            ],
        }
        seeds.append(
            TemplateDefinitionSeed(
                family_code=entry.family_code,
                document_type_code=derive_document_type_code(entry.family_code),
                source_application=entry.source_application,
                storage_scope=entry.storage_scope,
                legacy_host_procedure=entry.legacy_host_procedure,
                legacy_case_number=entry.legacy_case_numbers[0] if len(entry.legacy_case_numbers) == 1 else None,
                variant_type=derive_variant_type(entry.source_application).value,
                template_name=normalize_template_name(entry.template_pattern),
                template_pattern=entry.template_pattern,
                bookmark_contract_json=json.dumps(bookmark_contract, ensure_ascii=False, sort_keys=True),
                notes=entry.notes,
            )
        )
    return tuple(seeds)


def build_template_binding_seeds(entries: tuple[TemplateRegistryEntry, ...]) -> tuple[TemplateBindingSeed, ...]:
    bindings: list[TemplateBindingSeed] = []
    for entry in entries:
        bindings.append(
            TemplateBindingSeed(
                family_code=entry.family_code,
                template_name=normalize_template_name(entry.template_pattern),
                gxp_type=infer_gxp_type(entry.template_pattern),
                legacy_mode=entry.selection_legacy_mode or infer_legacy_mode(entry.family_code, entry.template_pattern),
                storage_scope=entry.storage_scope,
                selection_notes=entry.notes,
            )
        )
    return tuple(bindings)


def build_payload_builder_specs(entries: tuple[TemplateRegistryEntry, ...]) -> tuple[PayloadBuilderSpec, ...]:
    spec_index: dict[str, PayloadBuilderSpec] = {}
    for entry in entries:
        fields = tuple(
            PayloadBuilderFieldSpec(
                field_name=bookmark,
                source_procedure=entry.population_procedures[0] if entry.population_procedures else entry.legacy_host_procedure,
                sensitivity=field_sensitivity(bookmark),
            )
            for bookmark in entry.bookmarks
        )
        next_spec = PayloadBuilderSpec(
            family_code=entry.family_code,
            source_procedures=entry.population_procedures,
            fields=fields,
            copy_forward_required=bool(entry.copy_forward_dependencies),
            notes=entry.notes,
        )
        existing = spec_index.get(entry.family_code)
        if existing is None:
            spec_index[entry.family_code] = next_spec
            continue
        merged_fields = {
            field.field_name: field
            for field in (*existing.fields, *next_spec.fields)
        }
        merged_procedures = tuple(
            dict.fromkeys((*existing.source_procedures, *next_spec.source_procedures))
        )
        merged_notes = existing.notes
        if next_spec.notes and next_spec.notes != existing.notes:
            merged_notes = f"{existing.notes} | {next_spec.notes}" if existing.notes else next_spec.notes
        spec_index[entry.family_code] = PayloadBuilderSpec(
            family_code=entry.family_code,
            source_procedures=merged_procedures,
            fields=tuple(merged_fields[field_name] for field_name in sorted(merged_fields, key=str.lower)),
            copy_forward_required=(existing.copy_forward_required or next_spec.copy_forward_required),
            notes=merged_notes,
        )
    return tuple(spec_index[family_code] for family_code in sorted(spec_index, key=str.lower))
