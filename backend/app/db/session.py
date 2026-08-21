from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def build_engine(database_url: str):
    return create_engine(database_url, future=True)


def build_session_factory(database_url: str):
    engine = build_engine(database_url)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope(database_url: str) -> Iterator[Session]:
    factory = build_session_factory(database_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
