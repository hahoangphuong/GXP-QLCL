# Phase 4.5 - Non-Production Probe CLI

## Goal
Provide a repeatable CLI tool that operators or developers can run on a non-production private-share host to capture storage-validation evidence without using the web UI manually.

## Files
- [tools/probe_phase4_storage_nonprod.py](/D:/GXP-QLCL/tools/probe_phase4_storage_nonprod.py)
- [artifacts/phase4/probe_triplets.template.json](/D:/GXP-QLCL/artifacts/phase4/probe_triplets.template.json)
- [artifacts/phase4/probe_dkkd_sites.template.json](/D:/GXP-QLCL/artifacts/phase4/probe_dkkd_sites.template.json)
- [tests/test_phase4_probe_tool.py](/D:/GXP-QLCL/tests/test_phase4_probe_tool.py)

## What the tool does
- Reads storage roots from environment
- Loads a JSON array of inspection folder probe triplets
- Loads a JSON array of DDKD site-folder probe inputs
- Runs binding-first storage lookup for each triplet
- Runs live DDKD site-folder lookup for each site ID
- Optionally runs scratch-area write tests
- Writes:
  - `probe_report.json`
  - `probe_report.md`

## Usage
Example:

```powershell
$env:STORAGE_CLASS='synology_private_share_nonprod'
$env:STORAGE_INSPECTION_ROOT='\\\\tailscale-hostname\\shared\\01 - Kiểm tra GPs'
$env:STORAGE_DKKD_ROOT='\\\\tailscale-hostname\\shared\\Chứng nhận ĐĐKKDD'
python tools\probe_phase4_storage_nonprod.py `
  --database-url sqlite:///artifacts/phase2/staging_readonly.db `
  --input artifacts/phase4/probe_triplets.template.json `
  --dkkd-input artifacts/phase4/probe_dkkd_sites.template.json `
  --out-dir artifacts/phase4/nonprod_probe `
  --scratch-relative-path scratch/probe-20260813
```

## Safety
- The CLI performs write tests only when `--scratch-relative-path` is explicitly provided.
- Scratch writes stay relative to the configured storage root.
- The output report contains relative paths only.
- DDKD probes resolve by the durable `(<site_id>)` token and do not treat display-name text as identity.

## Next recommended step
Use this CLI with the non-production runbook to collect the first real private-share validation pack before attempting any document-generation or inspector desktop workflow integration.
