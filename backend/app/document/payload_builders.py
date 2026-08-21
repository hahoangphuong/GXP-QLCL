from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.app.project_paths import phase_artifact_path
from backend.app.document.service_contract import DocumentPayloadEnvelope, DocumentPayloadField


class DocumentPayloadBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class PayloadBuilderRegistryField:
    field_name: str
    source_procedure: str
    sensitivity: str


@dataclass(frozen=True)
class PayloadBuilderRegistryEntry:
    family_code: str
    source_procedures: tuple[str, ...]
    fields: tuple[PayloadBuilderRegistryField, ...]
    copy_forward_required: bool
    notes: str | None = None


@dataclass(frozen=True)
class PayloadBuildInput:
    family_code: str
    values: dict[str, str]
    notes: str | None = None
    strict: bool = True


@dataclass(frozen=True)
class PayloadBuildResult:
    envelope: DocumentPayloadEnvelope
    used_fields: tuple[str, ...]
    missing_registry_fields: tuple[str, ...]
    unexpected_input_fields: tuple[str, ...]


def load_payload_builder_registry(path: Path) -> tuple[PayloadBuilderRegistryEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: list[PayloadBuilderRegistryEntry] = []
    for item in payload["payload_builders"]:
        fields = tuple(
            PayloadBuilderRegistryField(
                field_name=field["field_name"],
                source_procedure=field["source_procedure"],
                sensitivity=field["sensitivity"],
            )
            for field in item["fields"]
        )
        entries.append(
            PayloadBuilderRegistryEntry(
                family_code=item["family_code"],
                source_procedures=tuple(item["source_procedures"]),
                fields=fields,
                copy_forward_required=bool(item["copy_forward_required"]),
                notes=item.get("notes"),
            )
        )
    return tuple(entries)


def load_default_payload_builder_registry() -> tuple[PayloadBuilderRegistryEntry, ...]:
    return load_payload_builder_registry(phase_artifact_path("phase5", "payload_builder_registry.json"))


def get_payload_builder_entry(
    registry_entries: tuple[PayloadBuilderRegistryEntry, ...],
    family_code: str,
) -> PayloadBuilderRegistryEntry:
    matches = [entry for entry in registry_entries if entry.family_code == family_code]
    if not matches:
        raise DocumentPayloadBuildError(f"No payload builder registry entry for family_code={family_code!r}")
    if len(matches) > 1:
        raise DocumentPayloadBuildError(f"Ambiguous payload builder registry entry for family_code={family_code!r}")
    return matches[0]


def build_payload_envelope(
    registry_entries: tuple[PayloadBuilderRegistryEntry, ...],
    build_input: PayloadBuildInput,
) -> PayloadBuildResult:
    entry = get_payload_builder_entry(registry_entries, build_input.family_code)
    known_fields = {field.field_name: field for field in entry.fields}
    unexpected = sorted(set(build_input.values) - set(known_fields))
    if build_input.strict and unexpected:
        raise DocumentPayloadBuildError(
            f"Unexpected input fields for family_code={build_input.family_code!r}: {', '.join(unexpected)}"
        )

    payload_fields: list[DocumentPayloadField] = []
    used_fields: list[str] = []
    for field_name, value in build_input.values.items():
        if field_name not in known_fields:
            continue
        field = known_fields[field_name]
        payload_fields.append(
            DocumentPayloadField(
                field_name=field.field_name,
                value=value,
                source=field.source_procedure,
                is_sensitive=(field.sensitivity == "sensitive"),
            )
        )
        used_fields.append(field.field_name)

    if not payload_fields and known_fields:
        raise DocumentPayloadBuildError(
            f"No payload fields mapped for family_code={build_input.family_code!r}"
        )

    missing = sorted(set(known_fields) - set(used_fields))
    envelope = DocumentPayloadEnvelope(
        family_code=build_input.family_code,
        fields=tuple(payload_fields),
        source_procedures=entry.source_procedures,
        notes=build_input.notes or entry.notes,
    )
    return PayloadBuildResult(
        envelope=envelope,
        used_fields=tuple(sorted(used_fields)),
        missing_registry_fields=tuple(missing),
        unexpected_input_fields=tuple(unexpected),
    )
