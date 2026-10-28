"""Real PostgreSQL transaction-isolation evidence for multi-SELECT reports.

A report issuing separate version and generation-run SELECTs cannot infer a
single consistent snapshot under READ COMMITTED. These disposable test tables
and transactions do not access production data or storage.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires PostgreSQL test database", allow_module_level=True)


@pytest.mark.parametrize(
    ("isolation", "expected_after_concurrent_commit"),
    [
        ("READ COMMITTED", 1),
        ("REPEATABLE READ", 0),
    ],
)
def test_two_selects_have_different_snapshot_contracts(
    isolation, expected_after_concurrent_commit,
):
    engine = create_engine(DATABASE_URL, future=True)
    table = f"output_snapshot_probe_{uuid4().hex}"
    try:
        # DDL and the writer's commits are deliberately outside the reader.
        with engine.begin() as creator:
            creator.execute(text(f"CREATE TABLE {table} (id integer PRIMARY KEY)"))
        with engine.connect().execution_options(isolation_level=isolation) as reader:
            with reader.begin():
                assert reader.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
                with engine.begin() as writer:
                    writer.execute(text(f"INSERT INTO {table} (id) VALUES (1)"))
                observed = reader.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                assert observed == expected_after_concurrent_commit
    finally:
        with engine.begin() as cleanup:
            cleanup.execute(text(f"DROP TABLE IF EXISTS {table}"))
        engine.dispose()
