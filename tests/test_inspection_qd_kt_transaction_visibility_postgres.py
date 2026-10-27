"""Disposable PostgreSQL contract: ORM refresh does not override MVCC isolation.

This test uses ONLY the loopback GitHub CI database. It never reads or writes
production tables, document data or storage objects.
"""
import os
from urllib.parse import urlparse

import pytest
from sqlalchemy import Column, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session

URL = os.environ.get("DATABASE_URL", "")
ENABLED = os.environ.get("GXP_QDKT_POSTGRES_CONCURRENCY_INTEGRATION") == "1"


class Base(DeclarativeBase):
    pass


class VisibilityProbe(Base):
    __tablename__ = "qdkt_ci_transaction_visibility_probe"
    id = Column(Integer, primary_key=True)
    value = Column(String(100), nullable=False)


def _checked_ci_url():
    if not ENABLED:
        pytest.skip("Opt-in disposable PostgreSQL CI only")
    parsed = urlparse(URL.replace("postgresql+psycopg://", "postgresql://", 1))
    if (
        parsed.scheme != "postgresql"
        or parsed.hostname not in ("127.0.0.1", "localhost")
        or parsed.port != 5432
        or parsed.path != "/gxp_qlcl_test"
        or parsed.username != "postgres"
    ):
        pytest.fail("QDKT PostgreSQL visibility test refuses non-disposable database")
    return URL


@pytest.mark.parametrize("isolation,should_see_update", [
    ("READ COMMITTED", True),
    ("REPEATABLE READ", False),
])
def test_populate_existing_refresh_respects_postgres_snapshot(isolation, should_see_update):
    engine = create_engine(_checked_ci_url())
    try:
        Base.metadata.create_all(engine, checkfirst=True)
        with engine.begin() as conn:
            conn.execute(VisibilityProbe.__table__.delete())
            conn.execute(VisibilityProbe.__table__.insert().values(id=1, value="before"))

        with (
            engine.connect().execution_options(isolation_level=isolation) as reader_connection,
            Session(reader_connection, autoflush=False) as reader,
            Session(engine, autoflush=False) as writer,
        ):
            first = reader.scalars(select(VisibilityProbe).where(VisibilityProbe.id == 1)).one()
            assert first.value == "before"

            writer.execute(
                VisibilityProbe.__table__.update()
                .where(VisibilityProbe.id == 1)
                .values(value="after")
            )
            writer.commit()

            # Same ORM object: a normal SELECT can retain the old attributes.
            cached = reader.scalars(select(VisibilityProbe).where(VisibilityProbe.id == 1)).one()
            assert cached is first
            assert cached.value == "before"

            refreshed = reader.scalars(
                select(VisibilityProbe)
                .where(VisibilityProbe.id == 1)
                .execution_options(populate_existing=True)
            ).one()
            assert refreshed is first
            assert refreshed.value == ("after" if should_see_update else "before")
            reader.rollback()
    finally:
        Base.metadata.drop_all(engine, checkfirst=True)
        engine.dispose()
