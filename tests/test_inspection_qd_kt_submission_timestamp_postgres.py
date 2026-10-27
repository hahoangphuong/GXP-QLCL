"""Disposable PostgreSQL type/offset evidence; no business rows are accessed."""
import os
from datetime import date, datetime
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text

from backend.app.document.inspection_qd_kt_renderer_contract import normalize_submission_date


def test_actual_postgres_column_and_session_offset_do_not_prove_business_date():
    if os.environ.get("GXP_QDKT_POSTGRES_CONCURRENCY_INTEGRATION") != "1":
        pytest.skip("Opt-in disposable PostgreSQL CI only")
    url = os.environ.get("DATABASE_URL", "")
    parsed = urlparse(url.replace("postgresql+psycopg://", "postgresql://", 1))
    if (parsed.scheme != "postgresql" or parsed.hostname not in ("127.0.0.1", "localhost")
        or parsed.port != 5432 or parsed.path != "/gxp_qlcl_test" or parsed.username != "postgres"):
        pytest.fail("QDKT timestamp test refuses non-disposable database")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            column_type = connection.execute(text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'case_application' "
                "AND column_name = 'submitted_on'"
            )).scalar_one()
            assert column_type == "timestamp with time zone"
            values = []
            for zone in ("UTC", "Etc/GMT-7"):
                connection.execute(text("SELECT set_config('TimeZone', :zone, true)"), {"zone": zone})
                values.append(connection.execute(text("SELECT CAST(:value AS timestamptz)"),
                    {"value": "2026-01-02T00:30:00+07:00"}).scalar_one())
            assert all(isinstance(value, datetime) and value.utcoffset() is not None for value in values)
            assert values[0] == values[1]  # same instant, different calendar day
            assert [normalize_submission_date(value, rule="AWARE_RECORDED_OFFSET_DATE") for value in values] == [date(2026, 1, 1), date(2026, 1, 2)]
            connection.rollback()
    finally:
        engine.dispose()
