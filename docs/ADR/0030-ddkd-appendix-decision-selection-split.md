# ADR 0030: Split DDKD Appendix And Issuance Decision Selection At Registry Level

## Context
`DDKD_APPENDIX_OR_DECISION` was originally seeded as one family-level template definition covering both `Get_Tplz` case 3 and case 4.

Audit against the active templates under `legacy/Templates` showed those are two different concrete files:
- `z3. Phụ lục GCN ĐĐKKDD.dotx`
- `z4. QĐ cấp ĐĐKKDD.dotx`

They do not share one stable physical bookmark surface:
- `z3` exposes a small appendix-oriented surface.
- `z4` exposes a much larger issuance-decision surface.

Keeping both behind one template definition invents a false identity and prevents fail-closed selection.

## Decision
- Keep one logical `family_code`: `DDKD_APPENDIX_OR_DECISION`.
- Split the curated registry and template seed into two concrete template entries.
- Add explicit `selection_legacy_mode` to the registry contract.
- Require callers to pass:
  - `legacy_mode = "appendix"` for `z3`
  - `legacy_mode = "issuance_decision"` for `z4`
- Preserve one shared payload-builder owner for the family by deduplicating payload specs at `family_code` level.

## Consequences
Positive:
- Template selection now reflects the real active legacy files and fails closed when the caller omits the required mode.
- Template definitions and bindings now have concrete identity instead of a synthetic family placeholder.
- The payload vocabulary remains owned once per family and does not fragment prematurely.

Negative:
- `DDKD_APPENDIX_OR_DECISION` is still not eligible for runtime bookmark-contract promotion because several payload fields remain unresolved against the real template surfaces.
- Callers must now provide `legacy_mode` explicitly for this family.
