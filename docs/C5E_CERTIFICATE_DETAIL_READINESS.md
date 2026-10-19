# C.5e certificate-detail (`Input_DC_to_CC`) readiness

## Current decision — source implemented; LIVE NOT VERIFIED

The earlier `BLOCKED_PENDING_EXACT_VBA_AND_TEMPLATE_EVIDENCE` finding was
based on two obsolete source probes: it looked for the active VBA body only
in `docs/VBA_FUNCTION_MAP.md` and for a certificate-detail destination
bookmark only in the **generic** Phase-5 template registry. Those are not
the owners of the evidence and no longer describe the source tree.

The source audit now reports
`SOURCE_CONTRACT_IMPLEMENTED_LIVE_NOT_VERIFIED` only when the captured
active VBA, dedicated source/destination Word asset contracts, checked
destination `Pvi` geometry and dedicated rendering owner all match.
**This is not a deployment or authenticated document-generation PASS.**

## Source-side evidence that now exists

- `tests/fixtures/c5e_certificate_detail/Input_DC_to_CC.active.bas`
  retains the active `Private Function Input_DC_to_CC` body; captured
  `helpers/Key2Bookmark.bas` retains the `L...` bookmark transformation.
  The commented `Input_DC_to_CC2` remains excluded. Their presence does
  not cryptographically authenticate the originating VBA archive.
- `backend/app/document/c5e_certificate_detail_source_assets.json`
  records the six content-addressed legacy source assets: three
  `certificate_9` and three `appendix_z3` assets for GMP/GLP/GSP.
  The active issuance runtime uses `certificate_9`, not `appendix_z3`.
- `backend/app/document/c5e_certificate_destination_assets.json`
  identifies separately captured **GMP and GLP** destination templates
  and SHA-256 values, matched against the tracked
  `tests/fixtures/c5e_certificate_detail/*.structure.json` structures,
  each with precisely one `Pvi` bookmark in `word/document.xml`.
  The generic `artifacts/phase5/template_registry.curated.json` contains
  general-information bookmarks and is not the `Pvi` evidence owner.
- `backend/app/document/c5e_certificate_detail_semantic_projection.py`,
  `c5e_certificate_detail_runtime.py`,
  `c5e_certificate_detail_docx_render.py` and
  `docx_template_render.py` contain the separate semantic and
  formatted-fragment insertion flow. Existing CI tests exercise this
  source implementation, but do not substitute for real Word output.

**GSP remains fail-closed at the destination template boundary.** The
dedicated destination registry explicitly marks the GSP Word template
unavailable/unverified; six source assets do not grant GSP destination
readiness. GDP is excluded by contract.

## Still missing for LIVE readiness

1. Check the actual **source and destination template bytes** present in
   the authorized runtime `template` storage against the registered
   SHA-256 checksums, at the exact verified deployment/source SHA.
   Tracked JSON hashes/fixtures alone are not a runtime storage inventory.
2. Verify an authorized, authenticated **real Case** end-to-end render and
   the resulting DOCX's structure and expected certificate-detail semantics,
   with protected source/template custody and no disclosed data.
3. Verify the GSP destination binary, template metadata and checksum
   separately before enabling GSP; unsupported input must still fail closed.

No automatic deployment, NAS/GCS read/write, VBA archive replacement,
real Case operation, data migration or certificate issuance is authorized
by this audit. Work that requires runtime credentials or template binaries
is paused until independently approved and source-pinned.

## Semantic invariants

- Do not reconstruct taxonomy nodes from compact summaries or historical
  prose, and never use `unkeyed_entries` as semantic input.
- The active VBA fixture, not the commented `Input_DC_to_CC2`, owns
  the source interpretation. Generic scalar/table clones cannot own `Pvi`.
- Preserve Word formatting and the destination paragraph suffix;
  unsupported fragment geometry or ambiguous ZIP member identity fails
  closed.
- No promotion of source tests, checksum-shaped metadata or fixture-only
  render outcomes to `AUTHENTICATED_REAL_BACKEND_VERIFIED`.

The owner is `tools/audit_c5e_certificate_detail_readiness.py`; its
tracked report is
`artifacts/legacy_audit/c5e_certificate_detail_readiness.json`.
