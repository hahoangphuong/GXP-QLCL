# ADR 0029: BBTD Uses Concrete Template Slot Mapping

## Context
`INSPECTION_BBTD_HOSO_DK` is one logical family, but the active legacy templates do not expose one stable physical bookmark surface.

Audit against active files under `legacy/Templates` showed:
- 8 live BBTD templates collapse into 4 exact bookmark sets.
- The business-facing payload stays narrow: `Daychuyen`, `Diachicoso`, `Fulldate`, `Tencoso`.
- The concrete templates expand those fields into numbered physical bookmarks such as `DayChuyen1`, `DayChuyen2`, `DayChuyen3`.
- Some templates populate only one numbered slot, while the GMP template populates all three.

Treating those templates as raw payload passthrough would miss the numbered bookmark fan-out that the real templates require.

## Decision
- Build a concrete-template variant contract artifact for `INSPECTION_BBTD_HOSO_DK`.
- Detect the concrete template variant from the actual DOCX bookmark set at render time.
- Map each business-facing payload field to the exact numbered bookmark targets allowed by that concrete variant.
- Fail closed if the template bookmark set does not match any curated BBTD variant.

## Consequences
Positive:
- The renderer now preserves the narrow business payload vocabulary while still honoring numbered physical bookmarks in real legacy templates.
- A single logical family can support one-line and three-line BBTD forms without leaking physical bookmark numbering into payload builders.
- Template drift becomes immediately visible through a variant mismatch.

Negative:
- BBTD now depends on another generated artifact that must be refreshed when active template binaries change.
- The current detector remains exact by bookmark set, so legitimate template edits require adjudication before rollout.
