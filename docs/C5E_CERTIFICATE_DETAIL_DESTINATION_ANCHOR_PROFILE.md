# C.5e destination `Pvi*` anchor profile

Source fragment extraction is now proven for all 802 legacy `L...` bookmarks. Before implementing insertion, the destination bookmark geometry must also be explicit.

This audit scans candidate legacy destination templates for bookmarks whose names begin with `Pvi` and records:

- start/end parent tags;
- same paragraph/cell/table flags;
- start/end ordinal within parent;
- whether the bookmark is empty when start/end share a parent;
- ancestor paths.

It does not modify templates or production renderer code.

Run:

```powershell
py tools/profile_c5e_certificate_detail_destination_anchors.py `
  --template-root "D:\GXP-QLCL\legacy\Templates"

py -m pytest `
  tests/test_profile_c5e_certificate_detail_destination_anchors.py -q
```

Then inspect `summary` from:

`artifacts/legacy_audit/c5e_certificate_detail_destination_anchor_profile.json`

The insertion primitive should only be implemented for geometry actually observed here.
