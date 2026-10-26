# QĐKT dossier code/date legacy source pair

Source-pin: `artifacts/legacy_audit/inspection_qd_kt_input_provenance.json`, provenance from `legacy/GXP-VBA code.zip` SHA-256 `6227fb0a6b3d74fa0f4cc655b94b021a40d65a508c2f2eefc62f1724c7b89ff7`.

`RecordForm.frm:343` assigns both variables from the same `Rg3` row in `db.ktra`: `s_MaHsDk` from `ColDB_HSDK_Ktra + 1` and `s_NgaynopHsDk` from `ColDB_HSDK_Ktra`. The QĐKT i=2 calls at lines 748–749 try writing those values to the exact bookmarks `HsDK` and `NgaynopHsDK` respectively. The latter call uses `Replace(s_NgaynopHsDk, "-", "/")`, a string substitution (not proof of date type or chronological validity).

The new read-only inspection and adversarial tests pin the common legacy row, distinct columns, exact expressions and SOURCE_ZIP hash. Combined with PR #139's binary evidence, neither exact bookmark exists in the four observed templates. This does not prove whether these fields should appear in a newly issued decision, whether they refer to submission or receipt, or which current `CaseApplication` fields own them. Both are `OWNER_PARTIAL`; `ready_to_render=False`. No template rewrite, Case mutation or rendering is enabled.
