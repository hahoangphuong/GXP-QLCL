# C.5e Certificate-detail evidence capture

This slice does **not** implement `Input_DC_to_CC`. It captures exact local legacy evidence needed to unblock the existing readiness gate.

## What is captured

The tool reads the legacy files without modifying them:

- exact active `Input_DC_to_CC` body from `RecordForm.frm`;
- same-module direct helper candidates and their exact bodies;
- SHA-256 hashes for the VBA ZIP, `RecordForm.frm`, each captured procedure, and certificate template;
- bookmark names and table/row structure from `.dotx`/`.docx` Word parts;
- short cell-text previews only, sufficient to review row ownership without copying full template prose.

Commented procedures are deliberately ignored and can never be promoted into active evidence.

## Usage

Use the original VBA source ZIP:

```powershell
py tools/capture_c5e_certificate_detail_evidence.py `
  --vba-zip "D:\path\to\GXP-VBA code.zip" `
  --template "D:\path\to\9. Chung chi GMP (moi).dotx"
```

If the exact template file is not known but a legacy template directory exists:

```powershell
py tools/capture_c5e_certificate_detail_evidence.py `
  --vba-zip "D:\path\to\GXP-VBA code.zip" `
  --template-root "D:\path\to\legacy templates"
```

`--template-root` discovers `.dotx/.docx` files whose names contain `Chung chi` and `moi/mới`. If discovery is too broad, rerun with `--template` and the exact file.

Default outputs:

- `artifacts/legacy_audit/c5e_certificate_detail_evidence_capture.json`
- `tests/fixtures/c5e_certificate_detail/Input_DC_to_CC.active.bas`
- `tests/fixtures/c5e_certificate_detail/helpers/*.bas`
- `tests/fixtures/c5e_certificate_detail/*.structure.json`

These generated fixtures should be reviewed before staging. Do not stage unrelated existing `tests/fixtures/` contents.

## Safety invariants

- no source file mutation;
- no use of `unkeyed_entries`;
- no historical prose or compact-summary fallback;
- no commented-VBA promotion;
- no certificate-detail implementation until row-level mapping is derived from the captured evidence.
