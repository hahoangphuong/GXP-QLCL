# QĐKT — evidence interpretation for numbered Word bookmarks

The business owner has confirmed the convention: VBA writes a common logical value named `Tencoso` to multiple physical template bookmarks by appending an index. The four original DOTX packages, verified by their SHA-256 checksums and pinned in `tests/fixtures/inspection_qd_kt_observed_template_binaries.json`, contain exactly `Tencoso1`, `Tencoso2`, `Tencoso3` for each of GLP, GMP, GMPbb and GSP.

Thus the earlier exact-name comparison that labeled absent physical `Tencoso` as an error was **a false positive**. Exact-name absence can still be reported as a literal observation, but must not be used to claim that a numbered series is absent or broken.

The standalone `observe_numbered_bookmarks` collector reports numbered physical names, indices and whether the exact unnumbered name exists. It remains a generic observation layer and does not infer VBA behavior from a prefix.

The follow-up source-parity contract in `inspection_qd_kt_vba_bookmark_series.py` independently inspects and pins `legacy/GXP-VBA code.zip`: `Replace_Bookmark` uses an inclusive caller-supplied range, keeps attempting later indices after a missing bookmark under `On Error Resume Next`, and repeats the same value at every existing target. For the real `CreateFile(i=2)` route this proves `Tencoso1..8` are attempted; the four checksum-pinned templates expose effective targets `Tencoso1..3`. It separately proves `Diadiemx1..3`, conditional GMP/GLP-only `VKN1..2`, exact `VKNx`, dynamic `TT1x`/`TT2x`, conditional exact `TT3x`, and DELETE-only `TT3Del`. These are distinct rules; the generic observer alone must still not be used to generalize another logical prefix.

The source `TenCtydd` is still traceable to the selected planning row and an alternate legacy site row; exact canonical Case/Site parity is not proven. The business data owner remains `OWNER_PARTIAL`; `ready_to_render=False`. No QĐKT creation, mutation, NAS interaction or template rewrite is permitted by this slice.
