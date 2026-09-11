# INSPECTION_QD_KT Business-Semantic Overlay

## Decision

This note adds a **business-semantic layer** on top of the existing source-derived
VBA provenance audit. It does not rewrite or reinterpret the source evidence in
`inspection_qd_kt_input_provenance.json`.

The product owner/user confirmed that the legacy VBA UI uses **one user-entered
text cell** containing both:

- `QDKT` — the QĐKT decision reference/number; and
- `NgayQDKT` — the QĐKT decision date.

The active VBA later splits that composite cell into the two rendered values.
The source-derived trace remains authoritative for the split mechanics; the fact
that the cell is a user-authored QĐKT business input is a separate business
confirmation.

## Evidence classes

Two evidence classes must remain separate:

1. **Source-derived provenance**
   - legacy source ZIP SHA256:
     `6227fb0a6b3d74fa0f4cc655b94b021a40d65a508c2f2eefc62f1724c7b89ff7`;
   - `QDKT` and `NgayQDKT` are derived from one `db.ktra` decision cell;
   - VBA splits the value into a reference fragment and a trailing date fragment.

2. **User-confirmed business semantics**
   - the combined cell is entered by the user;
   - it carries QĐKT decision reference + QĐKT decision date;
   - therefore the business owner is planning/authorization metadata for the
     inspection decision, not generic display prose.

The business confirmation must not be presented as if it were proven by VBA
source alone.

## Current modern-model finding

The current schema has:

- `InspectionPlan.decision_document_hint`;
- `InspectionOutcome.decision_reference`;
- no structured QĐKT decision-date field on `InspectionPlan`.

The current legacy importer also maps the legacy `Q. định` value into
`InspectionOutcome.decision_reference`, and separately copies the same legacy
value into `CaseApplication.dossier_reference`.

Those mappings are treated as **legacy compatibility projections**, not proof
that either target is the semantic owner of QĐKT. In particular, the typed
QĐKT contract must not silently reuse `InspectionOutcome.decision_reference`
merely because its name resembles `QDKT`; QĐKT is planning/authorization data
that exists before the inspection outcome.

## Updated owner disposition

The source-derived provenance file itself is unchanged. After applying the
business-semantic overlay:

| Field | Business owner | Current modern owner | Disposition |
|---|---|---|---|
| `QDKT` | user-authored QĐKT composite input → decision reference | `InspectionPlan` decision metadata; raw preservation candidate `decision_document_hint` | `OWNER_PARTIAL` |
| `NgayQDKT` | user-authored QĐKT composite input → decision date | `InspectionPlan` decision metadata; no structured date field exists | `OWNER_PARTIAL` |

Expected aggregate classification across the 14 active i=2 inputs becomes:

- `OWNER_PROVEN=0`
- `OWNER_PARTIAL=8`
- `OWNER_BLOCKED=6`

The typed QĐKT input contract remains `BUSINESS_INPUT_CONTRACT_MISSING` because
other active inputs remain unresolved and the planning-phase decision schema is
not yet closed.

## Schema decision

No schema migration is authorized by this note alone.

However, the current evidence now makes a later dedicated planning-phase QĐKT
owner plausible. If the remaining contract review confirms the legacy grammar
and lifecycle, the preferred direction is to model decision metadata explicitly
on the planning/authorization owner rather than preserve a combined string as
semantic truth.

A future migration candidate would be conceptually equivalent to:

- structured QĐKT decision reference;
- structured QĐKT issued/decision date;
- optional raw legacy composite text for audit/compatibility.

Exact field names and migration scope must be decided only after the remaining
business-input contracts are closed.

## Next contract-closing order

Continue without changing runtime/schema in this order:

1. Reconcile `HsDK` against `CaseApplication.dossier_code`.
2. Reconcile `NgaynopHsDK` against `CaseApplication.submitted_on`, including
   submitted-vs-received semantics and timezone/date normalization.
3. Reconcile `Tencoso` against `Site.site_name` and prove whether planning-row
   selection and `db.cso` selection are the same business owner.
4. Close ordered team rendering (`TTx`, `TT3x`, `TT3Del`) against
   `InspectionTeam` / `InspectionTeamMember` ordering and role text.
5. Only then decide whether the remaining blocked fields justify schema changes
   and whether the typed `INSPECTION_QD_KT` payload can leave
   `BUSINESS_INPUT_CONTRACT_MISSING`.

## Guardrails

- Do not parse display prose into authoritative structured truth without an
  explicit semantic contract.
- Do not repurpose `InspectionOutcome.decision_reference` as QĐKT truth without
  lifecycle proof.
- Do not mutate the source-derived provenance artifact to make user-confirmed
  facts look source-proven.
- Do not enable document creation/readiness while required active inputs remain
  unresolved.
