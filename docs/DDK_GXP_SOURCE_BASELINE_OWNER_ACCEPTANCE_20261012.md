# DDK GxP source baseline acceptance — scope-limited owner decision

**Decision recorded: 12 October 2026.** The data owner explicitly requested
to **close source verification without Microsoft Excel COM on Windows** and
continue development. The independent XLSB/JSON source reconciliation is
accepted as the working **source baseline** for development of *empty,
additive source provenance storage*. This replaces the earlier requirement
for Excel COM as a mandatory precondition to **this specific development
slice**. It does **not** retrospectively convert COM/HasFormula checks
into PASS.

## Accepted original-source baseline

- Original workbook SHA-256:
  `c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d`.
- 830 physical `db.dkkd` rows; 50 exact owner-approved confirmed-blanked
  exclusions, leaving 780 effective legacy DDK source records.
- Four row-3 GxP headings GMP, GLP, GSP, GDP with four distinct row-4
  companion fields each, 3,320 physical groups and 13,280 source cells.
- 748 nonblank ID CC cells; **861 original references** after explicit
  semicolon tokenization (GMP 851, GLP 9, GSP 1, GDP 0).
- Independent read-only XLSB/JSON reconciliation found **861/861 source
  token agreement** and no discrepancies in DDK identities or physical GxP
  group positions.
- Source anomalies **not** adjudicated: five cross-Site references (GMP
  Certificate 1064 twice; 1180, 1308, 1385 once); one DDK-versus-Site
  owning-Company mismatch (legacy DDK 626). Twenty-five groups have
  companion text without a Certificate ID, including six GDP activity
  fields. These are evidence, not permission to invent Certificate links.
- The independent source artifacts may share their XLSB extraction engine;
  agreement is not independent-engine corroboration. Microsoft Excel
  `Range.HasFormula` was **not executed** and original Excel `Value2`
  whitespace/formatting may differ from previously produced JSON.
  The decision accepts those residual uncertainties for the current
  scoped development work. No future step should claim `COM_VALIDATED`.

## Authorized scope for this development slice

Design and commit **two empty, additive schema entities** and their
tests on backend PR #7 only:

1. `business_eligibility_gxp_source_group`, storing original workbook
   fingerprint, sheet, physical Excel row/columns, GxP group, raw four
   source values and their group digest.
2. `business_eligibility_gxp_reference_evidence`, storing
   group-specific token ordinal and raw parsed legacy ID observations.

These represent **source evidence only**, with **no FK to** canonical
`Certificate`, `CertificateVersion`,
`BusinessEligibilityCertificate` or `BusinessEligibilityVersion`.
The current `BusinessEligibilityCertificateLink` is unchanged.

The draft migration `20261012_0023` creates **empty tables only**. No
auto-backfill, no SQL writes to the rehearsal or production databases,
no runtime importer behavior, no URL/API/read-model changes, no deploy.
Migration downgrade is permitted for empty tables, but refuses to discard
nonempty provenance records.

**Separate future gates** still require explicit owner approval for
mapping a DDK source row to a canonical version, assigning ID CC tokens
to Certificate identities, resolving Site/Company ownership and
multi-Site coverage, and deciding how and when to populate historical
records. The observed GMP/GLP/GSP/GDP group labels do not establish
business-grant state.

This decision supersedes older "COM must PASS before development" language
in `DDK_GXP_GROUP_PROVENANCE_CONTRACT_PROPOSAL_20261012.md` only in
relation to this accepted baseline and this strictly additive slice.
Existing security, integrity, validation and target database guards
remain in force. Both backend PR #7 and independent Codex UI PR #3
remain OPEN/DRAFT; no merges or production cutover.
