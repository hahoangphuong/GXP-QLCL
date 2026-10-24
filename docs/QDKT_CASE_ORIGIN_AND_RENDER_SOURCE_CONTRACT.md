# QĐKT source-of-truth correction: modern Case is not created from KHKT

**Business-owner clarification (24/10/2026):** A new Case's fields are either
entered by a user or, where a workflow such as **Tái** applies, copied from the
originating Case under that workflow's rules. **KẾ HOẠCH KIỂM TRA (KHKT) is
not an input source for creating any Case field.**

## Separate three distinct questions

1. **Case creation or reuse:** use explicitly entered Case data or
   Case-to-originating-Case inheritance. The exact set of copied fields must
   follow the owning Case workflow; do not infer inheritance of all fields or
   reconstruct it from KHKT.
2. **Historical data reconciliation:** read-only `db.ktra` ID ↔
   `Case.legacy_inspection_id` checks remain useful for migration/audit
   anomalies. They are **not** Case creation gates, not mandatory for newly
   entered Cases (which may have no legacy ID), and not document-render gates.
3. **QĐKT rendering:** read the **current persisted Case-owned facts**, related
   registered site, inspection team and other appropriate owner-backed fields.
   Validate the exact QĐKT bookmark contract independently. The legacy VBA
   expressions `DaychuyenDD`, `Tinhthanh`, `TTVdd` describe old UI
   representations, not a requirement to join the KHKT planning worksheet.

## Verified current backend implementation

In `backend/app/services/workflow.py::create_inspection_case`, the
reassessment Case is created as `DRAFT` from explicitly passed site,
GxP, line and standard context. `legacy_inspection_id` is null for this
new Case. When `source_case_id` is supplied, the function checks the
canonical ProductionLine identity and calls
`_copy_evaluation_scope_for_reassessment`. **The verified code only
authorizes this specific copying path; it is not proof that every Case
field is inherited.** Other data remain owned by the explicit Case and
related workflow inputs. No KHKT lookup occurs in this creation path.

## Ownership and non-inference rules

| Document input concern | Correct starting owner | Still to validate |
|---|---|---|
| Inspection Case | Current Case, user entry, or authorized originating Case inheritance | Existing Case workflow and inheritance rules |
| Manufacturing category / line | Relevant fields supplied in the Case workflow | Meaning and display mapping for QĐKT bookmarks; no substitution of planning text |
| Place / province | Registered site / Case-owned geographic selection | Historical province-zone and bookmark formatting |
| Inspectors and order | Case inspection team and ordered members | Exact TT bookmarks and display contract, including legacy format differences |
| Decision reference/date | Case-linked decision owner | Replacement/amendment precedence and blank issuance-date behavior |

A missing QĐKT field must be resolved by correcting the responsible Case-owned
input/workflow, not by reading KHKT, guessing from a similarly named Case, or
inserting a fallback string. Keep `ready_to_render=False` until the remaining
bookmark, source and template contracts pass. Do not unblock a renderer simply
because KHKT is no longer a prerequisite.

## Implications for backlog and tests

- Retire the **false requirement** to establish `Case → db.ktra → KHKT selected
  row` before Case creation or modern QĐKT rendering.
- Keep Snapshot V2 tooling for **historical inspection-row audit only**; it must
  never populate a new Case or become a runtime dependency.
- Investigate and test Case creation (user input), Tái inheritance (approved
  source Case), and any required user edits **in the Case workflow owner**.
- Test QĐKT source-bundle identity coherence and bookmark formatting with
  modern persisted Case-owned records; leave unproven template fields blocked.
- No data migration, mutation, route enablement or document issuance is
  authorized by this clarification alone.
