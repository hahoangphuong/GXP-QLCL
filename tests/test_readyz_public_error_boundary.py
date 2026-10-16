"""Public readiness must not echo SQL credentials, hosts, or driver diagnostics.

Both readiness failure paths are exercised through the real route owner.
These are deliberately synthetic errors; no VM or rehearsal DB is contacted.
"""

import json
from types import SimpleNamespace

import pytest

from backend.app.api.routers import health
from backend.app.main import create_app


class BrokenConnection:
    def __call__(self):
        raise RuntimeError(
            "psycopg connection to postgres.private.internal:5432 refused; "
            "postgresql://runtime_user:secret-password@10.148.0.3/gxp_legacy_rehearsal"
        )


class FakeSession:
    def __init__(self, *, broken_revision=False, revision="test-head"):
        self.broken_revision = broken_revision
        self.revision = revision
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement):
        query = str(statement)
        self.statements.append(query)
        if query == "SELECT 1":
            return SimpleNamespace()
        if query == "SELECT version_num FROM alembic_version":
            if self.broken_revision:
                raise RuntimeError(
                    "relation alembic_version missing at /opt/gxp/private/schema; "
                    "user=runtime_user password=secret-password host=10.148.0.3"
                )
            return SimpleNamespace(scalar_one=lambda: self.revision)
        raise AssertionError(f"Unexpected SQL in readiness test: {query}")


@pytest.fixture
def readiness_app(monkeypatch):
    monkeypatch.setattr(health, "expected_alembic_head_revision", lambda: "test-head")
    app = create_app("sqlite:///:memory:")
    return app


def response_body(response):
    return json.loads(response.body)


def assert_no_internal_details(body):
    contents = json.dumps(body)
    for forbidden in (
        "secret-password", "runtime_user", "10.148.0.3",
        "postgres.private.internal", "gxp_legacy_rehearsal",
        "/opt/gxp/private/schema", "psycopg",
    ):
        assert forbidden not in contents


def test_readyz_unreachable_database_is_503_with_safe_public_error(readiness_app):
    readiness_app.state.session_factory = BrokenConnection()
    response = health.readyz(SimpleNamespace(app=readiness_app))
    body = response_body(response)

    assert response.status_code == 503
    assert body["ok"] is False
    assert body["database_reachable"] is False
    assert body["schema_current"] is False
    assert body["database_error"] == "database_unavailable"
    assert_no_internal_details(body)


def test_readyz_schema_query_failure_is_503_with_safe_public_error(readiness_app):
    session = FakeSession(broken_revision=True)
    readiness_app.state.session_factory = lambda: session
    response = health.readyz(SimpleNamespace(app=readiness_app))
    body = response_body(response)

    assert response.status_code == 503
    assert session.statements == [
        "SELECT 1", "SELECT version_num FROM alembic_version",
    ]
    assert body["ok"] is False
    assert body["database_reachable"] is True
    assert body["schema_current"] is False
    assert body["actual_revision"] is None
    assert body["database_error"] == "schema_revision_unavailable"
    assert_no_internal_details(body)


def test_readyz_healthy_contract_remains_200_and_no_error(readiness_app):
    session = FakeSession()
    readiness_app.state.session_factory = lambda: session
    response = health.readyz(SimpleNamespace(app=readiness_app))
    body = response_body(response)

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["database_reachable"] is True
    assert body["schema_current"] is True
    assert body["expected_revision"] == "test-head"
    assert body["actual_revision"] == "test-head"
    assert body["database_error"] is None
    assert session.statements == [
        "SELECT 1", "SELECT version_num FROM alembic_version",
    ]


def test_readyz_schema_revision_drift_still_fails_closed(readiness_app):
    session = FakeSession(revision="old-revision")
    readiness_app.state.session_factory = lambda: session
    response = health.readyz(SimpleNamespace(app=readiness_app))
    body = response_body(response)

    assert response.status_code == 503
    assert body["database_reachable"] is True
    assert body["schema_current"] is False
    assert body["actual_revision"] == "old-revision"
    assert body["expected_revision"] == "test-head"
    assert body["database_error"] is None
