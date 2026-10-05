from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError


def _raise_stale_conflict(session: Session, exc: StaleDataError) -> None:
    session.rollback()
    raise HTTPException(
        status_code=409,
        detail="Stale update detected. Reload and retry with the latest version.",
    ) from exc


def commit_or_409(session: Session) -> None:
    try:
        session.commit()
    except StaleDataError as exc:
        _raise_stale_conflict(session, exc)


def get_session_from_request_factory(session_factory):
    def get_session():
        session = session_factory()
        try:
            yield session
        except StaleDataError as exc:
            # Optimistic-lock conflicts can surface during a service-level
            # flush before the endpoint reaches commit_or_409(). The request
            # transaction boundary owns translating either timing into 409.
            _raise_stale_conflict(session, exc)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return get_session
