"""Disposable PostgreSQL: Evaluation Scope must reject stale terminal Case.

The second Session has a cached nonterminal Case; a separate transaction
commits CLOSED. Taxonomy-scoped editing must recheck the authoritative parent
and avoid replacing blocks, selections or the aggregate after closure.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, CaseEvaluationScope, CaseEvaluationScopeBlock,
    CaseEvaluationScopeSelection, Company, EvaluationScopeTaxonomyNode,
    EvaluationScopeTaxonomyVersion, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_evaluation_scope_revalidates_case_terminal_owner_before_aggregate_edit():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test required; no mutations performed.")
    schema = "scope_terminal_refresh_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = contender = closing = None
    created_schema = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created_schema = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as setup:
            company = Company(legal_name="Synthetic scope terminal " + schema)
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="Synthetic scope site")
            setup.add(site)
            setup.flush()
            case = Case(site_id=site.id, gxp_type="GLP", state=CaseState.DRAFT)
            setup.add(case)
            version = EvaluationScopeTaxonomyVersion(
                taxonomy_content_sha256="a" * 64,
                source_workbook_sha256="b" * 64,
                schema_version="evaluation-scope-taxonomy/v1",
            )
            setup.add(version)
            setup.flush()
            node = EvaluationScopeTaxonomyNode(
                taxonomy_version_id=version.id, gxp_type="GLP",
                source_name="PVCN_GLP", node_key="1", description="Synthetic Root",
                source_order=1, source_excel_row=4,
            )
            setup.add(node)
            setup.flush()
            scope = CaseEvaluationScope(
                case_id=case.id, taxonomy_version_id=version.id,
                source_classification="STRUCTURED_VALID",
            )
            setup.add(scope)
            setup.commit()
            case_id, scope_id, token, node_id = case.id, scope.id, scope.row_version, node.id

        service = CaseWorkflowService()
        user = build_authenticated_user("synthetic-scope-editor", "manager")
        contender = factory()
        cached = contender.get(Case, case_id)
        assert cached.state == CaseState.DRAFT
        closing = factory()
        row = closing.get(Case, case_id)
        row.state = CaseState.CLOSED
        closing.commit()

        with pytest.raises(HTTPException) as denied:
            service.upsert_evaluation_scope(
                contender, case_id=case_id, expected_version=token,
                limitation_text="Must not persist",
                blocks=[{
                    "name": "Synthetic block",
                    "note": None,
                    "selections": [{"taxonomy_node_id": node_id, "custom_description": ""}],
                }],
                reason="stale Case identity regression",
                user=user,
            )
        assert denied.value.status_code == 409
        contender.rollback()

        with factory() as verify:
            assert verify.get(Case, case_id).state == CaseState.CLOSED
            persisted = verify.get(CaseEvaluationScope, scope_id)
            assert persisted.row_version == token
            assert persisted.limitation_text is None
            assert verify.scalar(select(func.count(CaseEvaluationScopeBlock.id))) == 0
            assert verify.scalar(select(func.count(CaseEvaluationScopeSelection.id))) == 0
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        for sess in (contender, closing):
            if sess is not None:
                sess.rollback()
                sess.close()
        if engine is not None:
            engine.dispose()
        if created_schema:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
