# C.5e destination anchor child profile

The narrowed block-context gate found all 3 real destination anchors unsafe. This tool profiles the exact direct-child structure of those 3 `Pvi*` paragraphs without changing any renderer logic.

It records:

- direct child tag sequence;
- run child tags and attributes;
- visible text;
- bookmark markup.

Use the result to decide whether the blocking element is formatting-only and can be preserved/hoisted deterministically, or whether it is semantic content that must keep the gate closed.

Run:

```powershell
py tools/profile_c5e_certificate_detail_destination_anchor_children.py `
  --template-root "D:\GXP-QLCL\legacy\Templates"

py -m pytest `
  tests/test_profile_c5e_certificate_detail_destination_anchor_children.py -q
```

Then inspect the JSON output.
