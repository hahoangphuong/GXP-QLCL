"""Read-only parity for QĐKT ``CreateFile(i=2)`` bookmark targeting.

The legacy ``Replace_Bookmark`` helper constructs every requested numbered
name and relies on ``On Error Resume Next`` when a bookmark is absent.  This
module only resolves names already present in an observed template.  It does
not write Word files, create missing bookmarks, resolve business owners, or
authorize QĐKT rendering.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


SUPPORTED_GXP_TYPES = frozenset({"GLP", "GMP", "GMPbb", "GSP"})


class QdKtVbaBookmarkContractError(ValueError):
    """The caller requested behavior outside the source-proven VBA contract."""


@dataclass(frozen=True)
class QdKtI2BookmarkOperation:
    """One source-proven i=2 operation reconciled with physical bookmarks."""

    logical_name: str
    operation_type: str
    candidate_targets: tuple[str, ...]
    effective_targets: tuple[str, ...]
    branch_reachable: bool
    branch_condition: str
    source_expression: str
    source_line: int


@dataclass(frozen=True)
class _OperationRule:
    operation_type: str
    first_index: int | None
    last_index: int | None
    explicit_targets: tuple[str, ...]
    applicable_gxp: frozenset[str]
    branch_condition: str
    source_expression: str
    source_line: int


_ALL_GXP = SUPPORTED_GXP_TYPES
_GMP_GLP = frozenset({"GMP", "GLP"})

# Direct source: legacy/GXP-VBA code.zip!RecordForm.frm, lines 744, 751-752,
# 754-766.  The TT targets are a separate dynamic-name loop, not an invocation
# of the numbered Replace_Bookmark bounds.
_I2_RULES: dict[str, _OperationRule] = {
    "Tencoso": _OperationRule(
        operation_type="WRITE",
        first_index=1,
        last_index=8,
        explicit_targets=(),
        applicable_gxp=_ALL_GXP,
        branch_condition="COMMON_I2",
        source_expression="TenCtydd",
        source_line=744,
    ),
    "Diadiemx": _OperationRule(
        operation_type="WRITE",
        first_index=1,
        last_index=3,
        explicit_targets=(),
        applicable_gxp=_ALL_GXP,
        branch_condition="COMMON_I2",
        source_expression="LCase_FirstChar(Tinhthanhx)",
        source_line=746,
    ),
    "VKNx": _OperationRule(
        operation_type="WRITE",
        first_index=None,
        last_index=None,
        explicit_targets=(),
        applicable_gxp=_GMP_GLP,
        branch_condition="Sel_GPs = 1 Or Sel_GPs = 2",
        source_expression="s1 from Get_VKN",
        source_line=751,
    ),
    "VKN": _OperationRule(
        operation_type="WRITE",
        first_index=1,
        last_index=2,
        explicit_targets=(),
        applicable_gxp=_GMP_GLP,
        branch_condition="(Sel_GPs = 1 Or Sel_GPs = 2) And i = 2",
        source_expression="s2 from Get_VKN",
        source_line=752,
    ),
    "TTx": _OperationRule(
        operation_type="WRITE",
        first_index=None,
        last_index=None,
        explicit_targets=("TT1x", "TT2x"),
        applicable_gxp=_ALL_GXP,
        branch_condition="k <= 1 And k <= UBound(Ds_TTV)",
        source_expression="Trim(Ds_TTV(k))",
        source_line=757,
    ),
    "TT3x": _OperationRule(
        operation_type="WRITE",
        first_index=None,
        last_index=None,
        explicit_targets=("TT3x",),
        applicable_gxp=_ALL_GXP,
        branch_condition="UBound(Ds_TTV) > 1",
        source_expression="TVss",
        source_line=765,
    ),
    "TT3Del": _OperationRule(
        operation_type="DELETE",
        first_index=None,
        last_index=None,
        explicit_targets=("TT3Del",),
        applicable_gxp=_ALL_GXP,
        branch_condition="UBound(Ds_TTV) <= 1",
        source_expression="Delete_Bookmark",
        source_line=766,
    ),
}


def _candidate_names(
    logical_name: str,
    *,
    first_index: int = -1,
    last_index: int = -1,
) -> tuple[str, ...]:
    if not isinstance(logical_name, str) or not logical_name:
        raise QdKtVbaBookmarkContractError("QDKT_LOGICAL_BOOKMARK_INVALID")
    # RecordForm.Replace_Bookmark lines 595-600: series mode is selected only
    # by (i >= 0) And (j > 0); k=0 denotes the unnumbered base name.
    if first_index >= 0 and last_index > 0:
        if first_index > last_index:
            return ()
        return tuple(
            logical_name if index == 0 else f"{logical_name}{index}"
            for index in range(first_index, last_index + 1)
        )
    return (logical_name,)


def resolve_vba_bookmark_targets(
    logical_name: str,
    physical_bookmarks: Iterable[str],
    *,
    first_index: int = -1,
    last_index: int = -1,
) -> tuple[str, ...]:
    """Return existing targets in VBA attempt order, continuing across gaps.

    Missing generated names are omitted because the helper is under
    ``On Error Resume Next``.  Exact generated names are used; near-prefix
    names are never accepted.
    """
    physical = frozenset(physical_bookmarks)
    if any(not isinstance(name, str) or not name for name in physical):
        raise QdKtVbaBookmarkContractError("QDKT_PHYSICAL_BOOKMARK_SET_INVALID")
    return tuple(
        name
        for name in _candidate_names(
            logical_name,
            first_index=first_index,
            last_index=last_index,
        )
        if name in physical
    )


def reconcile_qdkt_i2_bookmarks(
    gxp_type: str,
    physical_bookmarks: Iterable[str],
) -> dict[str, QdKtI2BookmarkOperation]:
    """Reconcile the source-proven series/team operations for QĐKT only."""
    if gxp_type not in SUPPORTED_GXP_TYPES:
        raise QdKtVbaBookmarkContractError("QDKT_GXP_TYPE_UNSUPPORTED")
    physical = tuple(physical_bookmarks)
    result: dict[str, QdKtI2BookmarkOperation] = {}
    for logical_name, rule in _I2_RULES.items():
        branch_reachable = gxp_type in rule.applicable_gxp
        if rule.explicit_targets:
            candidates = rule.explicit_targets
            physical_set = frozenset(physical)
            effective = tuple(name for name in candidates if name in physical_set)
        else:
            first = rule.first_index if rule.first_index is not None else -1
            last = rule.last_index if rule.last_index is not None else -1
            candidates = _candidate_names(
                logical_name, first_index=first, last_index=last,
            )
            effective = resolve_vba_bookmark_targets(
                logical_name,
                physical,
                first_index=first,
                last_index=last,
            )
        if not branch_reachable:
            effective = ()
        result[logical_name] = QdKtI2BookmarkOperation(
            logical_name=logical_name,
            operation_type=rule.operation_type,
            candidate_targets=candidates,
            effective_targets=effective,
            branch_reachable=branch_reachable,
            branch_condition=rule.branch_condition,
            source_expression=rule.source_expression,
            source_line=rule.source_line,
        )
    return result


def plan_repeated_bookmark_value(
    operation: QdKtI2BookmarkOperation,
    value: str,
) -> tuple[tuple[str, str], ...]:
    """Expose the helper's unchanged repeated value without mutating a file."""
    if operation.operation_type != "WRITE":
        raise QdKtVbaBookmarkContractError("QDKT_OPERATION_NOT_WRITE")
    return tuple((target, value) for target in operation.effective_targets)
