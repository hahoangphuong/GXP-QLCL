# C.5e destination block-replacement context gate

The source `Input_DC_to_CC` fragment is a table-level Word range. The destination `Pvi*` bookmark is inside a paragraph.

A `w:tbl` cannot be inserted as a child of `w:p`. Therefore server-side parity must model Word's block-level replacement behavior, not append a table inside the paragraph.

This gate proves whether the destination paragraph can safely be replaced as a whole. It requires:

- bookmark start/end are direct children of the same `w:p`;
- paragraph has no visible text;
- paragraph has no semantic direct children other than formatting-only runs;
- no unrelated bookmark markup is present.

If any condition fails, the future insertion primitive must fail closed.

Run:

```powershell
py tools/audit_c5e_certificate_detail_destination_block_context.py `
  --template-root "D:\GXP-QLCL\legacy\Templates"

py -m pytest `
  tests/test_c5e_certificate_detail_destination_block_context.py -q
```

Expected before implementing block insertion:

```text
STATUS=DESTINATION_BLOCK_REPLACEMENT_PROVEN
ANCHORS=3
BLOCK_REPLACE_SAFE=3
UNSAFE=0
```
