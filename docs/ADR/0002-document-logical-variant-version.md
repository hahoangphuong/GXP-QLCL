# ADR 0002: Separate Logical Document, Variant, and Version

## Status
Accepted

## Context
Legacy VBA generates and manipulates:
- editable Word outputs
- derived PDFs
- scanned/signed PDFs
- supporting BBKT/CAPA/template copies

These artifacts often represent one business document with multiple technical renditions.

## Decision
The target model will separate:
- logical document
- document variant/rendition
- document version

## Consequences
- The system can track draft/editable, issued, scanned, and signed artifacts without duplicating business meaning.
- `DocumentService` owns lineage; `StorageService` only owns binary placement and retrieval.
