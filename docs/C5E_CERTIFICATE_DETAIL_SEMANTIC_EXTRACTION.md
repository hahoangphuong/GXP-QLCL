# C.5e Certificate-detail semantic extraction

This step consumes only the sanitized fixtures created by `capture_c5e_certificate_detail_evidence.py`.

It does not modify production code and does not attempt to reproduce `Input_DC_to_CC` yet.

The audit extracts, with source-line references:

- literal bookmark access;
- `Key2Bookmark(...)` dynamic mapping calls;
- copy/paste/formatted-text operations;
- row/cell operations;
- branch and loop statements;
- string literals;
- active helper bodies;
- captured certificate template bookmarks and bookmarked table rows.

The purpose is to make the next semantic contract reviewable from deterministic evidence rather than from a prose interpretation of the VBA.

The audit deliberately excludes VBA comments. `Input_DC_to_CC2` or other commented historical variants therefore cannot become active evidence.

Run:

```powershell
py tools/audit_c5e_certificate_detail_semantics.py

py -m pytest `
  tests/test_capture_c5e_certificate_detail_evidence.py `
  tests/test_c5e_certificate_detail_semantics_audit.py -q
```

Then inspect:

```powershell
Get-Content `
  .\artifacts\legacy_audit\c5e_certificate_detail_semantic_extraction.json
```

Do not stage or implement the renderer until the extracted report has been reviewed and the row-level mapping is explicit.
