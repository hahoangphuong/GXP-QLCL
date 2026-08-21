from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentTemplateReference:
    legacy_name: str
    source_application: str
    source_procedure: str


@dataclass(frozen=True)
class BookmarkMutation:
    bookmark_name: str
    operation: str
    source_procedure: str


@dataclass(frozen=True)
class DocumentContract:
    logical_code: str
    source_procedure: str
    source_application: str
    templates: tuple[DocumentTemplateReference, ...]
    bookmark_mutations: tuple[BookmarkMutation, ...]
    output_extensions: tuple[str, ...]
    reuses_existing_document_content: bool = False
