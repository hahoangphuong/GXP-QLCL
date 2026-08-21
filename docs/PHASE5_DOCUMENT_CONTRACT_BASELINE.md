# Phase 5 Document Contract Baseline

## Scope
Phase 5 is not UI work and not final server-side rendering yet. The current deliverable is an evidence-based contract for legacy document generation so later implementation can replace VBA/COM without guessing.

## What was proven again from real VBA
- Word automation lives primarily in `RecordForm.frm` and `ExtRecordForm.frm`.
- Planning/document shell calls originate from workbook `Module1.bas`, but the business logic and bookmark mutation logic live in the add-in.
- Legacy generation uses configurable `Template_Path` and desktop Office automation.
- Legacy flow is not pure template fill:
  - some documents are created from templates;
  - some copy bookmark/table content from prior generated documents;
  - some delete rows or sections conditionally.

## Scope exclusions
- The PowerPoint-backed certificate branch is intentionally excluded from the current migration baseline because you confirmed it is legacy-only.

## Artifacts generated in this phase
- `tools/extract_phase5_document_contract.py`
- `artifacts/phase5/document_contract.json`
- `artifacts/phase5/document_contract.md`

## Current findings
- No real `.docx` / `.dotx` / `.xltx` template binaries were found under `legacy/` in this repository snapshot.
- Therefore, we can prove contract shape, procedure/template names, bookmark names, and copy-forward behavior, but we cannot yet prove final rendered layout or every formatting side effect.
- The VBA indicates at least these logical document families:
  - BBTD hồ sơ đăng ký
  - quyết định kiểm tra
  - kế hoạch kiểm tra
  - biên bản kiểm tra / biên bản đánh giá
  - CAPA round 1 / round 2
  - phiếu trình PCT / CT
  - quyết định cấp chứng chỉ
  - risk-management worksheet
  - external support/travel/payment forms from `ExtRecordForm`

## Curated template families proven from VBA
From `RecordForm.Get_Tpl` and adjacent document-construction procedures:
- `1. BBTD Ho so DK - {GP} - Moi/Tai.dotx`
- `2. QD KT - {GP}.dotx`
- `3. Ke hoach kiem tra {GP}.dotx`
- `4. BB KT - {GP}.dotx`
- `5. Danh gia CAPA - {GP}.dotx`
- `6. PT.PCT - {GP}.dotx`
- `7. PT.CT - {GP}.dotx`
- `8. QD cap CC - {GP}.dotx`
- `10. Bang cong cu quan ly rui ro.dotx`
- change/DDKD letter templates (`a.`, `b.`, `d.`, `11.` families)

From `ExtRecordForm.CreateFile`:
- travel authorization letter
- flight request letter
- participant list
- dossier checklist
- transfer-payment request
- advance payment workbook template
- payment request workbook template
- payment authorization letter

## Implication for target design
- `DocumentService` must own:
  - template registry
  - typed bookmark payload assembly
  - conditional section suppression
  - document lineage and copy-forward provenance
  - variant/version issuance tracking
- `StorageService` remains limited to folder resolution and binary IO.

## Known gaps
- Real template binaries are still missing from repo evidence.
- Bookmark formatting semantics that depend on template structure still need verification against actual files.
- Some flows use prior generated documents as source material (`BBKT`, CAPA, phiếu trình), so migration must preserve source-document linkage, not just final outputs.
