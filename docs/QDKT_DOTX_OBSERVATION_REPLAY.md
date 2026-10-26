# QĐKT — offline repeatability of four uploaded template observations

The original four DOTX uploads were inspected read-only on 2026-10-26 and the resulting hashes and bookmark-name sets are pinned in `tests/fixtures/inspection_qd_kt_observed_template_binaries.json` (PR #134).

`require_matching_qdkt_binary_observations(directory)` repeats the existing SHA-256, OPC template-part and Word bookmark checks against four local files named exactly as the manifest declares. It then compares the **complete observed physical bookmark-name set** and count for every GxP against the pinned fixture. Missing, altered or stale metadata and changed physical names are rejected. The uploaded originals were named with a `(2)` suffix; use read-only copies under their manifest filenames in a separate temporary directory to repeat the check. Do not rename or mutate the originals.

This replay is deliberately offline and internal. CI uses adversarial synthetic measurements to test the comparison logic, not real copies of the user's binary uploads. This is **binary evidence repeatability only**, not an approval that a VBA trace symbol maps to a bookmark, source Case data, a populated DOCX or an issued QĐKT. All 14 bookmark owners remain blocked/partial and `ready_to_render=False`.
