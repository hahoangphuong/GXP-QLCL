# db.ktra Batch 5 Residual Audit

`python -m tools.audit_db_ktra_residuals --compare-rehearsal` is the only
execution mode. It requires `DATABASE_URL` for PostgreSQL database
`gxp_legacy_rehearsal` at revision `20260912_0012`, starts with `SET TRANSACTION
READ ONLY`, verifies that state, issues SELECTs only, then rolls back and closes.

It writes three evidence artifacts only after those fences pass:

- `db_ktra_residual_audit_v1.json`
- `db_ktra_blocked_identity_v1.json`
- `db_ktra_blocked_parser_v1.json`

Residual compatibility data is classified as transformed contamination only for
an exact legacy raw-value equality with the documented historical Phase 2
compatibility-copy path. There is no fuzzy matching or normalization-based
proof. PCT source facts remain unordered, and CT parentage remains blocked
unless explicit source evidence exists. The tool creates no rows and never
cleans residual fields.
