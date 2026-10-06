from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.document.inspection_ke_hoach_kt_generation_date import (
    BUSINESS_TIMEZONE_NAME,
    InspectionKeHoachKtGenerationDateError,
    project_inspection_ke_hoach_kt_generation_date,
)


def test_khkt_generation_date_uses_vietnam_business_timezone_across_midnight():
    before_midnight = project_inspection_ke_hoach_kt_generation_date(
        datetime(2026, 10, 5, 16, 59, 59, tzinfo=timezone.utc)
    )
    at_midnight = project_inspection_ke_hoach_kt_generation_date(
        datetime(2026, 10, 5, 17, 0, 0, tzinfo=timezone.utc)
    )

    assert BUSINESS_TIMEZONE_NAME == "Asia/Ho_Chi_Minh"
    assert before_midnight.generated_on.isoformat() == "2026-10-05"
    assert before_midnight.fulldate == "ngày 05 tháng 10 năm 2026"
    assert at_midnight.generated_on.isoformat() == "2026-10-06"
    assert at_midnight.fulldate == "ngày 06 tháng 10 năm 2026"


def test_khkt_generation_date_rejects_timezone_naive_timestamp():
    with pytest.raises(
        InspectionKeHoachKtGenerationDateError,
        match="timezone-aware",
    ):
        project_inspection_ke_hoach_kt_generation_date(datetime(2026, 10, 6, 12, 0, 0))
