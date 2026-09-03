from __future__ import annotations

"""Shadow port of the legacy VBA evaluation-scope summary compiler.

This module intentionally does not replace ``render_evaluation_scope_summary``.
The business semantics here are ported from ``DCForm.frm``:
``Compile_Node`` -> ``Compile_Node_Full`` -> ``Compile_PVCN``.

GMP-specific post-processing (``VietChitiet_PVDG_GMP`` and
``VietChitiet_PVXX_GMP``) is deliberately deferred until its row-anchor
semantics have been ported and proven separately.
"""

from dataclasses import dataclass, replace
from typing import Any, Iterable, Sequence

from backend.app.domain.evaluation_scope import (
    EvaluationScopeRenderSpan,
    finalize_evaluation_scope_spans,
)


VBA_CR = "\r"


@dataclass(frozen=True)
class VbaNodeCompileResult:
    text: str
    spans: tuple[EvaluationScopeRenderSpan, ...]
    continuation_marker: bool
    opens_group: bool


@dataclass(frozen=True)
class VbaScopeCompileResult:
    text: str
    spans: tuple[EvaluationScopeRenderSpan, ...]
    contributions: tuple[dict[str, Any], ...]
    deferred_rules: tuple[str, ...]


@dataclass(frozen=True)
class _OwnedChar:
    char: str
    kind: str
    owner_type: str
    contribution_id: str
    metadata: dict[str, Any] | None = None


def _chars(
    text: str,
    *,
    kind: str,
    owner_type: str,
    contribution_id: str,
    metadata: dict[str, Any] | None = None,
) -> list[_OwnedChar]:
    return [
        _OwnedChar(ch, kind, owner_type, contribution_id, dict(metadata) if metadata else None)
        for ch in text
    ]


def _find_text(items: Sequence[_OwnedChar], needle: str, start: int = 0) -> int:
    if not needle:
        return -1
    haystack = "".join(item.char for item in items)
    return haystack.find(needle, start)


def _delete_first(items: list[_OwnedChar], needle: str) -> None:
    index = _find_text(items, needle)
    if index >= 0:
        del items[index : index + len(needle)]


def _replace_first_with_chars(
    items: list[_OwnedChar],
    needle: str,
    replacement: list[_OwnedChar],
) -> bool:
    index = _find_text(items, needle)
    if index < 0:
        return False
    items[index : index + len(needle)] = replacement
    return True


def _replace_all_renderer_owned(
    items: list[_OwnedChar],
    old: str,
    new: str,
    *,
    contribution_id: str,
    transformation_kind: str,
) -> None:
    """Port VBA ``Replace`` while retaining the transformed origin in metadata."""
    if not old:
        return
    start = 0
    while True:
        index = _find_text(items, old, start)
        if index < 0:
            return
        origin = items[index : index + len(old)]
        metadata = {
            "transformation_kind": transformation_kind,
            "origin_kinds": sorted({item.kind for item in origin}),
            "origin_owner_types": sorted({item.owner_type for item in origin}),
            "origin_text": old,
        }
        replacement = _chars(
            new,
            kind="VBA_COMPILER_TRANSFORM",
            owner_type="renderer",
            contribution_id=contribution_id,
            metadata=metadata,
        )
        items[index : index + len(old)] = replacement
        start = index + len(replacement)


def _trim_vba(items: list[_OwnedChar]) -> list[_OwnedChar]:
    """Approximate VBA ``Trim`` for the whitespace emitted by this compiler."""
    start = 0
    end = len(items)
    while start < end and items[start].char == " ":
        start += 1
    while end > start and items[end - 1].char == " ":
        end -= 1
    return items[start:end]


def _clean_text_chars(items: list[_OwnedChar], *, ext: bool = False) -> list[_OwnedChar]:
    """Direct port of ``DCForm.CleanText`` on an owned character stream."""
    result = list(items)
    _delete_first(result, " ($$)")
    _delete_first(result, "($$)")
    _delete_first(result, " $$")
    _delete_first(result, "$$")
    if ext:
        _delete_first(result, ": ")
    return result


def _clean_text_string(text: str, *, ext: bool = False) -> str:
    items = _chars(
        text,
        kind="SOURCE_TAXONOMY",
        owner_type="source",
        contribution_id="clean-text-probe",
    )
    return "".join(item.char for item in _clean_text_chars(items, ext=ext))


def _coalesce_spans(items: Sequence[_OwnedChar]) -> tuple[EvaluationScopeRenderSpan, ...]:
    spans: list[EvaluationScopeRenderSpan] = []
    for item in items:
        if not item.char:
            continue
        if spans and (
            spans[-1].kind == item.kind
            and spans[-1].owner_type == item.owner_type
            and spans[-1].contribution_id == item.contribution_id
            and spans[-1].metadata == item.metadata
        ):
            spans[-1] = replace(spans[-1], text=spans[-1].text + item.char)
        else:
            spans.append(
                EvaluationScopeRenderSpan(
                    kind=item.kind,
                    text=item.char,
                    owner_type=item.owner_type,
                    contribution_id=item.contribution_id,
                    metadata=item.metadata,
                )
            )
    if not spans:
        return ()
    _, finalized = finalize_evaluation_scope_spans(spans)
    return finalized


def _result_from_chars(items: Sequence[_OwnedChar]) -> tuple[str, tuple[EvaluationScopeRenderSpan, ...]]:
    if not items:
        return "", ()
    spans = _coalesce_spans(items)
    text = "".join(span.text for span in spans)
    return text, spans


def compile_vba_node(
    *,
    short_render: str | None,
    custom_description: str | None,
    contribution_id: str,
) -> VbaNodeCompileResult:
    """Port ``DCForm.Compile_Node`` without the mutable VBA position side effects."""
    source = short_render or ""
    custom = custom_description or ""
    if source == "":
        return VbaNodeCompileResult("", (), False, False)

    original_has_template = "$$" in source
    work = source
    chars: list[_OwnedChar] = []
    continuation = work.startswith("<")
    if continuation:
        chars.extend(
            _chars(
                "<",
                kind="SOURCE_CONTROL_CONTINUATION",
                owner_type="source",
                contribution_id=contribution_id,
                metadata={"source_field": "short_render", "vba_marker": "<"},
            )
        )
        work = work[1:]

    # VBA: taxonomy text is suppressed by '&' when custom description is nonblank.
    if not work.startswith("&") or custom == "":
        if work.startswith("&"):
            work = work[1:]
        chars.extend(
            _chars(
                work,
                kind="SOURCE_TAXONOMY",
                owner_type="source",
                contribution_id=contribution_id,
                metadata={"source_field": "short_render"},
            )
        )

    if custom != "":
        if original_has_template:
            replacement = _chars(
                custom,
                kind="SOURCE_CUSTOM_DESCRIPTION",
                owner_type="source",
                contribution_id=contribution_id,
                metadata={"source_field": "custom_description", "vba_operation": "template_substitution"},
            )
            # This intentionally replaces only a visible template slot.  When '&'
            # suppressed the source template, VBA Replace also finds no '$$'.
            _replace_first_with_chars(chars, "$$", replacement)
        else:
            chars.extend(
                _chars(
                    ": ",
                    kind="VBA_RENDERER_SEPARATOR",
                    owner_type="renderer",
                    contribution_id=contribution_id,
                    metadata={"vba_operation": "append_custom_description"},
                )
            )
            chars.extend(
                _chars(
                    custom,
                    kind="SOURCE_CUSTOM_DESCRIPTION",
                    owner_type="source",
                    contribution_id=contribution_id,
                    metadata={"source_field": "custom_description", "vba_operation": "append"},
                )
            )

    chars = _clean_text_chars(chars)
    current_text = "".join(item.char for item in chars)
    if not current_text.endswith("("):
        chars.extend(
            _chars(
                "; ",
                kind="VBA_RENDERER_TERMINATOR",
                owner_type="renderer",
                contribution_id=contribution_id,
                metadata={"vba_operation": "Compile_Node terminator"},
            )
        )

    for old, new in (
        ("; ;", ";"),
        (";;", ";"),
        ("::", ":"),
        (": ;", ":"),
        ("; )", ")"),
        (";)", ")"),
    ):
        _replace_all_renderer_owned(
            chars,
            old,
            new,
            contribution_id=contribution_id,
            transformation_kind=f"Compile_Node Replace {old!r}->{new!r}",
        )

    text, spans = _result_from_chars(chars)
    return VbaNodeCompileResult(
        text=text,
        spans=spans,
        continuation_marker=text.startswith("<"),
        opens_group=text.endswith("("),
    )


def _clean_taxonomy_short_render(
    short_render: str | None,
    *,
    contribution_id: str,
) -> list[_OwnedChar]:
    chars = _chars(
        short_render or "",
        kind="SOURCE_TAXONOMY",
        owner_type="source",
        contribution_id=contribution_id,
        metadata={"source_field": "short_render", "vba_operation": "CleanText ancestor"},
    )
    return _clean_text_chars(chars)


def _parent_key(node_key: str) -> str:
    head, separator, _ = node_key.rpartition(".")
    return head if separator else ""


def _ancestor_keys(node_key: str) -> list[str]:
    parts = node_key.split(".")
    return [".".join(parts[:index]) for index in range(1, len(parts))]


@dataclass
class _CompileState:
    emitted_keys: set[str]
    last_parent_key: str = "xxx"
    group_parent_mode: bool = False
    group_parent_node_key: str = ""


def _check_close_parent_mode(
    state: _CompileState,
    node_key: str,
    *,
    contribution_id: str,
) -> list[_OwnedChar]:
    if not state.group_parent_mode:
        return []
    if not node_key.startswith(state.group_parent_node_key):
        state.group_parent_mode = False
        return _chars(
            "<)\r",
            kind="VBA_GROUP_CLOSE_CONTROL",
            owner_type="renderer",
            contribution_id=contribution_id,
            metadata={"vba_operation": "Check_Close_ParentMode"},
        )
    return []


def _check_open_parent_mode(state: _CompileState, node_key: str, rendered_text: str) -> None:
    if rendered_text.strip().endswith("("):
        state.group_parent_mode = True
        state.group_parent_node_key = node_key


def _append_cr(chars: list[_OwnedChar], contribution_id: str, operation: str) -> None:
    chars.extend(
        _chars(
            VBA_CR,
            kind="VBA_RENDERER_LINE_BREAK",
            owner_type="renderer",
            contribution_id=contribution_id,
            metadata={"vba_operation": operation},
        )
    )


def _compile_node_full_chars(
    *,
    selected: dict[str, Any],
    node_by_key: dict[str, dict[str, Any]],
    state: _CompileState,
    block_ordinal: int,
) -> tuple[list[_OwnedChar], list[dict[str, Any]]]:
    node_key = str(selected["key"])
    parent_key = _parent_key(node_key)
    chars: list[_OwnedChar] = []
    contributions: list[dict[str, Any]] = []

    if parent_key != state.last_parent_key:
        state.last_parent_key = parent_key
        for ancestor_key in _ancestor_keys(node_key):
            ancestor = node_by_key.get(ancestor_key)
            if ancestor is None:
                raise ValueError(f"Missing VBA taxonomy ancestor {ancestor_key!r} for selected node {node_key!r}.")
            if ancestor_key in state.emitted_keys:
                continue
            state.emitted_keys.add(ancestor_key)
            contribution_id = f"ancestor:{block_ordinal}:{ancestor_key}"
            ancestor_chars = _clean_taxonomy_short_render(
                ancestor.get("short_render"), contribution_id=contribution_id
            )
            ancestor_text = "".join(item.char for item in ancestor_chars)
            if not ancestor_text.strip(" "):
                contributions.append(
                    {"contribution_id": contribution_id, "role": "required_ancestor", "node_key": ancestor_key, "visible": False}
                )
                continue
            chars.extend(
                _check_close_parent_mode(
                    state, ancestor_key, contribution_id=f"group-close:{block_ordinal}:{ancestor_key}"
                )
            )
            if not state.group_parent_mode:
                _check_open_parent_mode(state, ancestor_key, ancestor_text)
            chars.extend(ancestor_chars)
            _append_cr(chars, contribution_id, "Compile_Node_Full ancestor line")
            contributions.append(
                {"contribution_id": contribution_id, "role": "required_ancestor", "node_key": ancestor_key, "visible": True}
            )

    selected_node = node_by_key.get(node_key)
    if selected_node is None:
        raise ValueError(f"Selected node {node_key!r} is not present in the VBA taxonomy.")
    state.emitted_keys.add(node_key)
    contribution_id = f"selected:{block_ordinal}:{node_key}:{selected.get('source_order', '')}"
    node_result = compile_vba_node(
        short_render=selected_node.get("short_render"),
        custom_description=str(selected.get("custom_description") or ""),
        contribution_id=contribution_id,
    )
    chars.extend(
        _check_close_parent_mode(
            state, node_key, contribution_id=f"group-close:{block_ordinal}:{node_key}"
        )
    )
    if not state.group_parent_mode:
        _check_open_parent_mode(state, node_key, node_result.text)
    # Convert finalized node spans back to chars without reverse source inference:
    # every character inherits the span owner that was emitted during Compile_Node.
    for span in node_result.spans:
        chars.extend(
            _chars(
                span.text,
                kind=span.kind,
                owner_type=span.owner_type,
                contribution_id=span.contribution_id,
                metadata=span.metadata,
            )
        )
    contributions.append(
        {
            "contribution_id": contribution_id,
            "role": "selected_node",
            "node_key": node_key,
            "visible": bool(node_result.text),
            "custom_description": str(selected.get("custom_description") or ""),
        }
    )
    return chars, contributions


def _trim_trailing_cr_vba(chars: list[_OwnedChar]) -> list[_OwnedChar]:
    result = list(chars)
    while result and result[-1].char == VBA_CR:
        result = _trim_vba(result[:-1])
    return result



_GMP_ROW_ASEPTIC = 2
_GMP_ROW_PRI_PACK = 93
_GMP_ROW_SEC_PACK = 96
_GMP_ROW_XX_VT = 15
_GMP_ROW_XX_KVT = 49
_GMP_ROW_XX_SH = 60
_GMP_ROW_XX_DL = 78


def _taxonomy_by_source_order(nodes: Sequence[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(node.get("source_order") or 0): node for node in nodes if int(node.get("source_order") or 0) > 0}


def _vba_find_ci(text: str, needle: str, start: int = 0) -> int:
    if not needle:
        return -1
    return text.casefold().find(needle.casefold(), start)


def _vba_get_in_line_pos(text: str, needle: str) -> tuple[int, int, int]:
    """Return zero-based ``(start, end_inclusive, line_end)`` for GetInLinePos.

    ``line_end`` is the index of the following VBA CR, or ``len(text)`` when
    there is no following CR.  Only the fields used by the two active GMP
    detail procedures are exposed.
    """
    start = _vba_find_ci(text, needle)
    if start < 0:
        return -1, -1, -1
    end = start + len(needle) - 1
    line_end = text.find(VBA_CR, start + 1)
    if line_end < 0:
        line_end = len(text)
    return start, end, line_end


def _vba_pv_incl_pos(pvi: str, key: str) -> int:
    """Zero-based port of ``PV_Incl_Pos``; ``-1`` means VBA returned 0."""
    if not pvi or not key:
        return -1
    first = key[:1]
    for needle in (
        f" {first} ",
        f" {key} ",
        f" {key})",
        f" {first}. ",
        f" {key}. ",
    ):
        pos = _vba_find_ci(pvi, needle)
        if pos >= 0:
            return pos
    return -1


def _replace_owned_range_with_taxonomy_description(
    chars: list[_OwnedChar],
    *,
    start: int,
    length: int,
    description: str,
    contribution_id: str,
    node_key: str,
    procedure: str,
) -> int:
    if start < 0 or length < 0 or start + length > len(chars):
        return 0
    replacement = _chars(
        description,
        kind="SOURCE_TAXONOMY_DESCRIPTION",
        owner_type="source",
        contribution_id=contribution_id,
        metadata={
            "source_field": "description",
            "node_key": node_key,
            "vba_operation": procedure,
        },
    )
    chars[start : start + length] = replacement
    return len(description) - length


def _gmp_extract_line_payload(text: str, anchor: str) -> tuple[str, int] | None:
    start, end, line_end = _vba_get_in_line_pos(text, anchor)
    if start < 0 or line_end < 0:
        return None
    payload = text[end + 1 : line_end]
    pvi = " " + payload.replace(",", " ").replace(";", " ") + " "
    return pvi, end + 1


def _apply_vietchitiet_pvdg_gmp(
    chars: list[_OwnedChar],
    *,
    taxonomy_nodes: Sequence[dict[str, Any]],
    block_ordinal: int,
    contributions: list[dict[str, Any]],
) -> list[_OwnedChar]:
    """Port active ``VietChitiet_PVDG_GMP`` from ``DCForm.frm``.

    The procedure expands compact node keys that appear in the primary and
    secondary packaging lines into the taxonomy's full descriptions.
    """
    rows = _taxonomy_by_source_order(taxonomy_nodes)
    pri_anchor_row = rows.get(_GMP_ROW_PRI_PACK - 1)
    sec_anchor_row = rows.get(_GMP_ROW_SEC_PACK - 1)
    if pri_anchor_row is None or sec_anchor_row is None:
        raise ValueError("Missing GMP packaging anchor rows required by VBA detail expansion.")

    result = list(chars)
    working_pvi: dict[str, str] = {}
    for label, row, ext in (
        ("primary", pri_anchor_row, True),
        ("secondary", sec_anchor_row, True),
    ):
        anchor = _clean_text_string(str(row.get("short_render") or ""), ext=ext)
        extracted = _gmp_extract_line_payload("".join(item.char for item in result), anchor)
        if extracted is not None:
            working_pvi[label] = extracted[0]

    for source_order in range(_GMP_ROW_ASEPTIC - 1, _GMP_ROW_PRI_PACK):
        row = rows.get(source_order)
        if row is None:
            continue
        key = str(row.get("key") or "")
        description = str(row.get("description") or "")
        if not key:
            continue
        for label, anchor_row in (("primary", pri_anchor_row), ("secondary", sec_anchor_row)):
            pvi = working_pvi.get(label)
            if pvi is None:
                continue
            j = _vba_pv_incl_pos(pvi, key)
            if j < 0:
                continue
            anchor = _clean_text_string(str(anchor_row.get("short_render") or ""), ext=True)
            current_text = "".join(item.char for item in result)
            _st, ed, _line_end = _vba_get_in_line_pos(current_text, anchor)
            if ed < 0:
                continue
            # VBA: ReplaceMidStrS(rs, ed + j - 1, ..., desc).  ReplaceMidStrS
            # keeps Left$(s, DStart), so the Python replacement starts at the
            # zero-based offset ``(ed + 1) + j``.
            replace_start = (ed + 1) + j
            contribution_id = f"gmp-pvdg:{block_ordinal}:{label}:{key}"
            delta = _replace_owned_range_with_taxonomy_description(
                result,
                start=replace_start,
                length=len(key),
                description=description,
                contribution_id=contribution_id,
                node_key=key,
                procedure="VietChitiet_PVDG_GMP",
            )
            pvi_start = j + 1
            # Same ReplaceMidStrS semantics on the local Pvi string.
            working_pvi[label] = pvi[:pvi_start] + description + pvi[pvi_start + len(key) :]
            contributions.append(
                {
                    "contribution_id": contribution_id,
                    "role": "gmp_packaging_detail_expansion",
                    "node_key": key,
                    "packaging": label,
                    "visible": True,
                    "length_delta": delta,
                }
            )
    return result


def _apply_vietchitiet_pvxx_gmp(
    chars: list[_OwnedChar],
    *,
    taxonomy_nodes: Sequence[dict[str, Any]],
    block_ordinal: int,
    contributions: list[dict[str, Any]],
) -> list[_OwnedChar]:
    """Port active ``VietChitiet_PVXX_GMP`` from ``DCForm.frm``."""
    rows = _taxonomy_by_source_order(taxonomy_nodes)
    anchors = (
        ("sterile", _GMP_ROW_XX_VT),
        ("nonsterile", _GMP_ROW_XX_KVT),
        ("biologic", _GMP_ROW_XX_SH),
        ("herbal", _GMP_ROW_XX_DL),
    )
    for _label, source_order in anchors:
        if rows.get(source_order) is None:
            raise ValueError(f"Missing GMP batch-release anchor row {source_order} required by VBA detail expansion.")

    result = list(chars)
    working_pvi: dict[str, str] = {}
    for label, source_order in anchors:
        row = rows[source_order]
        locate_anchor = _clean_text_string(str(row.get("short_render") or "")).replace("()", "")
        extracted = _gmp_extract_line_payload("".join(item.char for item in result), locate_anchor)
        if extracted is not None:
            working_pvi[label] = extracted[0]

    for source_order in range(_GMP_ROW_ASEPTIC - 1, _GMP_ROW_PRI_PACK):
        row = rows.get(source_order)
        if row is None:
            continue
        key = str(row.get("key") or "")
        description = str(row.get("description") or "")
        if not key:
            continue
        for label, anchor_order in anchors:
            pvi = working_pvi.get(label)
            if pvi is None:
                continue
            j = _vba_pv_incl_pos(pvi, key)
            if j < 0:
                continue
            # VBA intentionally re-locates the replacement line by the full
            # taxonomy description, not by short_render.  Preserve that quirk.
            anchor_description = str(rows[anchor_order].get("description") or "")
            current_text = "".join(item.char for item in result)
            _st, ed, _line_end = _vba_get_in_line_pos(current_text, anchor_description)
            if ed < 0:
                continue
            replace_start = (ed + 1) + j
            contribution_id = f"gmp-pvxx:{block_ordinal}:{label}:{key}"
            delta = _replace_owned_range_with_taxonomy_description(
                result,
                start=replace_start,
                length=len(key),
                description=description,
                contribution_id=contribution_id,
                node_key=key,
                procedure="VietChitiet_PVXX_GMP",
            )
            pvi_start = j + 1
            working_pvi[label] = pvi[:pvi_start] + description + pvi[pvi_start + len(key) :]
            contributions.append(
                {
                    "contribution_id": contribution_id,
                    "role": "gmp_batch_release_detail_expansion",
                    "node_key": key,
                    "release_family": label,
                    "visible": True,
                    "length_delta": delta,
                }
            )
    return result


def compile_vba_scope_core(
    *,
    selections: Iterable[dict[str, Any]],
    taxonomy_nodes: Iterable[dict[str, Any]],
    block_ordinal: int = 1,
    gxp_type: str | None = None,
) -> VbaScopeCompileResult:
    """Port the core of ``Compile_PVCN`` before GMP detail post-processing.

    ``selections`` must carry ``key``, ``source_order`` and optional
    ``custom_description``.  Input order is reconstructed from ``source_order``
    because VBA ``LoadNodeList`` preserves persisted structured order.
    """
    nodes = tuple(taxonomy_nodes)
    node_by_key = {str(node["key"]): node for node in nodes}
    ordered = sorted(
        (dict(selection) for selection in selections),
        key=lambda item: (int(item.get("source_order") or 0), str(item.get("key") or "")),
    )
    state = _CompileState(emitted_keys=set())
    chars: list[_OwnedChar] = []
    contributions: list[dict[str, Any]] = []

    for selected in ordered:
        if not str(selected.get("key") or ""):
            # Mirrors Compile_PVCN: blank-key/unkeyed rows are retained by
            # LoadNodeList but not sent through Compile_Node_Full.
            continue
        node_chars, node_contributions = _compile_node_full_chars(
            selected=selected,
            node_by_key=node_by_key,
            state=state,
            block_ordinal=block_ordinal,
        )
        chars.extend(node_chars)
        _append_cr(chars, f"loop-break:{block_ordinal}:{selected['key']}", "Compile_PVCN loop")
        contributions.extend(node_contributions)

    _replace_all_renderer_owned(
        chars,
        "\r<",
        "",
        contribution_id=f"compile-pvcn:{block_ordinal}:continuation",
        transformation_kind="Compile_PVCN remove vbCr + '<' continuation marker",
    )
    chars = _trim_trailing_cr_vba(chars)

    if state.group_parent_mode:
        chars.extend(
            _chars(
                ").",
                kind="VBA_GROUP_FINAL_CLOSE",
                owner_type="renderer",
                contribution_id=f"compile-pvcn:{block_ordinal}:final-group-close",
                metadata={"vba_operation": "Compile_PVCN final group close"},
            )
        )
        state.group_parent_mode = False

    _append_cr(chars, f"compile-pvcn:{block_ordinal}:final-break", "Compile_PVCN final temporary CR")

    for old, new in (
        ("; )", "); "),
        (";)", ") "),
        (".)", ") "),
        (";\r", ".\r"),
        ("; \r", ". \r"),
        (") .", ")."),
    ):
        _replace_all_renderer_owned(
            chars,
            old,
            new,
            contribution_id=f"compile-pvcn:{block_ordinal}:cleanup",
            transformation_kind=f"Compile_PVCN Replace {old!r}->{new!r}",
        )

    chars = _trim_trailing_cr_vba(chars)
    deferred: tuple[str, ...] = ()
    if (gxp_type or "").upper() == "GMP":
        chars = _apply_vietchitiet_pvdg_gmp(
            chars,
            taxonomy_nodes=nodes,
            block_ordinal=block_ordinal,
            contributions=contributions,
        )
        chars = _apply_vietchitiet_pvxx_gmp(
            chars,
            taxonomy_nodes=nodes,
            block_ordinal=block_ordinal,
            contributions=contributions,
        )
    text, spans = _result_from_chars(chars)
    return VbaScopeCompileResult(
        text=text,
        spans=spans,
        contributions=tuple(contributions),
        deferred_rules=deferred,
    )


@dataclass(frozen=True)
class VbaBlockCompileResult:
    """Source-faithful projection of ``DCForm.Get_DC_Name_Desc`` for one block."""

    text: str
    spans: tuple[EvaluationScopeRenderSpan, ...]
    contributions: tuple[dict[str, Any], ...]
    core: VbaScopeCompileResult


@dataclass(frozen=True)
class VbaReadableScopeResult:
    """Human-readable multi-block projection plus the optional VBA limitation line."""

    text: str
    spans: tuple[EvaluationScopeRenderSpan, ...]
    blocks: tuple[VbaBlockCompileResult, ...]
    contributions: tuple[dict[str, Any], ...]
    deferred_rules: tuple[str, ...]


@dataclass(frozen=True)
class VbaNewFormatEnvelopeResult:
    """Exact outer ``GetData`` new-format envelope when raw block payloads are supplied."""

    text: str
    readable: VbaReadableScopeResult
    structured_payload: str


def _extend_span_chars(target: list[_OwnedChar], spans: Sequence[EvaluationScopeRenderSpan]) -> None:
    """Append already-owned span text without re-inferring source ownership."""
    for span in spans:
        target.extend(
            _chars(
                span.text,
                kind=span.kind,
                owner_type=span.owner_type,
                contribution_id=span.contribution_id,
                metadata=span.metadata,
            )
        )


def compile_vba_block(
    *,
    ordinal: int,
    name: str | None,
    note: str | None,
    selections: Iterable[dict[str, Any]],
    taxonomy_nodes: Iterable[dict[str, Any]],
    gxp_type: str | None = None,
) -> VbaBlockCompileResult:
    """Port the human-readable part of ``DCForm.Get_DC_Name_Desc``.

    Canonical persistence has already parsed the ``¶`` and ``¿`` delimiters, so
    this function accepts ``name`` and ``note`` directly.  The emitted text is
    nevertheless the VBA text, including its unusual leading space when a note
    exists without a block name.
    """
    block_ordinal = int(ordinal)
    core = compile_vba_scope_core(
        selections=selections,
        taxonomy_nodes=taxonomy_nodes,
        block_ordinal=block_ordinal,
        gxp_type=gxp_type,
    )
    chars: list[_OwnedChar] = []
    contributions: list[dict[str, Any]] = list(core.contributions)
    block_name = "" if name is None else str(name)
    block_note = "" if note is None else str(note)

    header_present = False
    if block_name != "":
        contribution_id = f"block-name:{block_ordinal}"
        chars.extend(
            _chars(
                "« ",
                kind="VBA_BLOCK_HEADER_DECORATION",
                owner_type="renderer",
                contribution_id=contribution_id,
                metadata={"vba_operation": "Get_DC_Name_Desc name prefix"},
            )
        )
        chars.extend(
            _chars(
                block_name,
                kind="SOURCE_BLOCK_NAME",
                owner_type="source",
                contribution_id=contribution_id,
                metadata={"source_field": "block.name", "vba_delimiter": "¶"},
            )
        )
        chars.extend(
            _chars(
                " »",
                kind="VBA_BLOCK_HEADER_DECORATION",
                owner_type="renderer",
                contribution_id=contribution_id,
                metadata={"vba_operation": "Get_DC_Name_Desc name suffix"},
            )
        )
        contributions.append(
            {"contribution_id": contribution_id, "role": "block_name", "block_ordinal": block_ordinal, "visible": True}
        )
        header_present = True

    if block_note != "":
        contribution_id = f"block-note:{block_ordinal}"
        # VBA always prefixes the note with one literal space, even when there
        # is no block name: IIf(note <> "", " (" & note & ")", "").
        chars.extend(
            _chars(
                " (",
                kind="VBA_BLOCK_NOTE_DECORATION",
                owner_type="renderer",
                contribution_id=contribution_id,
                metadata={"vba_operation": "Get_DC_Name_Desc note prefix"},
            )
        )
        chars.extend(
            _chars(
                block_note,
                kind="SOURCE_BLOCK_NOTE",
                owner_type="source",
                contribution_id=contribution_id,
                metadata={"source_field": "block.note", "vba_delimiter": "¿"},
            )
        )
        chars.extend(
            _chars(
                ")",
                kind="VBA_BLOCK_NOTE_DECORATION",
                owner_type="renderer",
                contribution_id=contribution_id,
                metadata={"vba_operation": "Get_DC_Name_Desc note suffix"},
            )
        )
        contributions.append(
            {"contribution_id": contribution_id, "role": "block_note", "block_ordinal": block_ordinal, "visible": True}
        )
        header_present = True

    if header_present:
        chars.extend(
            _chars(
                "\r\n",
                kind="VBA_RENDERER_LINE_BREAK",
                owner_type="renderer",
                contribution_id=f"block-header-break:{block_ordinal}",
                metadata={"vba_operation": "Get_DC_Name_Desc header vbCrLf"},
            )
        )
    _extend_span_chars(chars, core.spans)
    text, spans = _result_from_chars(chars)
    return VbaBlockCompileResult(
        text=text,
        spans=spans,
        contributions=tuple(contributions),
        core=core,
    )


def compile_vba_readable_scope(
    *,
    blocks: Iterable[dict[str, Any]],
    taxonomy_nodes: Iterable[dict[str, Any]],
    limitation_text: str | None = None,
    gxp_type: str | None = None,
) -> VbaReadableScopeResult:
    """Port ``SplitDC``/``Get_DC_Name_Desc`` + readable ``GetData`` composition.

    The block order is the persisted ``ordinal`` order.  Exactly one ``vbCrLf``
    is inserted between compiled blocks, matching ``Join(iDC_Comp, vbCrLf)``.
    A nonblank limitation is then appended as ``vbCrLf & \"(*...*)\"``.

    This function intentionally stops before the ``{...}*`` structured suffix;
    use :func:`compile_vba_new_format_envelope` only when the original per-block
    serialized values are available.
    """
    taxonomy = tuple(dict(node) for node in taxonomy_nodes)
    ordered_blocks = sorted(
        (dict(block) for block in blocks),
        key=lambda row: (int(row.get("ordinal") or 0), str(row.get("id") or "")),
    )
    compiled_blocks: list[VbaBlockCompileResult] = []
    chars: list[_OwnedChar] = []
    contributions: list[dict[str, Any]] = []
    deferred: list[str] = []

    for index, block in enumerate(ordered_blocks):
        ordinal = int(block.get("ordinal") or index + 1)
        compiled = compile_vba_block(
            ordinal=ordinal,
            name=block.get("name"),
            note=block.get("note"),
            selections=block.get("selections") or (),
            taxonomy_nodes=taxonomy,
            gxp_type=gxp_type,
        )
        if index:
            chars.extend(
                _chars(
                    "\r\n",
                    kind="VBA_RENDERER_BLOCK_SEPARATOR",
                    owner_type="renderer",
                    contribution_id=f"block-separator:{ordinal}",
                    metadata={"vba_operation": "GetData Join(iDC_Comp, vbCrLf)"},
                )
            )
        _extend_span_chars(chars, compiled.spans)
        compiled_blocks.append(compiled)
        contributions.extend(compiled.contributions)
        for rule in compiled.core.deferred_rules:
            if rule not in deferred:
                deferred.append(rule)

    raw_limitation = "" if limitation_text is None else str(limitation_text)
    if raw_limitation.strip() != "":
        if chars:
            chars.extend(
                _chars(
                    "\r\n",
                    kind="VBA_RENDERER_LINE_BREAK",
                    owner_type="renderer",
                    contribution_id="limitation:break",
                    metadata={"vba_operation": "GetData limitation vbCrLf"},
                )
            )
        contribution_id = "limitation"
        chars.extend(
            _chars(
                "(*",
                kind="VBA_LIMITATION_DECORATION",
                owner_type="renderer",
                contribution_id=contribution_id,
                metadata={"vba_operation": "GetData limitation prefix"},
            )
        )
        chars.extend(
            _chars(
                raw_limitation,
                kind="SOURCE_LIMITATION",
                owner_type="source",
                contribution_id=contribution_id,
                metadata={"source_field": "limitation_text"},
            )
        )
        chars.extend(
            _chars(
                "*)",
                kind="VBA_LIMITATION_DECORATION",
                owner_type="renderer",
                contribution_id=contribution_id,
                metadata={"vba_operation": "GetData limitation suffix"},
            )
        )
        contributions.append({"contribution_id": contribution_id, "role": "limitation", "visible": True})

    text, spans = _result_from_chars(chars)
    return VbaReadableScopeResult(
        text=text,
        spans=spans,
        blocks=tuple(compiled_blocks),
        contributions=tuple(contributions),
        deferred_rules=tuple(deferred),
    )


def _vba_getdata_normalize(value: str) -> str:
    """Port the three case-insensitive normalization calls at the end of GetData."""
    import re

    # VBA Trim removes leading/trailing ASCII spaces, not internal CR/LF.
    result = value.strip(" ")
    result = re.sub("beta", "β", result, flags=re.IGNORECASE)
    result = re.sub("lactam", "Lactam", result, flags=re.IGNORECASE)
    result = re.sub(" Lactam", "-Lactam", result, flags=re.IGNORECASE)
    return result


def compile_vba_new_format_envelope(
    *,
    blocks: Iterable[dict[str, Any]],
    taxonomy_nodes: Iterable[dict[str, Any]],
    limitation_text: str | None = None,
    gxp_type: str | None = None,
) -> VbaNewFormatEnvelopeResult:
    """Port the ``New_Form`` branch of ``DCForm.GetData`` including ``{...}*``.

    This helper deliberately fails closed unless every block supplies
    ``raw_block_value``.  Reconstructing the serialized node payload from
    selections would create a second persistence serializer and could alter
    source ordering or delimiter details.  Canonical persistence already keeps
    this exact legacy block value, so the faithful path is to reuse it.
    """
    materialized = tuple(dict(block) for block in blocks)
    missing = [int(block.get("ordinal") or index + 1) for index, block in enumerate(materialized) if block.get("raw_block_value") is None]
    if missing:
        raise ValueError(
            "VBA new-format envelope requires original raw_block_value for every block; "
            f"missing ordinals: {missing}."
        )

    readable = compile_vba_readable_scope(
        blocks=materialized,
        taxonomy_nodes=taxonomy_nodes,
        limitation_text=limitation_text,
        gxp_type=gxp_type,
    )
    structured_payload = "§".join(str(block.get("raw_block_value") or "") for block in sorted(materialized, key=lambda row: (int(row.get("ordinal") or 0), str(row.get("id") or ""))))

    # GetData first builds Join(iDC_Comp), conditionally appends limitation, then
    # always inserts vbCrLf before the structured suffix.  readable.text already
    # contains the first two pieces exactly.
    envelope = readable.text + "\r\n{" + structured_payload + "}*"
    envelope = _vba_getdata_normalize(envelope)
    return VbaNewFormatEnvelopeResult(
        text=envelope,
        readable=readable,
        structured_payload=structured_payload,
    )
