# Development rehearsal: DDK source-only GxP provenance import

After successful schema-only deployment, the actual VM postflight reported
`PASS_SCHEMA_0023_SOURCE_ONLY_EMPTY` for `gxp_legacy_rehearsal`,
`alembic_version=20261012_0023`, 0 source groups and 0 tokens; backend
`/readyz` reported expected/actual `0023`, healthy, SHA
`f96d9336fde453ac50db04f6b3df2193a03e5035`.

## Input identity and limits

Use the existing owner-accepted, **sealed** local plan produced by
`tools/plan_ddk_gxp_provenance_load.py` from the original physical
`db.dkkd` XLSB exports plus exact approved exclusions. The plan is **not**
the flattened `linked_certificate_ids` importer output. Original accepted
workbook SHA-256:
`c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d`.

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
   to the VM as a private file accessible by account `gxp`; do not infer its
   file path. `/var/tmp/gxp-ddk-provenance-plan.json` is only a suggested
   destination (permission 0600, owner gxp). If the plan has not been generated,
   create it first from the three original accepted JSON input artifacts,
   as in `docs/DDK_GXP_PROVENANCE_DRY_RUN_PLAN_20261012.md`.

2. With a PR #7 checkout/release that contains the new importer and
   dependencies, validate source JSON offline (no DB access):

```bash
sudo -H -u gxp /opt/gxp/current-venv/bin/python \
  -m tools.apply_ddk_gxp_provenance_rehearsal \
  --plan-json /var/tmp/gxp-ddk-provenance-plan.json \
  --expected-workbook-sha256 c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d \
  --expected-groups 3120 --expected-tokens 861
```

3. To apply *to test DB only*, add:

```bash
  --apply --confirm-target gxp_legacy_rehearsal
```

The CLI derives its target from the private `/etc/gxp/runtime.env`,
requires declared AND effective PostgreSQL URL to point at loopback
`gxp_legacy_rehearsal` as role `gxp_app`, and refuses other databases.
It checks the sealed plan, external workbook SHA, expected counts, revision,
table shape and constraints, and target emptiness before inserting anything.
The source payload is not logged.

One locked PostgreSQL transaction writes groups first, then tokens, verifies
the exact original group fields/token order/checksums from the same connection,
and commits only on success. Any mismatch aborts atomically. A second
application of the *identical* plan returns
`SOURCE_PROVENANCE_ALREADY_MATCHES_PLAN` (0 new rows). A different or
partially populated workbook is blocked rather than overwritten/repaired.

After import, **do not use the empty-table postflight SQL** (it intentionally
fails for nonempty source data). Use the existing
`tools/preflight_ddk_gxp_rehearsal.py` with the same plan and a
read-only database URL to confirm
`SOURCE_PROVENANCE_ALREADY_MATCHES_PLAN` independently.

The importer never writes Certificate, CertificateVersion, Case,
BusinessEligibilityVersion, Site or BusinessEligibilityCertificateLink.
Physical source evidence remains separate from reviewed canonical links.

## Native Linux/VM XLSB source path (when prior JSON exports are missing)

The development VM may contain an earlier private copy of the original
`Danh sách Kiểm tra GPs.xlsb` in `/tmp`. The prior private-file search
did not cover that directory. Never assume a file survived; test existence
and its SHA-256 against the source-owner accepted value first.

The older `tools.audit_ddk_idcc_physical --workbook` path requires Windows
Excel COM. Use `tools.build_ddk_xlsb_source_plan` on Linux instead. It reads
the cached cells in the binary original with a VM-isolated `pyxlsb==1.0.10`
dependency, reconstructs the four original group headings and their 16 raw
cells by **physical** column, retains all ID CC tokens by original ordinal,
validates the 830/50/861 accepted source baseline and the approved exclusion
contract, and saves a sealed `DRY_RUN_ONLY_NOT_APPLIED` JSON load plan.
The tool never opens PostgreSQL and does not modify the source workbook.

The grouped and token evidence views are derived from one reader. This is
explicitly recorded as `PYXLSB_CACHED_CELLS_SINGLE_READER`, with
`independent_reader_verification=false` and
`excel_com_formula_status=WAIVED_NOT_CHECKED`. It does not fabricate a
COM/HasFormula PASS or independent-engine validation. Actual source workbook
SHA and source population are required.

If the original binary is present on VM, use a separate tool dependency
directory under `/var/tmp` to keep the pinned backend runtime unchanged:

```bash
# Use current checked-out PR #7 after CI success; the target file must exist.
mkdir -p /var/tmp/gxp-ddk-tools-deps
/opt/gxp/current-backend-venv/bin/python -m pip install \
  --target /var/tmp/gxp-ddk-tools-deps pyxlsb==1.0.10
PYTHONPATH=/var/tmp/gxp-ddk-tools-deps \
  /opt/gxp/current-backend-venv/bin/python \
  -m tools.build_ddk_xlsb_source_plan \
  --workbook "/tmp/gxp-lifecycle-input/Danh sách Kiểm tra GPs.xlsb" \
  --approved-exclusions-json artifacts/phase3q/confirmed_blanked_rows.json \
  --expected-workbook-sha256 c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d \
  --expected-ddk-rows 830 \
  --expected-excluded-ddk-rows 50 \
  --expected-reference-tokens 861 \
  --output /var/tmp/gxp-ddk-source-only-plan.json
```

The example `/opt/gxp/current-backend-venv` is a placeholder: resolve
the actual VM virtual environment from existing deploy symlinks before use.
Do not assume that path exists. Keep the output private and outside Git.
Once the plan is sealed and independently validated, the existing importer
can read it by path on the same VM. No Windows PostgreSQL is involved.
