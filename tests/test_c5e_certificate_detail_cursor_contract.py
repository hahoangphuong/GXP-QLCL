from __future__ import annotations

from dataclasses import replace

import pytest

from backend.app.document.c5e_certificate_detail_cursor_contract import (
    CertificateDetailCursorContractError,
    CertificateDetailFragmentCursorPlan,
    WD_CELL,
    WD_CHARACTER,
    WD_LINE,
    build_fragment_cursor_plan,
    validate_fragment_cursor_plan,
)


def _shape(
    plan,
):
    return [
        (
            action.kind,
            action.unit,
            action.count,
        )
        for action in plan.actions
    ]


def test_word_unit_constants_are_locked():
    #
    # Microsoft Word WdUnits values used by the active
    # legacy procedure.
    #
    assert WD_CHARACTER == 1
    assert WD_LINE == 5
    assert WD_CELL == 12


def test_description_true_eng_part_true_exact_sequence():
    plan = build_fragment_cursor_plan(
        description_present=True,
        eng_part=True,
    )

    assert _shape(
        plan
    ) == [
        (
            "end_key",
            WD_LINE,
            None,
        ),
        (
            "emit_custom_description_vi",
            None,
            None,
        ),
        (
            "move_right",
            WD_CELL,
            2,
        ),
        (
            "move_right",
            WD_CHARACTER,
            1,
        ),
        (
            "emit_custom_description_en",
            None,
            None,
        ),
        (
            "move_right",
            WD_CHARACTER,
            2,
        ),
    ]


def test_description_true_eng_part_false_exact_sequence():
    plan = build_fragment_cursor_plan(
        description_present=True,
        eng_part=False,
    )

    assert _shape(
        plan
    ) == [
        (
            "end_key",
            WD_LINE,
            None,
        ),
        (
            "emit_custom_description_vi",
            None,
            None,
        ),
        (
            "move_right",
            WD_CHARACTER,
            2,
        ),
    ]


def test_description_false_eng_part_true_exact_sequence():
    plan = build_fragment_cursor_plan(
        description_present=False,
        eng_part=True,
    )

    assert _shape(
        plan
    ) == [
        (
            "end_key",
            WD_LINE,
            None,
        ),
        (
            "move_right",
            WD_CELL,
            2,
        ),
        (
            "move_right",
            WD_CHARACTER,
            1,
        ),
        (
            "move_right",
            WD_CHARACTER,
            2,
        ),
    ]


def test_description_false_eng_part_false_exact_sequence():
    plan = build_fragment_cursor_plan(
        description_present=False,
        eng_part=False,
    )

    assert _shape(
        plan
    ) == [
        (
            "end_key",
            WD_LINE,
            None,
        ),
        (
            "move_right",
            WD_CHARACTER,
            2,
        ),
    ]


@pytest.mark.parametrize(
    (
        "description_present",
        "eng_part",
    ),
    [
        (
            True,
            True,
        ),
        (
            True,
            False,
        ),
        (
            False,
            True,
        ),
        (
            False,
            False,
        ),
    ],
)
def test_sequence_numbers_are_contiguous(
    description_present,
    eng_part,
):
    plan = build_fragment_cursor_plan(
        description_present=(
            description_present
        ),
        eng_part=eng_part,
    )

    assert [
        action.sequence
        for action in plan.actions
    ] == list(
        range(
            1,
            len(plan.actions) + 1,
        )
    )


def test_main_topic_packaging_and_normal_do_not_belong_to_cursor_contract():
    #
    # Semantic branch deliberately does not appear as an
    # input to build_fragment_cursor_plan().
    #
    # All three legacy description branches have identical
    # cursor movement.
    #
    plan = build_fragment_cursor_plan(
        description_present=True,
        eng_part=True,
    )

    assert not hasattr(
        plan,
        "branch",
    )

    assert not any(
        hasattr(
            action,
            "branch",
        )
        for action in plan.actions
    )


def test_eng_part_controls_cell_navigation_even_without_description():
    #
    # Critical legacy behavior:
    #
    # even when PV_Desc is blank, EngPart=True still performs
    # the wdCell navigation before the final two-character
    # movement.
    #
    plan = build_fragment_cursor_plan(
        description_present=False,
        eng_part=True,
    )

    cell_moves = [
        action
        for action in plan.actions
        if (
            action.kind
            == "move_right"
            and action.unit
            == WD_CELL
        )
    ]

    assert len(
        cell_moves
    ) == 1

    assert (
        cell_moves[0].count
        == 2
    )


def test_description_english_emit_is_strictly_eng_part_gated():
    without_english = (
        build_fragment_cursor_plan(
            description_present=True,
            eng_part=False,
        )
    )

    with_english = (
        build_fragment_cursor_plan(
            description_present=True,
            eng_part=True,
        )
    )

    assert (
        "emit_custom_description_en"
        not in {
            action.kind
            for action
            in without_english.actions
        }
    )

    assert (
        "emit_custom_description_en"
        in {
            action.kind
            for action
            in with_english.actions
        }
    )


def test_no_description_never_emits_custom_description_text():
    for eng_part in (
        False,
        True,
    ):
        plan = (
            build_fragment_cursor_plan(
                description_present=False,
                eng_part=eng_part,
            )
        )

        kinds = {
            action.kind
            for action in plan.actions
        }

        assert (
            "emit_custom_description_vi"
            not in kinds
        )

        assert (
            "emit_custom_description_en"
            not in kinds
        )


def test_every_plan_begins_with_end_key_wdline():
    for description_present in (
        False,
        True,
    ):
        for eng_part in (
            False,
            True,
        ):
            plan = (
                build_fragment_cursor_plan(
                    description_present=(
                        description_present
                    ),
                    eng_part=eng_part,
                )
            )

            first = (
                plan.actions[0]
            )

            assert (
                first.kind
                == "end_key"
            )

            assert (
                first.unit
                == WD_LINE
            )

            assert (
                first.count
                is None
            )


def test_every_plan_ends_with_move_right_two_characters():
    for description_present in (
        False,
        True,
    ):
        for eng_part in (
            False,
            True,
        ):
            plan = (
                build_fragment_cursor_plan(
                    description_present=(
                        description_present
                    ),
                    eng_part=eng_part,
                )
            )

            last = (
                plan.actions[-1]
            )

            assert (
                last.kind
                == "move_right"
            )

            assert (
                last.unit
                == WD_CHARACTER
            )

            assert (
                last.count
                == 2
            )


def test_validate_accepts_canonical_plan():
    plan = build_fragment_cursor_plan(
        description_present=True,
        eng_part=True,
    )

    validate_fragment_cursor_plan(
        plan
    )


def test_validate_rejects_modified_plan():
    plan = build_fragment_cursor_plan(
        description_present=True,
        eng_part=True,
    )

    actions = list(
        plan.actions
    )

    actions[-1] = replace(
        actions[-1],
        count=3,
    )

    invalid = (
        CertificateDetailFragmentCursorPlan(
            description_present=True,
            eng_part=True,
            actions=tuple(
                actions
            ),
        )
    )

    with pytest.raises(
        CertificateDetailCursorContractError
    ):
        validate_fragment_cursor_plan(
            invalid
        )