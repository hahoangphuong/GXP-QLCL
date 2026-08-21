# Document Template Registry

## Purpose
This document is the curated, migration-facing registry for legacy document families. It sits above the raw VBA parser artifact and below future `DocumentService` implementation.

## Evidence rules
- Only include flows with direct VBA evidence.
- Do not treat template filenames parsed from `ChrW(...)` fragments as authoritative when the parser output is visibly broken.
- Use the curated family/template names proven by `Get_Tpl`, `Get_Tplz`, `CreateFile`, `CreateFilez`, and the corresponding population procedures.
- Keep the PowerPoint-backed certificate branch out of scope.

## Registry outputs
- Curated JSON artifact: `artifacts/phase5/template_registry.curated.json`
- Curated Markdown artifact: `artifacts/phase5/template_registry.curated.md`
- Real-template audit JSON: `artifacts/phase5/template_compatibility_audit.json`
- Real-template audit Markdown: `artifacts/phase5/template_compatibility_audit.md`

## Real-template verification status
- The repository now contains active template binaries under `legacy/Templates`.
- The curated registry remains the family-level map, but the exact bookmark contract must now be validated against the real binaries.
- See `docs/PHASE5_REAL_TEMPLATE_AUDIT.md` for the first active-template compatibility pass.

## Main family groups
### Inspection-core documents
- Registration dossier assessment minutes
- Inspection decision
- Inspection plan
- Inspection minutes
- CAPA round 1 / round 2
- PCT / CT presentation documents
- Certificate issuance decision
- Word-scoped certificate issuance
- Risk-management worksheet
- Status / change letters

### DDKD documents
- Presentation for DDK issuance
- DDK certificate
- DDK appendix / issuance-decision family

### Support documents
- Travel authorization
- Flight request
- Attendee list
- Checklist families
- Payment-support letters
- Excel payment workbooks

## Design implications
- `DocumentService` needs a first-class `family_code`, not just free-text template names.
- Template selection must branch by:
  - document family
  - GP stream
  - legacy mode such as Moi/Tai
  - support or DDKD host flow
- Payload assembly must be composed from one or more population procedures.
- Copy-forward dependencies must be explicit lineage, especially for:
  - CAPA from prior BBKT
  - CAPA round 2 from CAPA round 1
  - PT.CT from prior PT.PCT

## Known review-required families
- Case 14 in `RecordForm.CreateFile` mixes comments about change-report evaluation and routing to business-eligibility issuance.
- Case 15 `Tao_BB_Danhgia` is proven as a family, but the raw bookmark parser does not yet capture its full payload shape.
- DDKD template filenames in `Get_Tplz` still need exact verification against real template binaries.
