# Phase 5 Real Template Audit

## Scope
This step audits the real active template binaries now present under `legacy/Templates` and compares them against the curated Phase 5 registry.

## Delivered
- real-template audit tool: `tools/audit_phase5_real_templates.py`
- machine-readable artifact: `artifacts/phase5/template_compatibility_audit.json`
- human-readable artifact: `artifacts/phase5/template_compatibility_audit.md`

## Evidence boundary
- The audit only treats top-level files under `legacy/Templates` as the active baseline.
- Archived revisions under `legacy/Templates/Cũ` are intentionally excluded from the active compatibility matrix.
- The audit is evidence-based and does not assume canonical bookmark names from VBA are identical to the real template bookmark names.

## Main findings
- Real templates are now present for `24/25` curated families in the active top-level template set.
- Only `DDKD_CERTIFICATE` currently matches the curated bookmark contract exactly.
- `INSPECTION_CAPA_LAN_1` and `INSPECTION_CAPA_LAN_2` now have verified active template binaries, but still require source-document copy-forward behavior.
- `CERTIFICATE_ISSUANCE_WORD` still spans mixed binary types because the active set includes a `.potx` alongside Word `.dotx` files.
- No active top-level template in this audit required header/footer bookmark replacement; all discovered bookmarks were found in body parts.
- Many families show contract drift between VBA-derived bookmark names and real template bookmark names, especially:
  - suffix-expanded bookmark variants such as `TenCoSo1`, `TT1x`, `Diadiemx1`
  - conditional-delete variants such as `NoWHO_Del1`, `TaiDel2`
  - table-oriented row bookmarks that were not fully captured by the original registry baseline

## Design implications
- The current registry is useful as a family map, but not yet sufficient as an exact render contract for most families.
- The next document-generation step should introduce a reconciled bookmark alias or template-specific contract layer rather than forcing VBA canonical names directly into render.
- Copy-forward families must be implemented from the real bookmark/table evidence, not just from procedure names.
- PowerPoint-backed and Excel-backed branches remain separate migration concerns and should not be forced into the Word render path.

## Known gaps
- The audit does not yet inspect archived revisions under `legacy/Templates/Cũ`.
- The audit does not yet diff semantic layout behavior such as conditional section deletion or table-row expansion rules.
- The audit treats top-level files as active based on placement, not on a verified business approval log.

## Next recommended task
Reconcile the curated registry against the real template bookmark contracts family by family, then update payload builders and template metadata so render uses the real bookmark names rather than the current VBA-normalized baseline.
