# C.5e cross-container bookmark geometry profile

The real legacy source documents contain 802 `L...` bookmarks, and all of them span beyond a single XML parent. Therefore same-parent extraction is not a valid model.

This tool does not copy fragments and does not modify renderer code. It profiles each bookmark's geometry:

- start/end XML path;
- start/end parent tags;
- lowest common ancestor;
- same paragraph/cell/row/table flags;
- document-order distance;
- tag counts between start and end.

The output aggregates distinct geometry shapes across all source documents. A small finite shape set is the prerequisite for a deterministic WordprocessingML range extractor.

Run:

```powershell
py tools/profile_c5e_certificate_detail_cross_container_bookmarks.py `
  --source-root "D:\GXP-QLCL\legacy\Templates"
```

Then:

```powershell
py -m pytest `
  tests/test_profile_c5e_certificate_detail_cross_container_bookmarks.py -q
```

Inspect at minimum:

- `summary.distinct_shape_count`
- `summary.global_shape_counts`
- `summary.unresolved_bookmarks`

No production document generation behavior changes in this slice.
