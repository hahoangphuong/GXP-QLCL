from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


#
# Exact Word WdUnits numeric values used by active
# Input_DC_to_CC.
#
WD_CHARACTER = 1
WD_LINE = 5
WD_CELL = 12


class CertificateDetailCursorContractError(
    RuntimeError
):
    pass


CursorActionKind = Literal[
    "end_key",
    "move_right",
    "emit_custom_description_vi",
    "emit_custom_description_en",
]


@dataclass(frozen=True)
class CertificateDetailCursorAction:
    """
    One deterministic cursor/composition action derived
    from active legacy Input_DC_to_CC.

    This is a geometry contract only.

    It does NOT:
    - mutate OOXML;
    - translate text;
    - render custom-description text;
    - load source fragments;
    - emulate Microsoft Word.
    """

    sequence: int
    kind: CursorActionKind

    unit: int | None = None
    count: int | None = None

    legacy_member: str | None = None


@dataclass(frozen=True)
class CertificateDetailFragmentCursorPlan:
    """
    Cursor transition after one source fragment has been
    assigned through Selection.FormattedText.
    """

    description_present: bool
    eng_part: bool

    actions: tuple[
        CertificateDetailCursorAction,
        ...,
    ]


def build_fragment_cursor_plan(
    *,
    description_present: bool,
    eng_part: bool,
) -> CertificateDetailFragmentCursorPlan:
    """
    Exact active-VBA cursor contract after:

        Selection.FormattedText = <source bookmark>.Range.FormattedText

    Proven legacy structure:

    If description exists:
        EndKey Unit:=5

        TypeText <VI description>

        If EngPart Then
            MoveRight Unit:=12, Count:=2
            MoveRight Unit:=1, Count:=1
            TypeText <EN description>
        End If

        MoveRight Unit:=1, Count:=2

    Else:
        EndKey Unit:=5

        If EngPart Then
            MoveRight Unit:=12, Count:=2
            MoveRight Unit:=1, Count:=1
        End If

        MoveRight Unit:=1, Count:=2
    End If

    Important:
    - Unit 5  = wdLine
    - Unit 12 = wdCell
    - Unit 1  = wdCharacter

    main_topic / packaging_special / normal affect only
    the text payload emitted by TypeText; they do not
    affect this cursor geometry.
    """

    actions: list[
        CertificateDetailCursorAction
    ] = []

    sequence = 0

    def emit(
        kind: CursorActionKind,
        *,
        unit: int | None = None,
        count: int | None = None,
        legacy_member: str | None = None,
    ) -> None:
        nonlocal sequence

        sequence += 1

        actions.append(
            CertificateDetailCursorAction(
                sequence=sequence,
                kind=kind,
                unit=unit,
                count=count,
                legacy_member=(
                    legacy_member
                ),
            )
        )

    #
    # Both branches begin with:
    #
    # Selection.EndKey Unit:=5
    #
    emit(
        "end_key",
        unit=WD_LINE,
        legacy_member="EndKey",
    )

    if description_present:
        #
        # One of the three semantic branches:
        #
        # main_topic
        # packaging_special
        # normal
        #
        # Geometry is identical.
        #
        emit(
            "emit_custom_description_vi",
            legacy_member="TypeText",
        )

    if eng_part:
        #
        # Selection.MoveRight Unit:=12, count:=2
        #
        # Unit 12 = wdCell.
        #
        emit(
            "move_right",
            unit=WD_CELL,
            count=2,
            legacy_member="MoveRight",
        )

        #
        # Selection.MoveRight Unit:=1, count:=1
        #
        # Unit 1 = wdCharacter.
        #
        emit(
            "move_right",
            unit=WD_CHARACTER,
            count=1,
            legacy_member="MoveRight",
        )

        if description_present:
            emit(
                "emit_custom_description_en",
                legacy_member="TypeText",
            )

    #
    # Both branches finally execute:
    #
    # Selection.MoveRight Unit:=1, count:=2
    #
    emit(
        "move_right",
        unit=WD_CHARACTER,
        count=2,
        legacy_member="MoveRight",
    )

    return (
        CertificateDetailFragmentCursorPlan(
            description_present=(
                description_present
            ),
            eng_part=eng_part,
            actions=tuple(
                actions
            ),
        )
    )


def validate_fragment_cursor_plan(
    plan: CertificateDetailFragmentCursorPlan,
) -> None:
    """
    Fail closed if a cursor plan does not conform to the
    proven legacy state-machine boundary.
    """

    expected = build_fragment_cursor_plan(
        description_present=(
            plan.description_present
        ),
        eng_part=(
            plan.eng_part
        ),
    )

    if plan != expected:
        raise (
            CertificateDetailCursorContractError(
                "Certificate-detail fragment cursor plan "
                "does not match the proven "
                "Input_DC_to_CC contract."
            )
        )