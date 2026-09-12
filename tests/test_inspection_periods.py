from datetime import date

import pytest

from backend.app.domain.inspection_periods import InspectionPeriodSourceState, parse_legacy_inspection_periods


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("20-21/10/2017", ((date(2017, 10, 20), date(2017, 10, 21)),)),
        ("31/07 - 01/08/2009", ((date(2009, 7, 31), date(2009, 8, 1)),)),
        ("20, 21, 25/01/2021", ((date(2021, 1, 20), date(2021, 1, 20)), (date(2021, 1, 21), date(2021, 1, 21)), (date(2021, 1, 25), date(2021, 1, 25)))),
        ("01/01/2021; 03-04/01/2021 và 06/01/2021", ((date(2021, 1, 1), date(2021, 1, 1)), (date(2021, 1, 3), date(2021, 1, 4)), (date(2021, 1, 6), date(2021, 1, 6)))),
        ("2021-01-20 00:00:00+00:00", ((date(2021, 1, 20), date(2021, 1, 20)),)),
    ],
)
def test_parser_preserves_each_ordered_source_segment(value, expected):
    result = parse_legacy_inspection_periods(value)
    assert result.state == InspectionPeriodSourceState.KNOWN
    assert tuple((segment.started_on, segment.ended_on) for segment in result.segments) == expected


@pytest.mark.parametrize(
    ("value", "state"),
    [("", "MISSING"), ("???", "PENDING_INPUT"), ("-", "NOT_APPLICABLE"), ("Xét hồ sơ", "NON_DATE_EXPRESSION"), ("24-01/2018", "UNRESOLVED")],
)
def test_parser_keeps_sentinels_and_unresolved_values_distinct(value, state):
    assert parse_legacy_inspection_periods(value).state.value == state
