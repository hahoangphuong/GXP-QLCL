from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError


def commit_or_409(session: Session) -> None:
    try:
        session.commit()
    except StaleDataError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Stale update detected. Reload and retry with the latest version.") from exc


def get_session_from_request_factory(session_factory):
    def get_session():
        session = session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return get_session
