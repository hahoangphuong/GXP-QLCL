"""Experimental transaction-receipt gate over the *actual* Change Request service.

This is intentionally TEST-ONLY. There is no production receipt table, API,
idempotency endpoint, authorized lookup, replay, retention, or rollout. The
contract proposed in Draft PR #315 requires owner approval. These regressions
prove only the PostgreSQL transaction mechanics needed for a future decision.

Only disposable loopback PostgreSQL gxp_qlcl_test, in an isolated schema.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import AppUser, AuditEvent, ChangeRequest, Company, Site
from backend.app.services.workflow import CaseWorkflowService


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)

# The synthetic receipt schema is never imported or applied by runtime.
_CREATE_RECEIPT = """
    CREATE TABLE test_receipt (
        operation_id text PRIMARY KEY,
        actor text NOT NULL,
        site_id uuid NOT NULL REFERENCES site(id),
        command_type text NOT NULL,
        fingerprint text NOT NULL,
        result_id uuid REFERENCES change_request(id)
            DEFERRABLE INITIALLY DEFERRED
    )
"""
_RECEIPT_CONSTRAINT = """
    CREATE FUNCTION test_receipt_requires_result() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM test_receipt
            WHERE operation_id = NEW.operation_id AND result_id IS NULL
        ) THEN
            RAISE EXCEPTION 'receipt without committed business result'
                USING ERRCODE = '23514';
        END IF;
        RETURN NULL;
    END $$
"""
_CREATE_TRIGGER = """
    CREATE CONSTRAINT TRIGGER test_receipt_result_required
        AFTER INSERT OR UPDATE ON test_receipt
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION test_receipt_requires_result()
"""


@pytest.fixture
def disposable():
    url = make_url(DATABASE_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "gxp_qlcl_test"
        or url.host not in {"localhost", "127.0.0.1"}
        or url.port != 5432
    ):
        pytest.fail("Only loopback disposable gxp_qlcl_test may be mutated.")

    schema = "cr_receipt_gate_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(text(_CREATE_RECEIPT))
            conn.execute(text(_RECEIPT_CONSTRAINT))
            conn.execute(text(_CREATE_TRIGGER))
        factory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False, future=True,
        )
        with factory() as seed:
            company = Company(legal_name="Synthetic receipt " + schema)
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Site A")
            second_site = Site(company_id=company.id, site_name="Site B")
            seed.add_all([site, second_site])
            seed.add(AppUser(
                username="synthetic-receipt-actor",
                display_name="Synthetic actor", is_active=True,
            ))
            seed.commit()
            ids = (site.id, second_site.id)
        yield factory, ids
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _actor():
    return build_authenticated_user(
        "synthetic-receipt-actor", "manager",
        permissions=["change_request.edit", "change_request.approve"],
    )


def _execute(session, *, site_id, operation_id="synthetic-op",
             fingerprint="synthetic-fingerprint", actor="synthetic-receipt-actor"):
    # A transaction-local candidate: claim a unique command *before* the
    # Site root lock; only the winning transaction executes real workflow.
    claimed = session.execute(text("""
        INSERT INTO test_receipt
            (operation_id, actor, site_id, command_type, fingerprint)
        VALUES (:op, :actor, CAST(:site AS uuid),
                'change_request.create', :fingerprint)
        ON CONFLICT (operation_id) DO NOTHING
        RETURNING operation_id
    """), dict(op=operation_id, actor=actor, site=site_id,
               fingerprint=fingerprint)).scalar_one_or_none()
    if claimed is None:
        existing = session.execute(text("""
            SELECT actor, site_id, command_type, fingerprint, result_id
            FROM test_receipt WHERE operation_id = :op
        """), {"op": operation_id}).one()
        # The hypothetical contract must reject changed intent, rather than
        # return another actor's result or misclassify it as a safe retry.
        if (
            existing.actor != actor
            or str(existing.site_id) != site_id
            or existing.command_type != "change_request.create"
            or existing.fingerprint != fingerprint
        ):
            raise ValueError("synthetic command identity mismatch")
        if existing.result_id is None:
            raise AssertionError("a committed receipt must bind a business result")
        return str(existing.result_id)

    result = CaseWorkflowService().create_change_request(
        session,
        site_id=site_id,
        scope_label="SYNTHETIC",
        description="Transaction receipt experiment",
        submitted_on=None,
        requester_name=None,
        reason="Proof only",
        user=_actor(),
    )
    session.execute(text("""
        UPDATE test_receipt SET result_id = CAST(:result AS uuid)
        WHERE operation_id = :op
    """), dict(result=result["change_request_id"], op=operation_id))
    return result["change_request_id"]


def _lookup(session, *, operation_id, actor, site_id):
    # This is not an authorized endpoint: it only models non-disclosure
    # after the caller's real authorization has been checked elsewhere.
    return session.execute(text("""
        SELECT result_id FROM test_receipt
        WHERE operation_id = :op AND actor = :actor
          AND site_id = CAST(:site AS uuid)
          AND result_id IS NOT NULL
    """), dict(op=operation_id, actor=actor, site=site_id)).scalar_one_or_none()


def _counts(session):
    return (
        session.scalar(select(func.count(ChangeRequest.id))),
        session.scalar(
            select(func.count(AuditEvent.id))
            .where(AuditEvent.action == "change_request.create")
        ),
        session.scalar(text("SELECT count(*) FROM test_receipt")),
    )


def test_committed_response_lost_then_same_operation_returns_one_result(disposable):
    factory, (site_id, _) = disposable
    with factory() as original:
        result_id = _execute(original, site_id=site_id)
        original.commit()  # Simulate lost HTTP response *after* commit.
    with factory() as recovered:
        assert str(_lookup(
            recovered, operation_id="synthetic-op",
            actor="synthetic-receipt-actor", site_id=site_id,
        )) == result_id
        assert _execute(recovered, site_id=site_id) == result_id
        recovered.commit()
    with factory() as verify:
        assert _counts(verify) == (1, 1, 1)


def test_rollback_before_commit_leaves_no_receipt_or_business(disposable):
    factory, (site_id, _) = disposable
    with factory() as interrupted:
        attempted_id = _execute(interrupted, site_id=site_id)
        interrupted.rollback()  # Simulate connection lost before commit.
    with factory() as verify:
        assert _counts(verify) == (0, 0, 0)
        assert _lookup(
            verify, operation_id="synthetic-op",
            actor="synthetic-receipt-actor", site_id=site_id,
        ) is None
    with factory() as retry:
        committed_id = _execute(retry, site_id=site_id)
        retry.commit()
    assert committed_id != attempted_id
    with factory() as verify:
        assert _counts(verify) == (1, 1, 1)


def test_concurrent_same_operation_waits_then_observes_committed_result(disposable):
    factory, (site_id, _) = disposable
    with factory() as first, factory() as competitor:
        first_id = _execute(first, site_id=site_id)
        # A separate transaction cannot claim the same operation before the
        # first one resolves. A bounded lock_timeout makes this deterministic.
        competitor.execute(text("SET LOCAL lock_timeout = '250ms'"))
        with pytest.raises(OperationalError) as blocked:
            _execute(competitor, site_id=site_id)
        assert blocked.value.orig.sqlstate == "55P03"
        competitor.rollback()
        first.commit()
        assert _execute(competitor, site_id=site_id) == first_id
        competitor.commit()
    with factory() as verify:
        assert _counts(verify) == (1, 1, 1)


@pytest.mark.parametrize(
    "changed",
    [
        dict(fingerprint="different-payload"),
        dict(actor="different-actor"),
    ],
)
def test_reused_operation_with_different_identity_is_rejected(disposable, changed):
    factory, (site_id, _) = disposable
    with factory() as first:
        original = _execute(first, site_id=site_id)
        first.commit()
    with factory() as competitor:
        with pytest.raises(ValueError, match="identity mismatch"):
            _execute(competitor, site_id=site_id, **changed)
        competitor.rollback()
    with factory() as verify:
        assert _counts(verify) == (1, 1, 1)
        assert str(verify.get(ChangeRequest, original).id) == original


def test_same_operation_cross_site_rejected_and_lookup_is_non_disclosing(disposable):
    factory, (site_id, other_site_id) = disposable
    with factory() as first:
        first_id = _execute(first, site_id=site_id)
        first.commit()
    with factory() as other_site:
        assert _lookup(
            other_site, operation_id="synthetic-op",
            actor="synthetic-receipt-actor", site_id=other_site_id,
        ) is None
        assert _lookup(
            other_site, operation_id="synthetic-op",
            actor="other-actor", site_id=site_id,
        ) is None
        with pytest.raises(ValueError, match="identity mismatch"):
            _execute(other_site, site_id=other_site_id)
        other_site.rollback()
    with factory() as verify:
        assert _counts(verify) == (1, 1, 1)
        assert verify.get(ChangeRequest, first_id).site_id == site_id


def test_committed_receipt_without_result_is_rejected_by_database(disposable):
    factory, (site_id, _) = disposable
    with factory() as incomplete:
        incomplete.execute(text("""
            INSERT INTO test_receipt
                (operation_id, actor, site_id, command_type, fingerprint)
            VALUES ('incomplete-op', 'synthetic-receipt-actor',
                    CAST(:site AS uuid), 'change_request.create',
                    'synthetic-fingerprint')
        """), {"site": site_id})
        with pytest.raises(IntegrityError) as denied:
            incomplete.commit()
        assert denied.value.orig.sqlstate == "23514"
        incomplete.rollback()
    with factory() as verify:
        assert _counts(verify) == (0, 0, 0)
