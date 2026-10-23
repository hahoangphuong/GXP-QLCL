"""Pure legacy-source QĐKT team layout instructions; no document mutation.

Accepts a *source-attested* formatted legacy TTVdd string, never derives it
from modern team-member names or roles. It does not authorize production render.
"""
from __future__ import annotations
from dataclasses import dataclass


class QdKtTeamLayoutBlocked(ValueError):
    pass


@dataclass(frozen=True)
class QdKtTeamLayoutInstructions:
    first: str
    second: str
    third_and_later: tuple[str, ...]
    delete_third_member_bookmark: bool
    template_extension_required: bool
    source_equivalence_proven: bool = False
    renderer_authorized: bool = False


def plan_qdkt_team_layout(*, legacy_display: str, source_attested: bool,
                          template_extension: str | None) -> QdKtTeamLayoutInstructions:
    """Capture only proven split/count semantics of RecordForm.frm:754-766.

    TT_ext is a *template-derived formatting fragment*: the planner returns
    logical members, not a guessed Word line break or conditional deletion.
    """
    if not source_attested:
        raise QdKtTeamLayoutBlocked("LEGACY_TEAM_DISPLAY_SOURCE_UNATTESTED")
    if not isinstance(legacy_display, str) or not legacy_display.strip():
        raise QdKtTeamLayoutBlocked("LEGACY_TEAM_DISPLAY_MISSING")
    members = tuple(part.strip() for part in legacy_display.split("|"))
    if len(members) < 2 or any(not part for part in members):
        raise QdKtTeamLayoutBlocked("LEGACY_TEAM_MEMBER_CARDINALITY_OR_EMPTY_TOKEN")
    if len(members) > 3 and (not isinstance(template_extension, str) or not template_extension.strip()):
        raise QdKtTeamLayoutBlocked("TEAM_EXTENSION_FRAGMENT_MISSING")
    return QdKtTeamLayoutInstructions(
        first=members[0], second=members[1], third_and_later=members[2:],
        delete_third_member_bookmark=len(members) == 2,
        template_extension_required=len(members) > 3,
    )
