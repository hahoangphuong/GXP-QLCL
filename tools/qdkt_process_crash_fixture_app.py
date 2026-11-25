"""Fail-closed loopback-only QĐKT crash test worker.

This is imported by Uvicorn ONLY under an explicit disposable integration test.
It intentionally terminates its own process at a selected POST commit boundary.
Never import from application runtime code.
"""
from __future__ import annotations

import os
import re

from sqlalchemy.engine import make_url

if os.environ.get("GXP_QDKT_CRASH_TEST") != "1":
    raise RuntimeError("QĐKT crash worker requires explicit disposable test opt-in.")
if os.environ.get("GXP_CANONICAL_WORKFLOW_POSTGRES") != "1":
    raise RuntimeError("QĐKT crash worker requires the isolated PostgreSQL gate.")
if os.environ.get("APP_ENV", "development").lower() in {"production", "prod"}:
    raise RuntimeError("QĐKT crash worker cannot run in production mode.")

db_url = os.environ.get("DATABASE_URL", "")
url = make_url(db_url) if db_url else None
options = url.query.get("options", "") if url is not None else ""
if (
    url is None or url.get_backend_name() != "postgresql"
    or url.host not in {"localhost", "127.0.0.1"}
    or url.port != 5432
    or url.database not in {"gxp_qlcl_test", "gxp_workflow_disposable"}
    or not re.fullmatch(r"-csearch_path=workflow_it_[0-9a-f]{32}", options)
):
    raise RuntimeError("QĐKT crash worker requires exact disposable loopback schema.")

mode = os.environ.get("GXP_QDKT_CRASH_MODE")
if mode not in {"precommit", "postcommit", "recovery"}:
    raise RuntimeError("QĐKT crash worker requires an explicit crash phase.")

from backend.app.main import create_app
import backend.app.api.routers.workflow as workflow_router

app = create_app(
    db_url,
    app_env={
        "AUTH_MODE": "header_stub",
        "APP_ENV": "development",
        "DATABASE_URL": db_url,
        "DB_MODE": "local_postgres",
    },
)

if mode != "recovery":
    original_commit = workflow_router.commit_or_409

    def crash_at_boundary(session):
        if mode == "precommit":
            os._exit(74)
        original_commit(session)
        # SQLAlchemy has returned from the real PostgreSQL commit.
        # The process dies before the endpoint can return HTTP response.
        os._exit(73)

    workflow_router.commit_or_409 = crash_at_boundary
