# Read-only DDK GxP source-token candidate classification — 14 Oct 2026

## Scope

Code: `tools/audit_ddk_gxp_canonical_candidates_readonly.py`. Owner:
backend PR #7; no schema changes, no mutations, no approved links, no
frontend API changes. This tool supplements persisted original Excel
`db.dkkd` source groups and per-token evidence, which remain immutable
source observations.

On rehearsal VM `gxp-web-prod`, as verified by the operator on 14 Oct:

- Actual web runtime `97182e58c3a673938d1b263c7eeaab41d28147b4`.
- Schema `20261012_0023`, database `gxp_legacy_rehearsal`.
- 3,120 source groups and 861 ID CC tokens, imported from accepted original
  XLSB SHA-256 `c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d`.
- 780 actual DDK version rows, 780 distinct DDK aggregates; no multiple
  persisted DDK versions and no canonical `business_eligibility_certificate_link` rows.
- Prior owner baseline flags five cross-Site source references and one
  DDK 626 company inconsistency. This tool must **measure**, not
  normalize or approve, those observations.

## Analysis semantics

Every physical Excel `source_group / source_row_number / token_index`
observation is preserved. The audit checks SHA-bound four-field source
digests, distinct GMP/GLP/GSP/GDP physical columns, four-group completeness,
token raw values/ordinal, and accepted corpus counts. It compares each
*legacy integer* ID CC against canonical Certificate.legacy_certificate_id
with dimensions:

- candidate found / absent (no canonical ID invented);
- exact GxP type / different type (no GMPbb remapping);
- same / different Site UUID (no Site ownership rescue);
- DDK company compared against DDK Site owning company;
- repeated legacy references counted without deduplication;
- potential cross-Site same-company evidence reported but not promoted.

`SOURCE_OBSERVATION_NOT_APPROVED` is present for **every token**, even if
all observed IDs/type/Site match. No "safe-to-link", "eligible", "auto-match",
regulatory status, version selection or scope assignment is exposed.
Existing canonical link count is read as a separate observation, not altered.

## VM command after this commit CI passes

Run from the checked-out validated backend PR #7 source tree. Use the
current VM runtime env, without printing DSN or credentials:

```bash
sudo -H -u gxp /opt/gxp/current-venv/bin/python \
  -m tools.audit_ddk_gxp_canonical_candidates_readonly \
  --expected-workbook-sha256 c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d \
  --expected-groups 3120 --expected-tokens 861
```

The command uses `/etc/gxp/runtime.env` and verifies
`DB_MODE=local_postgres`, `DB_NAME=gxp_legacy_rehearsal`,
`DB_USER=gxp_app`, and local host with no overriding URI parameters.
The connection starts with PostgreSQL
`default_transaction_read_only=on`, the transaction verifies `READ ONLY`,
correct database and expected Alembic revision. It cannot insert, link or
modify existing source/Certificate tables.

For a private **token-level** JSON report, specify
`--output-json /var/tmp/gxp-ddk-private/candidate-audit-20261014.json`.
The file is written mode 0600 and cannot overwrite an existing file. Never
copy original source/report records to public GitHub, CI logs, or a frontend
API response; the CLI stdout prints aggregate counts only.

The source baseline acceptance waived Excel COM verification for this
development-only corpus. The tool does not claim independent COM validation.
Any future canonical links or DDK version mappings require explicit owner
adjudication of cross-Site/Company, version and regulatory scope.
