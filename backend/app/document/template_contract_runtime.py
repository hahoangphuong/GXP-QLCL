from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from backend.app.project_paths import phase_artifact_path
from backend.app.document.service_contract import DocumentPayloadField


class TemplateContractRuntimeError(RuntimeError):
    pass


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": WORD_NS}


@dataclass(frozen=True)
class TemplateContractFieldResolution:
    field_name: str
    resolution_type: str
    target_bookmarks: tuple[str, ...]
    evidence: str


@dataclass(frozen=True)
class TemplateContractFamily:
    family_code: str
    compatibility_status: str
    copy_forward_dependencies: tuple[dict[str, object], ...]
    field_resolutions: tuple[TemplateContractFieldResolution, ...]
    unresolved_fields: tuple[str, ...]
    unmatched_real_bookmarks: tuple[str, ...]


@dataclass(frozen=True)
class TemplateScalarReplacementPlan:
    family_code: str
    mode: str
    bookmark_replacements: dict[str, str]
    resolved_input_fields: tuple[str, ...]
    passthrough_input_fields: tuple[str, ...]
    template_variant_key: str | None = None


@dataclass(frozen=True)
class TemplateVariantContract:
    variant_key: str
    template_name: str
    bookmarks: tuple[str, ...]
    allowed_payload_fields: tuple[str, ...]
    exclusive_bookmarks: tuple[str, ...]
    field_mappings: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class FamilyVariantContracts:
    family_code: str
    variants: tuple[TemplateVariantContract, ...]


def load_template_contract_reconciliation(path: Path) -> tuple[TemplateContractFamily, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    families: list[TemplateContractFamily] = []
    for item in payload["families"]:
        resolutions = tuple(
            TemplateContractFieldResolution(
                field_name=field["field_name"],
                resolution_type=field["resolution_type"],
                target_bookmarks=tuple(field["target_bookmarks"]),
                evidence=field["evidence"],
            )
            for field in item["field_resolutions"]
        )
        families.append(
            TemplateContractFamily(
                family_code=item["family_code"],
                compatibility_status=item["compatibility_status"],
                copy_forward_dependencies=tuple(item.get("copy_forward_dependencies", [])),
                field_resolutions=resolutions,
                unresolved_fields=tuple(item.get("unresolved_fields", [])),
                unmatched_real_bookmarks=tuple(item.get("unmatched_real_bookmarks", [])),
            )
        )
    return tuple(families)


def load_default_template_contract_reconciliation() -> tuple[TemplateContractFamily, ...]:
    return load_template_contract_reconciliation(phase_artifact_path("phase5", "template_contract_reconciled.json"))


def load_family_variant_contracts(path: Path) -> FamilyVariantContracts:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return FamilyVariantContracts(
        family_code=payload["family_code"],
        variants=tuple(
            _load_template_variant_contract(item)
            for item in payload["variants"]
        ),
    )


def _load_template_variant_contract(item: dict[str, object]) -> TemplateVariantContract:
    raw_field_mappings = item.get("field_mappings")
    if isinstance(raw_field_mappings, dict):
        field_mappings = {
            str(field_name): tuple(str(bookmark) for bookmark in bookmarks)
            for field_name, bookmarks in raw_field_mappings.items()
        }
    else:
        field_mappings = {
            str(field_name): (str(field_name),)
            for field_name in item["allowed_payload_fields"]
        }
    return TemplateVariantContract(
        variant_key=item["variant_key"],
        template_name=item["template_name"],
        bookmarks=tuple(item["bookmarks"]),
        allowed_payload_fields=tuple(item["allowed_payload_fields"]),
        exclusive_bookmarks=tuple(item["exclusive_bookmarks"]),
        field_mappings=field_mappings,
    )


def load_default_dkkd_variant_contracts() -> FamilyVariantContracts:
    return load_family_variant_contracts(phase_artifact_path("phase5", "dkkd_template_variants.json"))


def load_default_bbtd_variant_contracts() -> FamilyVariantContracts:
    return load_family_variant_contracts(phase_artifact_path("phase5", "bbtd_template_variants.json"))


def get_template_contract_family(
    families: tuple[TemplateContractFamily, ...],
    family_code: str,
) -> TemplateContractFamily | None:
    matches = [family for family in families if family.family_code == family_code]
    if len(matches) > 1:
        raise TemplateContractRuntimeError(f"Ambiguous template contract family for family_code={family_code!r}")
    return matches[0] if matches else None


def _is_exact_only_family(family: TemplateContractFamily) -> bool:
    if family.unresolved_fields:
        return False
    if not family.field_resolutions:
        return False
    return all(resolution.resolution_type == "exact" for resolution in family.field_resolutions)


def build_scalar_replacement_plan(
    families: tuple[TemplateContractFamily, ...],
    family_code: str,
    payload_fields: tuple[DocumentPayloadField, ...],
) -> TemplateScalarReplacementPlan:
    family = get_template_contract_family(families, family_code)
    if family is None or not _is_exact_only_family(family):
        replacements = {field.field_name: field.value for field in payload_fields}
        field_names = tuple(sorted(replacements))
        return TemplateScalarReplacementPlan(
            family_code=family_code,
            mode="payload_passthrough",
            bookmark_replacements=replacements,
            resolved_input_fields=(),
            passthrough_input_fields=field_names,
            template_variant_key=None,
        )

    resolution_index = {resolution.field_name: resolution for resolution in family.field_resolutions}
    replacements: dict[str, str] = {}
    resolved_fields: list[str] = []
    passthrough_fields: list[str] = []
    for field in payload_fields:
        resolution = resolution_index.get(field.field_name)
        if resolution is None:
            replacements[field.field_name] = field.value
            passthrough_fields.append(field.field_name)
            continue
        for target_bookmark in resolution.target_bookmarks:
            replacements[target_bookmark] = field.value
        resolved_fields.append(field.field_name)
    return TemplateScalarReplacementPlan(
        family_code=family_code,
        mode="contract_exact",
        bookmark_replacements=replacements,
        resolved_input_fields=tuple(sorted(dict.fromkeys(resolved_fields))),
        passthrough_input_fields=tuple(sorted(dict.fromkeys(passthrough_fields))),
        template_variant_key=None,
    )


def _extract_document_bookmarks_from_docx_bytes(template_bytes: bytes) -> tuple[str, ...]:
    with ZipFile(BytesIO(template_bytes), "r") as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    names = [
        bookmark.attrib.get(f"{{{WORD_NS}}}name")
        for bookmark in root.findall(".//w:bookmarkStart", NSMAP)
    ]
    bookmarks = sorted({name for name in names if name and not name.startswith("_")}, key=str.lower)
    return tuple(bookmarks)


def _detect_template_variant(
    family_contract: FamilyVariantContracts,
    template_bytes: bytes,
) -> TemplateVariantContract:
    template_bookmarks = set(_extract_document_bookmarks_from_docx_bytes(template_bytes))
    for variant in family_contract.variants:
        if set(variant.bookmarks) == template_bookmarks:
            return variant
    raise TemplateContractRuntimeError(
        f"{family_contract.family_code} template bytes did not match any known variant contract; fail closed."
    )


def _build_variant_exact_plan(
    family_code: str,
    payload_fields: tuple[DocumentPayloadField, ...],
    *,
    template_bytes: bytes,
    family_contract: FamilyVariantContracts,
) -> TemplateScalarReplacementPlan:
    variant = _detect_template_variant(family_contract, template_bytes)
    disallowed = sorted(
        {
            field.field_name
            for field in payload_fields
            if field.field_name not in variant.allowed_payload_fields
        }
    )
    if disallowed:
        raise TemplateContractRuntimeError(
            f"Template variant {variant.variant_key!r} does not allow payload fields: {', '.join(disallowed)}"
        )

    replacements: dict[str, str] = {}
    resolved_fields: list[str] = []
    for field in payload_fields:
        targets = variant.field_mappings.get(field.field_name)
        if not targets:
            raise TemplateContractRuntimeError(
                f"Template variant {variant.variant_key!r} does not define field mapping for {field.field_name!r}"
            )
        for target_bookmark in targets:
            replacements[target_bookmark] = field.value
        resolved_fields.append(field.field_name)
    return TemplateScalarReplacementPlan(
        family_code=family_code,
        mode="contract_variant_exact",
        bookmark_replacements=replacements,
        resolved_input_fields=tuple(sorted(dict.fromkeys(resolved_fields))),
        passthrough_input_fields=(),
        template_variant_key=variant.variant_key,
    )


def build_scalar_replacement_plan_for_template(
    families: tuple[TemplateContractFamily, ...],
    family_code: str,
    payload_fields: tuple[DocumentPayloadField, ...],
    *,
    template_bytes: bytes,
) -> TemplateScalarReplacementPlan:
    if family_code == "DDKD_CERTIFICATE":
        return _build_variant_exact_plan(
            family_code,
            payload_fields,
            template_bytes=template_bytes,
            family_contract=load_default_dkkd_variant_contracts(),
        )
    if family_code == "INSPECTION_BBTD_HOSO_DK":
        return _build_variant_exact_plan(
            family_code,
            payload_fields,
            template_bytes=template_bytes,
            family_contract=load_default_bbtd_variant_contracts(),
        )
    return build_scalar_replacement_plan(families, family_code, payload_fields)
