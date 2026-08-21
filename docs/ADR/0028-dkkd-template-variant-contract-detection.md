# ADR 0028: Detect DDKD Template Variant From Concrete DOCX Bytes

## Context
`DDKD_CERTIFICATE` was initially promoted into the runtime template contract gate because its reconciled scalar field set looked exact at the family level.

Further audit against the active template binaries under `legacy/Templates` showed the family is only exact as a union:
- the `ddkd_certificate_new` template does not expose every bookmark used by the adjustment form.
- the `ddkd_certificate_adjustment` template adds variant-specific bookmarks such as `Cap_lan` and `GCN_thaythe`.

Allowing family-level passthrough after template selection would silently reintroduce field loss risk.

## Decision
- Detect the concrete DDKD template variant from the actual DOCX bookmark set at render time.
- Compare the concrete bookmark set against a curated variant contract artifact.
- Allow only the payload fields explicitly supported by the detected variant.
- Fail closed when:
  - the concrete template does not match any known variant contract; or
  - the payload contains fields not allowed by that variant.

## Consequences
Positive:
- Runtime behavior is now aligned with the real active DDKD templates, not only the family-level union contract.
- The `ddkd_certificate_new` and `ddkd_certificate_adjustment` variants can share one logical family without silently dropping variant-only fields.
- Template drift becomes observable immediately through a contract mismatch.

Negative:
- DDKD render now depends on an additional artifact that must be regenerated when active template binaries change.
- The current variant detector is bookmark-set exact, so legitimate template edits must be adjudicated before deployment.
