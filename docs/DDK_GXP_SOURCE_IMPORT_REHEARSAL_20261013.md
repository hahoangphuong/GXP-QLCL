# Development rehearsal: DDK source-only GxP provenance import

After successful schema-only deployment, the actual VM postflight reported
\`PASS_SCHEMA_0023_SOURCE_ONLY_EMPTY\` for \`gxp_legacy_rehearsal\`,
\`alembic_version=20261012_0023\`, 0 source groups and 0 tokens; backend
\`/readyz\` reported expected/actual \`0023\`, healthy, SHA
\`f96d9336fde453ac50db04f6b3df2193a03e5035\`.

## Input identity and limits

Use the existing owner-accepted, **sealed** local plan produced by
\`tools/plan_ddk_gxp_provenance_load.py\` from the original physical
\`db.dkkd\` XLSB exports plus exact approved exclusions. The plan is **not**
the flattened \`linked_certificate_ids\` importer output. Original accepted
workbook SHA-256:
\`c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d\`.

Expected 780 effective rows × four physical groups = **3,120** group records,
and **861** distinct ordinal token observations (851 GMP, 9 GLP, 1 GSP,
0 GDP); 3,981 records total. Preserve blank ID CC values, and GxP scope,
standard and activity text regardless of whether there is an ID. No
certificate number/ID is deduplicated or used to create an FK. The source
export is owner-accepted for this development context; its Excel COM/HasFormula
checks were waived, not completed.

Input JSON contains confidential source business data: DO NOT commit it,
attach it to a PR, upload to a public bucket, or print its contents in logs.

## Steps

1. Keep the original sealed plan on the operator's local disk and transfer it
   to the VM as a private file accessible by account \`gxp\`; do not infer its
   file path. \`/var/tmp/gxp-ddk-provenance-plan.json\` is only a suggested
   destination (permission 0600, owner gxp). If the plan has not been generated,
   create it first from the three original accepted JSON input artifacts,
   as in \`docs/DDK_GXP_PROVENANCE_DRY_RUN_PLAN_20261012.md\`.

2. With a PR #7 checkout/release that contains the new importer and
   dependencies, validate source JSON offline (no DB access):

\`\`\`bash
sudo -H -u gxp /opt/gxp/current-venv/bin/python \
  -m tools.apply_ddk_gxp_provenance_rehearsal \
  --plan-json /var/tmp/gxp-ddk-provenance-plan.json \
  --expected-workbook-sha256 c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d \
  --expected-groups 3120 --expected-tokens 861
\`\`\`

3. To apply *to test DB only*, add:

\`\`\`bash
  --apply --confirm-target gxp_legacy_rehearsal
\`\`\`

The CLI derives its target from the private \`/etc/gxp/runtime.env\`,
requires declared AND effective PostgreSQL URL to point at loopback
\`gxp_legacy_rehearsal\` as role \`gxp_app\`, and refuses other databases.
It checks the sealed plan, external workbook SHA, expected counts, revision,
table shape and constraints, and target emptiness before inserting anything.
The source payload is not logged.

One locked PostgreSQL transaction writes groups first, then tokens, verifies
the exact original group fields/token order/checksums from the same connection,
and commits only on success. Any mismatch aborts atomically. A second
application of the *identical* plan returns
\`SOURCE_PROVENANCE_ALREADY_MATCHES_PLAN\` (0 new rows). A different or
partially populated workbook is blocked rather than overwritten/repaired.

After import, **do not use the empty-table postflight SQL** (it intentionally
fails for nonempty source data). Use the existing
\`tools/preflight_ddk_gxp_rehearsal.py\` with the same plan and a
read-only database URL to confirm
\`SOURCE_PROVENANCE_ALREADY_MATCHES_PLAN\` independently.

The importer never writes Certificate, CertificateVersion, Case,
BusinessEligibilityVersion, Site or BusinessEligibilityCertificateLink.
Physical source evidence remains separate from reviewed canonical links.
