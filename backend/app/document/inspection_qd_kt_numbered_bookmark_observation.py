"""Physical numbered bookmark families in QĐKT templates (read-only evidence).

A logical VBA label and the physical Word bookmark may differ. This module
only classifies exact base+positive-decimal-index names; it does NOT emulate an
unreviewed VBA helper, prove a Case data owner, or enable rendering.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Collection


@dataclass(frozen=True)
class NumberedBookmarkObservation:
    logical_name: str
    numbered_targets: tuple[str, ...]
    indices: tuple[int, ...]
    exact_target_present: bool
    business_owner_verified: bool = False
    vba_write_semantics_verified: bool = False
    ready_to_render: bool = False


def observe_numbered_bookmarks(
    logical_name: str, physical_names: Collection[str],
) -> NumberedBookmarkObservation:
    if not logical_name or not isinstance(logical_name, str):
        raise ValueError("A nonempty logical bookmark name is required.")
    if any(not isinstance(name, str) or not name for name in physical_names):
        raise ValueError("Invalid physical bookmark name.")
    if len(set(physical_names)) != len(physical_names):
        raise ValueError("Duplicate physical bookmark names.")
    pattern = re.compile(rf"{re.escape(logical_name)}([1-9][0-9]*)\Z")
    matches = []
    for name in physical_names:
        match = pattern.fullmatch(name)
        if match:
            matches.append((int(match.group(1)), name))
    matches.sort(key=lambda item: (item[0], item[1]))
    if len({index for index, _ in matches}) != len(matches):
        raise ValueError("Ambiguous numbered bookmark index.")
    return NumberedBookmarkObservation(
        logical_name=logical_name,
        numbered_targets=tuple(name for _, name in matches),
        indices=tuple(index for index, _ in matches),
        exact_target_present=logical_name in physical_names,
    )
