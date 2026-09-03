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
    text, spans = _result_from_chars(chars)
    deferred: tuple[str, ...] = ()
    if (gxp_type or "").upper() == "GMP":
        deferred = ("VietChitiet_PVDG_GMP", "VietChitiet_PVXX_GMP")
    return VbaScopeCompileResult(
        text=text,
        spans=spans,
        contributions=tuple(contributions),
        deferred_rules=deferred,
    )
