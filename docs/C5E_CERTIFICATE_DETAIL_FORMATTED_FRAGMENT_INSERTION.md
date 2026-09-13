# C.5e formatted-fragment destination insertion primitive

The legacy evidence now proves:

- 802/802 source `L...` bookmarks can be extracted deterministically as `w:tbl` fragments;
- all 3 destination `Pvi` bookmarks are empty and share one bookmark geometry;
- the `Pvi` bookmark sits at the beginning of a paragraph whose suffix contains a heading that must be preserved.

Therefore the correct server-side block operation is **not** to replace the whole paragraph and **not** to nest `w:tbl` inside `w:p`.

This primitive inserts the source `w:tbl` as a sibling immediately before the destination paragraph, removes only the target `Pvi` bookmark markup, and preserves the paragraph suffix exactly.

It fails closed when:

- the destination bookmark is missing/duplicated;
- start/end are not adjacent direct children of the same paragraph;
- semantic content exists before the bookmark;
- the fragment is not a `w:tbl`;
- the fragment still contains bookmark markup.

This slice intentionally does not wire the primitive into document generation workflow or API ownership yet.
