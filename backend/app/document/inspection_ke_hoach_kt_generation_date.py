from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo


BUSINESS_TIMEZONE_NAME = "Asia/Ho_Chi_Minh"
BUSINESS_TIMEZONE = ZoneInfo(BUSINESS_TIMEZONE_NAME)


class InspectionKeHoachKtGenerationDateError(RuntimeError):
    pass


@dataclass(frozen=True)
class InspectionKeHoachKtGenerationDateProjection:
    generated_on: date
    fulldate: str


def project_inspection_ke_hoach_kt_generation_date(
    generated_at: datetime,
) -> InspectionKeHoachKtGenerationDateProjection:
    """Project legacy FormatDateS(Date, 1) using the approved Vietnam business calendar."""
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise InspectionKeHoachKtGenerationDateError(
            "KHKT generation timestamp must be timezone-aware"
        )
    generated_on = generated_at.astimezone(BUSINESS_TIMEZONE).date()
    return InspectionKeHoachKtGenerationDateProjection(
        generated_on=generated_on,
        fulldate=(
            f"ngày {generated_on.day:02d} tháng {generated_on.month:02d} "
            f"năm {generated_on.year:04d}"
        ),
    )
