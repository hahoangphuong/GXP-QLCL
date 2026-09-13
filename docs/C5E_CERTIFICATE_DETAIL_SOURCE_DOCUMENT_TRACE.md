# C.5e certificate-detail source-document trace

`Input_DC_to_CC` copies:

`wdDoc2.Bookmarks(Key2Bookmark(...)).Range.FormattedText`

into the destination certificate at bookmark `Pvi{GPs_T}`.

The already captured GMP/GLP certificate `.dotx` files are therefore **destination** templates. They are not sufficient to implement the copy because the formatted fragment originates in `wdDoc2`.

This tool searches the original VBA ZIP for **active callers** of `Input_DC_to_CC`, records the surrounding procedure with line provenance, and reports nearby:

- `Set <document> = ...` assignments;
- `Documents.Open` / related document-open calls;
- string literals that may identify the source template path/name.

Commented callers are ignored.

Run:

```powershell
py tools/trace_c5e_certificate_detail_source_document.py `
  --vba-zip "D:\GXP-QLCL\legacy\GXP-VBA code.zip"
```

Then inspect:

```powershell
Get-Content `
  .\artifacts\legacy_audit\c5e_certificate_detail_source_document_trace.json
```

Once the exact `wdDoc2` file is identified, capture that source Word file's bookmark structure and fragments before implementing any renderer change.
