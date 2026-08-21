from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CopyForwardDependency:
    source_family_code: str
    condition: str
    source_bookmarks: tuple[str, ...] = ()


@dataclass(frozen=True)
class TemplateRegistryEntry:
    family_code: str
    logical_name: str
    source_application: str
    storage_scope: str
    legacy_host_procedure: str
    legacy_case_numbers: tuple[int, ...]
    template_pattern: str
    selection_legacy_mode: str | None
    population_procedures: tuple[str, ...]
    bookmarks: tuple[str, ...]
    copy_forward_dependencies: tuple[CopyForwardDependency, ...] = ()
    notes: str | None = None


def load_curated_registry(path: Path) -> tuple[TemplateRegistryEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: list[TemplateRegistryEntry] = []
    for item in payload["entries"]:
        dependencies = tuple(
            CopyForwardDependency(
                source_family_code=dependency["source_family_code"],
                condition=dependency["condition"],
                source_bookmarks=tuple(dependency.get("source_bookmarks", [])),
            )
            for dependency in item.get("copy_forward_dependencies", [])
        )
        entries.append(
            TemplateRegistryEntry(
                family_code=item["family_code"],
                logical_name=item["logical_name"],
                source_application=item["source_application"],
                storage_scope=item["storage_scope"],
                legacy_host_procedure=item["legacy_host_procedure"],
                legacy_case_numbers=tuple(item["legacy_case_numbers"]),
                template_pattern=item["template_pattern"],
                selection_legacy_mode=item.get("selection_legacy_mode"),
                population_procedures=tuple(item["population_procedures"]),
                bookmarks=tuple(item["bookmarks"]),
                copy_forward_dependencies=dependencies,
                notes=item.get("notes"),
            )
        )
    return tuple(entries)
