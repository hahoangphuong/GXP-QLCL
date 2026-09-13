# C.5e certificate-detail source asset contract

Scope is explicitly limited to **GMP, GLP and GSP**. GDP is excluded by design and is rejected by the runtime contract.

The six proven legacy source documents are modeled as content-addressed source assets:

- `certificate_9`: `9. PhamviGMP.docx`, `9. PhamviGLP.docx`, `9. PhamviGSP.docx`
- `appendix_z3`: `z3. PhamviGMP.docx`, `z3. PhamviGLP.docx`, `z3. PhamviGSP.docx`

Each asset has the SHA-256 captured from the legacy evidence run. The registry is exactly a 2x3 matrix. Missing, duplicate, extra, checksum-mismatched, unsupported, or GDP assets fail closed.

This slice does not yet invent a Cloud/SMB storage path. Runtime deployment must assign an explicit StorageService locator and preserve the registered checksum. It also does not reuse `copy_forward`.

Validate the local legacy evidence:

```powershell
py -m pytest tests/test_c5e_certificate_detail_source_asset_contract.py -q

py tools/audit_c5e_certificate_detail_source_asset_registry.py `
  --source-root "D:\GXP-QLCL\legacy\Templates"
```

Expected:

```text
STATUS=SOURCE_ASSET_REGISTRY_VERIFIED
ASSETS=6
VERIFIED=6
BLOCKERS=0
```
