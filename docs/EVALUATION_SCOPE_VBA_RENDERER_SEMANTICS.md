# Evaluation Scope VBA Renderer Semantics

Status: source-derived contract for the VBA-to-Python evaluation-scope summary port.

This document describes **legacy VBA behavior**, not the current Python renderer and not historical prose as a byte-level oracle. Unless explicitly marked otherwise, evidence comes from the source-controlled VBA under `artifacts/legacy_audit/vba_sources/GPs/`.

## 1. Semantic authority and output classes

The forward implementation contract is:

```text
canonical persisted evaluation scope
    -> VBA-derived semantic compiler
    -> owned semantic fragments/spans emitted during compilation
    -> human-readable summary + provenance
```

Three outputs must remain distinct:

1. **VBA algorithmic projection** — the business-rule target of the port.
2. **Historical `db.ktra` rendered prose** — migration/history evidence; it can be stale or reflect an older payload/state.
3. **Current Python canonical projection** — compatibility/reference implementation during the transition.

Neither (2) nor (3) is the semantic oracle for the VBA port, and byte equality with either is not required unless a later gate explicitly requires compatibility for a particular use case.

Provenance must be emitted while compiling. Reverse ownership by `text.find`, substring matching, or regex reconstruction is not part of the forward design.

## 2. Active entry points and compile call chain

### 2.1 UI/edit entry

**PROVEN_ACTIVE** — `DCForm.frm :: Edit_DC`

`Edit_DC` sets `Sel_GPs`, parses old/new stored representations via `Get_DCx`, initializes the form, then returns `GetData`. When the form uses the new format, `GetData` persists both readable compiled prose and the structured payload.

`MainForm.frm` calls `DCForm.Edit_DC(...)` when editing the inspection evaluation scope and then writes `DCForm.DaychuyenSum` back to the inspection source field.

### 2.2 Per-block human-readable compilation

**PROVEN_ACTIVE** — `DCForm.frm :: Get_DC_Name_Desc`

For one serialized scope block, `Get_DC_Name_Desc`:

1. parses optional block name (`¶`) and note (`¿`),
2. loads structured node rows with `LoadNodeList`,
3. compiles the node list with `Compile_PVCN`,
4. prepends the display header `« <name> »` and optional ` (<note>)`, followed by `vbCrLf` when a header exists.

**PROVEN_ACTIVE call chain:**

```text
Get_DC_Name_Desc
    -> LoadNodeList
    -> Compile_PVCN
        -> Compile_Node_Full
            -> Compile_Node
            -> CleanText
        -> GMP only: VietChitiet_PVDG_GMP
        -> GMP only: VietChitiet_PVXX_GMP
```

`RecordForm.frm :: Input_DC_to_CC` also calls `DCForm.Get_DC_Name_Desc`, proving that this compile path is consumed by document-generation workflows as well as by the editor.

### 2.3 GMP combine routine

**PROVEN_INACTIVE at the active call site** — `DCForm.frm :: Compile_PVCN`

The call to `VietGop_PVCN_GMP(rs)` is commented out. The active GMP post-processing calls are instead:

```vb
Call VietChitiet_PVDG_GMP(rs)
Call VietChitiet_PVXX_GMP(rs)
```

`VietGop_PVCN_GMP` remains legacy code/evidence but must not be ported as active behavior unless another proven active caller is found.

## 3. Taxonomy source and column semantics

### 3.1 Named-range selection

**PROVEN_ACTIVE** — `DCForm.frm :: Init_PVCN`

| `Sel_GPs` | Named range requested by VBA | Current canonical taxonomy availability |
|---:|---|---|
| 1 | `PVCN_GMP` | AVAILABLE |
| 2 | `PVCN_GLP` | AVAILABLE |
| 3 | `PVCN_GSP` | AVAILABLE |
| 4 | none / erased | not a taxonomy compile family |
| 5 | `PVCN_GMP` | AVAILABLE (GMP taxonomy reused) |
| 6 | `PVCN_GDP` | **MISSING in current extracted workbook artifact** |

The current source-controlled taxonomy artifact explicitly reports GDP as unavailable because `PVCN_GDP` is not defined in the legacy workbook snapshot. Therefore the Python port must **fail closed for GDP taxonomy compilation** unless a valid source taxonomy is later supplied. It must not alias GDP to GMP.

### 3.2 Column indexes

**PROVEN_ACTIVE** — constants near the top of `DCForm.frm`:

| VBA constant | Column | Semantic role | Compile relevance |
|---|---:|---|---|
| `PVCN_colKey` | 1 | hierarchical node key | direct |
| `PVCN_colDesc` | 2 | full/source description | direct in GMP detail expansion; UI/document output |
| `PVCN_colGoiy` | 4 | hint/suggestion | UI edit support; not directly used by core summary compiler shown here |
| `PVCN_colMainTopic` | 6 | main-topic indicator | tree/edit behavior; affects whether a node is directly checkable/edited as a main topic |
| `PVCN_colViettat` | 7 | short-render/template text | primary summary compile source |
| `PVCN_colNoExpanded` | 8 | no-expand/tree hint | UI/tree expansion behavior; not proven as summary text input |

The canonical `EvaluationScopeTaxonomyNode` already persists `node_key`, `description`, `hint`, `main_topic`, `short_render`, `no_expand`, `source_order`, and `source_excel_row`.

## 4. Stored structured payload and block serialization

### 4.1 New-format outer envelope

**PROVEN_ACTIVE** — `DCForm.frm :: GetData`, `Get_DC_cu`, `Get_DC_moi`, `Get_DC_gh`

For new-format data, `GetData` constructs:

```text
<compiled human-readable blocks>
(*<limitation>*)              # only when limitation is nonblank
{<structured blocks joined by §>}*
```

The final `}*` is the new-format sentinel used by `Check_DC_NF` and parsing helpers.

The readable prose before `{...}*` is not the structured source-of-truth. The structured payload inside `{...}*` plus taxonomy is the semantic input for deterministic re-compilation.

### 4.2 Multi-block delimiter `§`

**PROVEN_ACTIVE** — `DCForm.frm :: SplitDC`, `GetData`

`DaychuyenSum` is split on `§` to recover multiple scope/site blocks. `GetData` joins `iDaychuyen` with `§` when saving the structured payload.

`§` is therefore **structured serialization**, not a human-readable summary delimiter. Human-readable block summaries are joined separately with `vbCrLf` through `iDC_Comp`.

### 4.3 Block name delimiter `¶`

**PROVEN_ACTIVE** — `DCForm.frm :: Get_DC_Name_Desc`, `Update_Daychuyen_Ls`

`Update_Daychuyen_Ls` serializes the block name as:

```text
<name>¶<node-list>¿<note>
```

`Get_DC_Name_Desc` locates the first `¶`; when present after position 1 it treats text through that delimiter as the stored name segment. Human-readable rendering removes the terminal delimiter and produces:

```text
« <name> »
```

### 4.4 Note delimiter `¿`

**PROVEN_ACTIVE** — `DCForm.frm :: Get_DC_Name_Desc`, `Update_Daychuyen_Ls`

The last `¿` separates the structured node list from the optional block note. Human-readable rendering appends a nonblank note as:

```text
 (<note>)
```

on the same header line as `« <name> »` when a name exists.

### 4.5 Limitation `(* ... *)`

**PROVEN_ACTIVE** — `DCForm.frm :: GetData`, `Get_DC_gh`, `Get_Full_DC`

The limitation is serialized outside the `{...}*` structured node payload as `(*<text>*)` immediately before it. `Get_DC_gh` extracts it. `Get_Full_DC` likewise appends it to compiled text before the structured payload.

The core `Compile_PVCN` procedure does **not** compile limitation text. Limitation is a separate outer-layer contribution and must retain separate provenance in Python.

## 5. Structured node-list parsing

### 5.1 `LoadNodeList`

**PROVEN_ACTIVE** — `DCForm.frm :: LoadNodeList`

Input is the structured block node-list text. Processing is source-order preserving:

1. remove `vbLf`, split on `vbCr`,
2. trim each line,
3. parse key/description using `Get_Key_Desc`,
4. validate the key against the active taxonomy,
5. store valid keyed lines in `CurNodes` in input order and populate `PV_map`,
6. mark invalid/unkeyed lines temporarily,
7. append those unkeyed lines to `CurNodes` after keyed rows.

A keyed `PVNodeType` stores at least:

- `skey` — taxonomy key,
- `sDesc` — persisted/custom description,
- `iGidx` — taxonomy row index,
- `iLine` — source line index.

### 5.2 `Get_Key_Desc`

**PROVEN_ACTIVE**

The parser first searches for `:`; if absent, the first space separates key from description. The key is trimmed and validated numerically/hierarchically against the taxonomy. Description is the trimmed remainder.

### 5.3 Unkeyed entries

**PROVEN_ACTIVE as persisted structured data; NOT part of `Compile_PVCN` node loop**

`LoadNodeList` appends invalid/unkeyed lines to `CurNodes` with blank `skey` and populated `sDesc`. `Compile_PVCN` only calls `Compile_Node_Full` when `LNodes(i).skey <> vbNullString`, so unkeyed entries are **not emitted by the core VBA summary compiler shown here**.

This is important for the Python port: current canonical persistence has `CaseEvaluationScopeUnkeyedEntry`, but automatically inserting those entries into a VBA-faithful summary would be a behavior extension. They must remain preserved as canonical data and provenance, while summary emission requires an explicit product decision or additional proven VBA path.

## 6. Tree selection and ancestor semantics

### 6.1 Tri-state checkbox model

**PROVEN_ACTIVE UI behavior** — `clsNode.cls :: Checked`, `CheckTriStateParent`, `CheckTriStateChildren`

Checkbox values are:

- `-1` = checked,
- `0` = unchecked,
- `+1` = mixed.

When tri-state is enabled:

- changing a node propagates its checked state down through children,
- parents recompute to checked only when all children are checked,
- parents recompute to unchecked only when all children are unchecked,
- otherwise the parent becomes mixed,
- mixed propagates upward.

This is primarily **tree/UI state behavior**. The persisted structured node list, not the transient `Checked` value itself, is what `Compile_PVCN` consumes.

### 6.2 Main-topic nodes

**PROVEN_ACTIVE tree/edit behavior** — `DCForm.frm :: AddNode2`, `SetNodeValue`, `mcTree_DblClick`, `mcTree_NodeCheck`

A row whose `PVCN_colMainTopic` is nonblank is treated differently from a normal selectable leaf:

- `AddNode2` does not directly set its checkbox from the persisted keyed-row check flag,
- main-topic custom text is displayed as `(<custom>)` in the tree caption,
- editing a new main-topic value requires at least one child selection,
- normal non-main-topic custom descriptions can create runtime subnodes.

For **summary compilation**, however, main-topic rows can still appear as taxonomy ancestors through `Compile_Node_Full`; their `short_render` determines whether they emit summary text.

### 6.3 Required ancestor restoration

**PROVEN_ACTIVE compile behavior** — `DCForm.frm :: Compile_Node_Full`

For each keyed selected node, `Compile_Node_Full` derives each dotted ancestor prefix, looks it up in the taxonomy, and emits it once if not already in `NodeMap` and its cleaned `short_render` is nonblank.

Therefore a parent/ancestor does not need to be persisted as a separate selected row to contribute structural summary text.

This is the semantic basis for the current canonical read model's concept of required ancestors.

## 7. Runtime subnodes from custom descriptions

**PROVEN_ACTIVE UI behavior** — `DCForm.frm :: SetNodeValue`

For a non-main-topic node with nonblank custom description, VBA splits the description on `;` and creates runtime child nodes with synthetic keys:

```text
<parent-key>.1+
<parent-key>.2+
...
```

The runtime child caption is each trimmed segment. These children support tree navigation/editing and selection targeting inside the persisted custom description.

The persisted semantic owner remains the parent node's `sDesc` string; runtime `+` subkeys are not independent taxonomy nodes.

The current canonical model preserves the parent `custom_description`, which is sufficient to deterministically reconstruct these UI runtime children when needed. Independent persistence of synthetic subnodes is **not required for summary compilation**.

## 8. Core node compilation: `Compile_Node`

**PROVEN_ACTIVE** — `DCForm.frm :: Compile_Node`

`Compile_Node` is the source-derived owner for selected-node short-render/custom-description composition.

### 8.1 Inputs

For the selected `LNodes(idx)`:

- taxonomy row = `LNodes(idx).iGidx`,
- template/short-render = `PVCN_GxP(j, PVCN_colViettat)`,
- custom description = `LNodes(idx).sDesc`.

If the taxonomy index is invalid or `short_render` is blank, the function emits nothing.

### 8.2 `<` marker

**PROVEN_ACTIVE**

When the very first character of `short_render` is `<`:

1. `Compile_Node` emits a literal leading `<` into its intermediate result,
2. removes `<` from the taxonomy template before the rest of composition,
3. increments the internal `sp` offset used for position tracking.

Later, `Compile_PVCN` executes:

```vb
rs = Replace(rs, vbCr & "<", vbNullString, ...)
```

Thus `<` is a **continuation/join instruction**: when a compiled line begins with `<`, its preceding carriage-return plus `<` is removed, joining it to the preceding output line. `<` itself is not visible in the final summary.

This differs from the old Python helper's simplified boolean interpretation and must be ported from this actual two-stage behavior.

### 8.3 `&` marker

**PROVEN_ACTIVE**

After optional leading `<` handling, if the first character of the remaining short-render is `&`:

- when `sDesc` is **blank**, VBA removes `&` and emits the remaining short-render text;
- when `sDesc` is **nonblank**, VBA suppresses the taxonomy short-render text entirely at this stage.

The custom-description branch then still executes:

- if the original short-render contained `$$`, substitute into the current intermediate result,
- otherwise append `": " & sDesc` to the current result.

Therefore `&` is not simply "strip ampersand". With nonblank custom description it suppresses the taxonomy text and leaves the custom-description composition branch to provide visible content.

Any Python port must preserve this branch order exactly rather than infer ownership from the final string.

### 8.4 `$$` marker

**PROVEN_ACTIVE**

`j = InStr(1, s, "$$", ...)` is computed from the taxonomy short-render before `<`/`&` mutation.

When custom description is nonblank and `j > 0`, VBA substitutes only the **first** `$$` occurrence with `sDesc`:

```vb
rs = Replace(rs, "$$", sDesc, 1, 1, ...)
```

When custom description is blank, no substitution occurs; `CleanText` subsequently removes template forms ` ($$)`, `($$)`, ` $$`, or `$$`.

This proves template-slot ownership structurally. The Python port must create taxonomy-prefix, custom-description, and taxonomy-suffix fragments directly from the template position; it must not locate the custom text afterward by string search.

### 8.5 Custom description without `$$`

**PROVEN_ACTIVE**

When `sDesc` is nonblank but the taxonomy short-render contains no `$$`, VBA appends:

```text
: <sDesc>
```

to the current intermediate result.

Because this happens after the `&` branch, an `&` template with nonblank description can reduce to only `: <sDesc>` (subject to subsequent cleanup). The Python port must reproduce the actual branch output first; presentation policy changes, if any, belong to a separate decision.

### 8.6 `CleanText`

**PROVEN_ACTIVE** — `DCForm.frm :: CleanText`

`CleanText` removes at most the first occurrence of these marker forms in sequence:

```text
 ($$)
($$)
 $$
$$
```

When optional `Ext=True`, it additionally removes the first `": "` occurrence.

`CleanText2` runs `CleanText`, trims, and removes a final `:`.

### 8.7 Node terminator and local cleanup

**PROVEN_ACTIVE**

After `CleanText`:

- if the result does **not** end in `(`, append `"; "`,
- if it ends in `(`, do not append the semicolon terminator.

Then local cleanup applies:

```text
"; ;" -> ";"
";;"  -> ";"
"::"  -> ":"
": ;" -> ":"
"; )" -> ")"
";)"  -> ")"
```

These are compiler-owned transformations and should be represented in the Python compiler as semantic/token composition rules, not post-hoc ownership recovery.

## 9. Ancestor/full compilation: `Compile_Node_Full`

**PROVEN_ACTIVE**

For each selected keyed node:

1. derive dotted ancestors in top-down prefix order,
2. emit each ancestor at most once using `NodeMap`,
3. ancestor output is `CleanText(PVCN_colViettat)` plus `vbCr`, provided it is nonblank,
4. maintain group-parent state based on an emitted fragment ending in `(`,
5. compile the selected node through `Compile_Node`,
6. close an active parent group when the next key no longer belongs to the current group-parent key,
7. update positional metadata used by UI highlighting and later GMP post-processing.

### 9.1 Group-parent open

**PROVEN_ACTIVE** — `Check_Open_ParentMode`

If trimmed emitted text ends with `(`:

```text
GroupParentNodeMode = True
GroupParentNodeKey = current key
```

### 9.2 Group-parent close

**PROVEN_ACTIVE** — `Check_Close_ParentMode`

When a subsequent key no longer starts with `GroupParentNodeKey`, VBA emits:

```text
<)
```

and clears group mode. The leading `<` participates in the same continuation handling performed later in `Compile_PVCN`.

If compilation ends while group mode remains open, `Compile_PVCN` appends `).`.

## 10. Whole-scope compilation: `Compile_PVCN`

**PROVEN_ACTIVE**

`Compile_PVCN` initializes `NodeMap`, `TopicNodes`, position state, and group state; it then processes each keyed `LNodes` row in input order through `Compile_Node_Full` and appends `vbCr` after each call.

After traversal it performs whole-result composition cleanup:

1. `vbCr & "<"` -> empty string, joining continuation lines,
2. remove trailing `vbCr`,
3. close remaining group with `).` if necessary,
4. append one `vbCr`,
5. cleanup:
   - `"; )" -> "); "`
   - `";)" -> ") "`
   - `".)" -> ") "`
   - `";" & vbCr -> "." & vbCr`
   - `"; " & vbCr -> ". " & vbCr`
   - `") ." -> ")."`
6. remove trailing `vbCr`,
7. for `Sel_GPs = 1` apply the two active GMP detail procedures,
8. return `Trim(rs)`.

This whole-scope stage owns final line punctuation and continuation/group materialization.

## 11. GMP-specific active post-processing

### 11.1 `VietChitiet_PVDG_GMP`

**PROVEN_ACTIVE for `Sel_GPs = 1`**

The procedure first derives packaging-scope substrings with `Get_PV_Dgoi`. It then scans taxonomy rows from the aseptic region through the primary-packaging boundary. Where a taxonomy key is found inside the primary or secondary packaging scope, it replaces that compact key token in the already-compiled summary with the taxonomy **full description** (`PVCN_colDesc`) and updates stored position metadata.

Semantic effect: compact packaging-scope key references are expanded to human-readable taxonomy descriptions after the main compile.

### 11.2 `VietChitiet_PVXX_GMP`

**PROVEN_ACTIVE for `Sel_GPs = 1`**

Analogously, `Get_PV_XXuong` derives scope text for the configured manufacturing/release categories (`XXVT`, `XXKVT`, `XXSH`, `XXDL`). Matching compact keys are replaced in the compiled result with taxonomy full descriptions and position metadata is updated.

### 11.3 Positional row constants

**PROVEN_ACTIVE but taxonomy-version-sensitive**

The VBA uses fixed source-row indexes such as `PVCN_rowAseptic`, `PVCN_rowPriPack`, `PVCN_rowXXVT`, etc. These indexes are positions inside the legacy named-range array, not semantic IDs.

For the Python port, these must **not** become unexplained magic database row numbers. The port should resolve the equivalent semantic taxonomy nodes from the versioned taxonomy source while retaining an explicit source-derived mapping/test. If an exact mapping cannot be proven for a taxonomy version, the GMP detail transformation must fail closed rather than shift to a neighboring row.

## 12. Tree expansion and summary relevance

### 12.1 `no_expand`

**PROVEN_ACTIVE UI behavior; NOT PROVEN summary behavior**

`PVCN_colNoExpanded` is consumed by tree expansion state (`PV_TreeExpand`). No direct use in `Compile_Node`, `Compile_Node_Full`, or `Compile_PVCN` was found. Therefore it should not alter summary text in the port unless another active source path proves otherwise.

### 12.2 `hint`

**PROVEN_ACTIVE UI edit support; NOT PROVEN summary input**

`PVCN_colGoiy` is passed to the edit dialog (`SuaPVCN.Get_PVCN`). No direct compile use in the core summary path is proven.

## 13. Current canonical persistence -> VBA semantic input mapping

| VBA semantic input | Current canonical owner | Availability | Notes |
|---|---|---|---|
| GxP type / taxonomy family | `Case.gxp_type` + taxonomy version | AVAILABLE | GDP taxonomy currently unavailable in extracted source artifact |
| taxonomy version | `CaseEvaluationScope.taxonomy_version_id` | AVAILABLE for structured imported scopes | structured scopes retain their persisted version |
| taxonomy key | `EvaluationScopeTaxonomyNode.node_key` / selection snapshot | AVAILABLE | direct equivalent of `PVCN_colKey` |
| source/full description | `EvaluationScopeTaxonomyNode.description` | AVAILABLE | equivalent of `PVCN_colDesc` |
| hint | `EvaluationScopeTaxonomyNode.hint` | AVAILABLE | equivalent of `PVCN_colGoiy` |
| main-topic marker | `EvaluationScopeTaxonomyNode.main_topic` | AVAILABLE | equivalent of `PVCN_colMainTopic` |
| short-render template | `EvaluationScopeTaxonomyNode.short_render` | AVAILABLE | equivalent of `PVCN_colViettat` |
| no-expand marker | `EvaluationScopeTaxonomyNode.no_expand` | AVAILABLE | UI behavior |
| taxonomy source order | `EvaluationScopeTaxonomyNode.source_order` | AVAILABLE | deterministic order independent of DB UUID |
| legacy source row | `EvaluationScopeTaxonomyNode.source_excel_row` | AVAILABLE | useful for auditing old positional GMP constants |
| selected keyed node | `CaseEvaluationScopeSelection.taxonomy_node_id` | AVAILABLE | canonical selection owner |
| persisted/custom node description | `CaseEvaluationScopeSelection.custom_description` | AVAILABLE | equivalent to keyed `PVNodeType.sDesc` |
| node key snapshot | `CaseEvaluationScopeSelection.node_key_snapshot` | AVAILABLE | legacy evidence/fence |
| taxonomy description snapshot | `CaseEvaluationScopeSelection.taxonomy_description_snapshot` | AVAILABLE | evidence; live compile should use persisted taxonomy version semantics |
| block ordinal | `CaseEvaluationScopeBlock.ordinal` | AVAILABLE | deterministic multi-block ordering |
| block name | `CaseEvaluationScopeBlock.name` | AVAILABLE | `¶` serialization semantic |
| block note | `CaseEvaluationScopeBlock.note` | AVAILABLE | `¿` serialization semantic |
| raw block value | `CaseEvaluationScopeBlock.raw_block_value` | AVAILABLE | evidence only; not required to recompile structured semantics |
| limitation | `CaseEvaluationScope.limitation_text` | AVAILABLE | outer-layer `(*...*)` contribution |
| unkeyed line | `CaseEvaluationScopeUnkeyedEntry.text` + `source_order` | AVAILABLE | preserved but core `Compile_PVCN` does not emit it |
| historical readable prose | `CaseEvaluationScope.rendered_prose` | AVAILABLE | historical presentation evidence, not semantic input |
| raw legacy aggregate | `CaseEvaluationScope.raw_legacy_value` | AVAILABLE | historical evidence, not semantic input for current structured compilation |
| tree checked/mixed transient state | not persisted as independent field | DERIVABLE for editor from selections/tree hierarchy | not required by core summary compiler |
| runtime `+` subnodes | not persisted independently | DERIVABLE from non-main-topic custom description split on `;` | UI construct, not independent taxonomy semantics |
| `PVCN_GDP` taxonomy | none in current artifact | **MISSING** | VBA has a code path but workbook taxonomy snapshot says unavailable |
| GMP positional semantic constants | taxonomy rows + source row/order | DERIVABLE WITH SOURCE MAPPING | must be mapped/tested explicitly, not assumed by numeric DB position |

## 14. Inputs that must fail closed or remain deferred

### 14.1 GDP taxonomy

**MISSING** in the current extracted taxonomy artifact. The port must not silently borrow another GxP taxonomy.

### 14.2 Unkeyed-entry summary emission

Canonical data exists, but the active `Compile_PVCN` core loop skips blank-key rows. Therefore summary emission of unkeyed entries is **NOT YET AUTHORIZED by VBA core compile evidence**. Preserve them exactly in data/provenance; do not silently drop them from canonical storage and do not silently inject them into a VBA-faithful summary.

### 14.3 Taxonomy-version-specific GMP positional rules

The data needed to derive a mapping exists, but a later implementation slice must prove each source-row/key mapping against the versioned taxonomy before activating GMP detail replacement.

## 15. Document-generation relationship

`RecordForm.frm :: Input_DC_to_CC` consumes the same structured block parser (`Get_DC_Name_Desc`, `Load_DC_Nodes`) but generates detailed Word content from taxonomy bookmarks rather than relying solely on the compact compiled summary. This proves two important ownership boundaries:

1. compact human-readable summary compilation is not the only consumer of structured evaluation scope;
2. later C.5e document payload fields must be mapped from the exact VBA/document contract, not blindly from one generic summary string.

This document therefore does **not** authorize feeding the compact VBA-port summary into `INSPECTION_QD_KT` or `INSPECTION_KE_HOACH_KT` payload fields without a separate source audit.

## 16. Python port contract

The next implementation slice should add an isolated shadow compiler whose internal helpers correspond visibly to the VBA responsibilities:

```text
parse canonical block inputs
    -> load selected node state / required ancestors
    -> compile_node            # VBA Compile_Node semantics
    -> compile_node_full       # ancestor + group semantics
    -> compile_scope           # VBA Compile_PVCN semantics
    -> apply active GMP detail transformations
    -> prepend block name/note
    -> append limitation at aggregate layer
```

### Required implementation properties

- deterministic ordering from the persisted taxonomy version and block/selection source order,
- owned spans/fragments emitted **during** compilation,
- taxonomy, custom-description, compiler delimiter, block metadata, and limitation ownership kept distinct,
- no `text.find`/substring reconstruction of semantic ownership,
- no fallback to current Python renderer inside the VBA-port path,
- unsupported/missing semantic inputs fail closed or are explicitly reported,
- current production renderer remains unchanged until shadow validation and an explicit cutover gate.

### Initial shadow validation should prove

- source-order traversal,
- required ancestor emission,
- `$$`, `&`, `<` behavior from the VBA branches above,
- group open/close behavior,
- local and whole-scope delimiter cleanup,
- multi-block name/note composition,
- limitation separation,
- active GMP detail transformations on source-proven taxonomy mappings,
- no dropped selected semantic contributions except source-proven structural/non-rendering nodes,
- complete owned-fragment provenance.

## 17. Source evidence index

Primary source references used in this contract:

- `DCForm.frm :: Init_PVCN`
- `DCForm.frm :: Edit_DC`
- `DCForm.frm :: GetData`
- `DCForm.frm :: Get_DC_cu / Get_DC_moi / Get_DC_gh`
- `DCForm.frm :: Get_DC_Name_Desc`
- `DCForm.frm :: SplitDC`
- `DCForm.frm :: Get_Key_Desc`
- `DCForm.frm :: LoadNodeList`
- `DCForm.frm :: Load_DC_Nodes`
- `DCForm.frm :: SetNodeValue`
- `DCForm.frm :: mcTree_DblClick / mcTree_NodeCheck`
- `DCForm.frm :: CleanText / CleanText2`
- `DCForm.frm :: Check_Open_ParentMode / Check_Close_ParentMode`
- `DCForm.frm :: Compile_Node`
- `DCForm.frm :: Compile_Node_Full`
- `DCForm.frm :: Compile_PVCN`
- `DCForm.frm :: VietChitiet_PVDG_GMP`
- `DCForm.frm :: VietChitiet_PVXX_GMP`
- `DCForm.frm :: VietGop_PVCN_GMP` (inactive at active compile call site)
- `clsNode.cls :: Checked / CheckTriStateParent / CheckTriStateChildren`
- `MainForm.frm :: call to DCForm.Edit_DC and persistence of DCForm.DaychuyenSum`
- `RecordForm.frm :: Input_DC_to_CC / Get_DC_Name_Desc usage`
- `backend/app/db/models/phase1.py :: EvaluationScopeTaxonomy* / CaseEvaluationScope*`
- `artifacts/legacy_snapshot/evaluation_scope_taxonomy.json :: taxonomy_availability`

## 18. Open questions intentionally deferred

The following are intentionally **not** filled from inference:

1. whether any other active caller enables `VietGop_PVCN_GMP` in a production path;
2. whether unkeyed rows should appear in the new application's compact summary despite VBA core compilation skipping them;
3. exact semantic-key mapping for every GMP positional row constant across taxonomy versions;
4. GDP compilation behavior until a real `PVCN_GDP` taxonomy source is supplied;
5. document-specific mappings (`Daychuyen`, `GhPviDG`, `GhPviCN`, `GioiHanPvi`) until the C.5e VBA/document-builder audit is performed.

These items must remain explicit gates, not be resolved by convenience or by current Python output.
