# ADR 0011: Document Contract and Template Registry First

## Status
Accepted

## Context
Legacy GxP document generation is not a simple mail-merge flow. Evidence from `RecordForm.frm` and `ExtRecordForm.frm` shows:
- multiple Word templates selected by procedure and business branch;
- bookmark writes, deletes, existence checks, row deletion, and table mutation;
- copy-forward logic from prior BBKT/CAPA/phiếu trình documents;
- no verified template binaries currently present in repository `legacy/`.

Implementing server-side generation before capturing this contract would force undocumented assumptions.

## Decision
Before full rendering implementation:
- maintain a generated document-contract artifact derived from VBA evidence;
- introduce a first-class template registry concept in the target model;
- model document generation per logical document family, template, bookmark payload, and copy-forward dependencies.

The PowerPoint-backed certificate branch is excluded from the current target baseline at user direction because it is legacy-only.

## Consequences
- Phase 5 can progress safely without inventing rendering behavior.
- Later rendering adapters can be swapped or staged while preserving business contract.
- Missing template binaries remain a known blocker for full visual parity, but not for contract definition and data-model preparation.
