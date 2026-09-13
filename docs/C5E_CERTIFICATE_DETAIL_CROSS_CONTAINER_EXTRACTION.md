# C.5e deterministic cross-container bookmark extractor

The geometry audit reduced all 802 observed legacy `L...` bookmarks to two shapes:

1. start parent `w:p`, end parent `w:p`, LCA `w:tbl` — 796 bookmarks;
2. start parent `w:p`, end parent `w:tbl`, LCA `w:tbl` — 6 bookmarks.

This shadow extractor supports exactly those two shapes and fails closed for anything else.

For each bookmark it:

- finds `bookmarkStart` and matching `bookmarkEnd`;
- verifies geometry is one of the two audited shapes;
- clones the intersecting portion of the common `w:tbl`;
- prunes all XML outside the bookmark range;
- strips all bookmark markup from the clone to avoid duplicate bookmark IDs;
- records visible text, row/cell/paragraph counts, exact XML, and SHA-256.

It does **not** modify `backend/app/document/docx_template_render.py` and does not yet insert the fragment into a destination document. The next gate is 802/802 successful extraction on the real legacy source templates.

Run:

```powershell
py tools/extract_c5e_certificate_detail_cross_container_fragments.py `
  --source-root "D:\GXP-QLCL\legacy\Templates"

py -m pytest `
  tests/test_extract_c5e_certificate_detail_cross_container_fragments.py -q
```

Expected on real evidence before renderer integration:

```text
STATUS=CROSS_CONTAINER_FRAGMENTS_EXTRACTED
DOCUMENTS=6
BOOKMARKS=802
EXTRACTED=802
ERRORS=0
```

No `unkeyed_entries`, compact summary, historical prose, or commented VBA are used.
