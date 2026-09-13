# C.5e `Input_DC_to_CC` contract candidate

The semantic evidence shows that the active VBA path performs a dynamic **formatted bookmark fragment copy** and has no direct row/cell mutation. Therefore this slice intentionally rejects the earlier assumption that generic table-row cloning is the primary replacement primitive.

The candidate builder reads only:

`tests/fixtures/c5e_certificate_detail/Input_DC_to_CC.active.bas`

It preserves every active line with line provenance and classifies:

- dynamic `Key2Bookmark(...)` source bookmark copy;
- selection text writes and movement;
- `PV_map` / `PV_Desc`;
- main-topic and primary/secondary-pack branches;
- `EngPart`;
- scope notes/name/data;
- `SplitLines` and translation helpers.

The expected source bookmark transform is taken from the captured `Key2Bookmark` helper:

1. trim key;
2. remove trailing `.`;
3. prefix `L`;
4. replace `.` with `_`.

The candidate remains review evidence, not production implementation. In particular, preserving `Range.FormattedText` may require a dedicated DOCX fragment-copy primitive rather than plain scalar text or table-row cloning.

Run:

```powershell
py tools/build_c5e_certificate_detail_contract_candidate.py

py -m pytest `
  tests/test_c5e_certificate_detail_contract_candidate.py -q
```

Then provide:

```powershell
Get-Content `
  .\artifacts\legacy_audit\c5e_certificate_detail_contract_candidate.json
```

No `unkeyed_entries`, compact-summary text, historical prose, or commented VBA may be used.
