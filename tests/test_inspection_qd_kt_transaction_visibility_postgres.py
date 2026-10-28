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


# Dedicated disposable relation probe, not the production Case/Document tables.
# It mirrors the ownership join and exercises two real PostgreSQL connections.
from sqlalchemy import ForeignKey


class BoundaryCase(Base):
    __tablename__ = "qdkt_ci_boundary_case"
    id = Column(String(40), primary_key=True)


class BoundaryDocument(Base):
    __tablename__ = "qdkt_ci_boundary_document"
    id = Column(String(40), primary_key=True)
    case_id = Column(String(40), ForeignKey("qdkt_ci_boundary_case.id"), nullable=False)


class BoundaryBinding(Base):
    __tablename__ = "qdkt_ci_boundary_binding"
    id = Column(String(40), primary_key=True)
    case_id = Column(String(40), ForeignKey("qdkt_ci_boundary_case.id"), nullable=False)
    relative_path = Column(String(200), nullable=False)


class BoundaryVersion(Base):
    __tablename__ = "qdkt_ci_boundary_version"
    id = Column(String(40), primary_key=True)
    document_id = Column(String(40), ForeignKey("qdkt_ci_boundary_document.id"), nullable=False)
    storage_binding_id = Column(String(40), ForeignKey("qdkt_ci_boundary_binding.id"), nullable=False)
    storage_relative_path = Column(String(200), nullable=False)


def _boundary_source(session):
    return session.execute(
        select(
            BoundaryDocument.case_id,
            BoundaryBinding.case_id,
            BoundaryBinding.relative_path,
            BoundaryVersion.storage_relative_path,
            BoundaryVersion.storage_binding_id,
        )
        .join(BoundaryDocument, BoundaryVersion.document_id == BoundaryDocument.id)
        .join(BoundaryBinding, BoundaryVersion.storage_binding_id == BoundaryBinding.id)
        .where(BoundaryVersion.id == "v1")
        .execution_options(populate_existing=True)
    ).one()


@pytest.mark.parametrize("isolation,observes_commit", [
    ("READ COMMITTED", True),
    ("REPEATABLE READ", False),
])
@pytest.mark.parametrize("mutation", ["binding_owner", "binding_path", "version_binding"])
def test_concurrent_case_version_binding_source_visibility(isolation, observes_commit, mutation):
    engine = create_engine(_checked_ci_url())
    try:
        Base.metadata.create_all(engine, checkfirst=True)
        with engine.begin() as conn:
            conn.execute(BoundaryVersion.__table__.delete())
            conn.execute(BoundaryBinding.__table__.delete())
            conn.execute(BoundaryDocument.__table__.delete())
            conn.execute(BoundaryCase.__table__.delete())
            conn.execute(BoundaryCase.__table__.insert(), [{"id": "case-1"}, {"id": "case-2"}])
            conn.execute(BoundaryDocument.__table__.insert().values(id="d1", case_id="case-1"))
            conn.execute(BoundaryBinding.__table__.insert(), [
                {"id": "b1", "case_id": "case-1", "relative_path": "case-1"},
                {"id": "b2", "case_id": "case-2", "relative_path": "case-2"},
            ])
            conn.execute(BoundaryVersion.__table__.insert().values(
                id="v1", document_id="d1", storage_binding_id="b1",
                storage_relative_path="case-1/draft.docx",
            ))
        with (
            engine.connect().execution_options(isolation_level=isolation) as reader_conn,
            Session(reader_conn, autoflush=False) as reader,
            Session(engine, autoflush=False) as writer,
        ):
            initial = _boundary_source(reader)
            assert initial == ("case-1", "case-1", "case-1", "case-1/draft.docx", "b1")
            if mutation == "binding_owner":
                statement = BoundaryBinding.__table__.update().where(
                    BoundaryBinding.id == "b1"
                ).values(case_id="case-2")
            elif mutation == "binding_path":
                statement = BoundaryBinding.__table__.update().where(
                    BoundaryBinding.id == "b1"
                ).values(relative_path="case-2")
            else:
                statement = BoundaryVersion.__table__.update().where(
                    BoundaryVersion.id == "v1"
                ).values(storage_binding_id="b2")
            writer.execute(statement)
            # Uncommitted changes must not be interpreted as observed drift.
            assert _boundary_source(reader) == initial
            writer.commit()
            after = _boundary_source(reader)
            assert (after != initial) is observes_commit
            if observes_commit:
                assert after[0] == "case-1"
                assert after[1] != "case-1" or after[2] != "case-1"
            reader.rollback()
    finally:
        Base.metadata.drop_all(engine, checkfirst=True)
        engine.dispose()
