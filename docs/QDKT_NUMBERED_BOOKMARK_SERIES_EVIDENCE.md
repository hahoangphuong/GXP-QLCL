# QĐKT — evidence interpretation for numbered Word bookmarks

The business owner has confirmed the convention: VBA writes a common logical value named `Tencoso` to multiple physical template bookmarks by appending an index. The four original DOTX packages, verified by their SHA-256 checksums and pinned in `tests/fixtures/inspection_qd_kt_observed_template_binaries.json`, contain exactly `Tencoso1`, `Tencoso2`, `Tencoso3` for each of GLP, GMP, GMPbb and GSP.

Thus the earlier exact-name comparison that labeled absent physical `Tencoso` as an error was **a false positive**. Exact-name absence can still be reported as a literal observation, but must not be used to claim that a numbered series is absent or broken.

The standalone `observe_numbered_bookmarks` collector reports numbered physical names, indices and whether the exact unnumbered name exists. It is **not** a substitute for inspecting the original VBA helper: although the recorded call for `Tencoso` uses `TenCtydd, 1, 8`, the helper's stopping rule, handling of missing bookmarks and exact write behaviour remain unverified here. Gaps are reported, not automatically deemed valid/invalid under VBA. Do not generalize to `TTx`, `Diadiemx`, `VKN` or other logical names without their relevant VBA call/helper proof.

The source `TenCtydd` is still traceable to the selected planning row and an alternate legacy site row; exact canonical Case/Site parity is not proven. The business data owner remains `OWNER_PARTIAL`; `ready_to_render=False`. No QĐKT creation, mutation, NAS interaction or template rewrite is permitted by this slice.
