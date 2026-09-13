# C.5e source formatted-fragment capture

The active VBA caller trace proves that `Input_DC_to_CC` receives its formatted source content from:

- `9. Phamvi{S_GPs}.docx` for certificate issuance;
- `z3. Phamvi{GPs_T}.docx` for DDKD appendix generation.

Those documents are separate from the destination certificate templates.

This tool captures every bookmark beginning with `L` from those source Word documents and records:

- source file SHA-256;
- bookmark name;
- visible text;
- exact XML inside the bookmark range;
- fragment SHA-256;
- run properties;
- paragraph properties;
- whether the fragment contains runs, paragraphs, or tables.

The first implementation deliberately supports only bookmark start/end pairs located under the same XML parent. Any cross-container bookmark span is reported as a blocker rather than reconstructed heuristically.

Run against the legacy template directory:

```powershell
py tools/capture_c5e_certificate_detail_source_fragments.py `
  --source-root "D:\GXP-QLCL\legacy\Templates"
```

Then run:

```powershell
py -m pytest `
  tests/test_capture_c5e_certificate_detail_source_fragments.py -q
```

Inspect:

```powershell
Get-Content `
  .\artifacts\legacy_audit\c5e_certificate_detail_source_fragments.json
```

No production renderer code is changed by this slice.
