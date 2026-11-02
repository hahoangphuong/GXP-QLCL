"""Router transaction boundary regression: no hidden retry or accidental commit.

No database is opened: the probe isolates the Session protocol invoked by all
workflow mutation routes. It is intentionally separate from disposable PostgreSQL
concurrency/row-lock suites.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi import HTTPException
from sqlalchemy.orm.exc import StaleDataError

from backend.app.api.session import (
    commit_or_409,
    get_session_from_request_factory,
)


@dataclass
class RecordingSession:
    calls: list[str] = field(default_factory=list)
    commit_error: Exception | None = None

    def commit(self):
        self.calls.append("commit")
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self):
        self.calls.append("rollback")

    def close(self):
        self.calls.append("close")


def test_successful_mutation_commits_once_without_implicit_replay():
    session = RecordingSession()
    commit_or_409(session)
    assert session.calls == ["commit"]


def test_stale_commit_rolls_back_and_translates_to_conflict():
    session = RecordingSession(commit_error=StaleDataError("stale"))
    with pytest.raises(HTTPException) as caught:
        commit_or_409(session)
    assert caught.value.status_code == 409
    assert session.calls == ["commit", "rollback"]


def test_other_commit_failure_is_not_misreported_as_stale_or_retried():
    error = RuntimeError("synthetic commit failure")
    session = RecordingSession(commit_error=error)
    with pytest.raises(RuntimeError) as caught:
        commit_or_409(session)
    assert caught.value is error
    assert session.calls == ["commit"]  # request dependency owns rollback


def test_request_boundary_rolls_back_non_stale_commit_exception_once():
    error = RuntimeError("synthetic commit failure")
    session = RecordingSession(commit_error=error)
    provider = get_session_from_request_factory(lambda: session)
    request = provider()
    assert next(request) is session
    with pytest.raises(RuntimeError) as caught:
        request.throw(error)
    assert caught.value is error
    assert session.calls == ["rollback", "close"]


def test_request_boundary_translates_service_level_stale_flush():
    session = RecordingSession()
    provider = get_session_from_request_factory(lambda: session)
    request = provider()
    assert next(request) is session
    with pytest.raises(HTTPException) as caught:
        request.throw(StaleDataError("stale during flush"))
    assert caught.value.status_code == 409
    assert session.calls == ["rollback", "close"]


def test_request_boundary_does_not_commit_successful_read():
    session = RecordingSession()
    provider = get_session_from_request_factory(lambda: session)
    request = provider()
    assert next(request) is session
    with pytest.raises(StopIteration):
        next(request)
    assert session.calls == ["close"]
