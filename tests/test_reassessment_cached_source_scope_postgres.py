"""PostgreSQL regression: reassessment must ignore stale ORM source-scope identity.

The creator Session reads the source aggregate, an independent transaction
commits an edit, then the creator takes the Case lock and copies the scope.
A Case row lock alone does not refresh an already loaded SQLAlchemy object.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AppUser, Case, CaseEvaluationScope, CaseEvaluationScopeBlock,
    CaseEvaluationScopeSelection, Company, EvaluationScopeTaxonomyNode,
    EvaluationScopeTaxonomyVersion, Site,
)
from backend.app.services.workflow import CaseWorkflowService


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_reassessment_copy_refreshes_cached_source_scope_after_committed_edit():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test required; no mutation performed.")
    schema = "reassessment_cached_scope_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = None
    created_schema = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created_schema = True
        engine = create_engine(
            DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as setup:
            company = Company(legal_name="Synthetic cached source scope " + schema)
            setup.add(company)
            setup.add(AppUser(
                username="synthetic-scope-copy",
                display_name="Synthetic Scope Copy",
                is_active=True,
            ))
            setup.flush()
            site = Site(company_id=company.id, site_name="Synthetic reassessment site")
            setup.add(site)
            setup.flush()
            source = Case(site_id=site.id, gxp_type="GLP", state=CaseState.CERTIFIED)
            setup.add(source)
            taxonomy = EvaluationScopeTaxonomyVersion(
                taxonomy_content_sha256="e" * 64,
                source_workbook_sha256="f" * 64,
                schema_version="evaluation-scope-taxonomy/v1",
            )
            setup.add(taxonomy)
            setup.flush()
            node = EvaluationScopeTaxonomyNode(
                taxonomy_version_id=taxonomy.id, gxp_type="GLP",
                source_name="PVCN_GLP", node_key="1",
                description="Synthetic Root", source_order=1, source_excel_row=4,
            )
            setup.add(node)
            setup.flush()
            scope = CaseEvaluationScope(
                case_id=source.id, taxonomy_version_id=taxonomy.id,
                source_classification="STRUCTURED_VALID",
                raw_legacy_value="synthetic source",
                limitation_text="before",
            )
            setup.add(scope)
            setup.flush()
            block = CaseEvaluationScopeBlock(
                case_evaluation_scope_id=scope.id, ordinal=1, name="before",
            )
            setup.add(block)
            setup.flush()
            selection = CaseEvaluationScopeSelection(
                block_id=block.id, taxonomy_node_id=node.id, source_order=1,
                custom_description="before",
                node_key_snapshot=node.node_key,
                taxonomy_description_snapshot=node.description,
            )
            setup.add(selection)
            setup.commit()
            site_id, source_id = site.id, source.id
            scope_id, block_id, selection_id = scope.id, block.id, selection.id

        service = CaseWorkflowService()
        user = build_authenticated_user("synthetic-scope-copy", "manager")
        # Begin a Session and cache all source levels before a separate
        # transaction edits them. Commit the reader transaction so it can
        # subsequently acquire a fresh READ COMMITTED snapshot.
        with factory() as creator:
            # Retain strong references: SQLAlchemy's identity map can drop
            # clean objects if no Python reference remains.
            cached_scope = creator.get(CaseEvaluationScope, scope_id)
            cached_block = creator.get(CaseEvaluationScopeBlock, block_id)
            cached_selection = creator.get(CaseEvaluationScopeSelection, selection_id)
            assert cached_scope.limitation_text == "before"
            assert cached_block.name == "before"
            assert cached_selection.custom_description == "before"
            creator.commit()

            with factory() as editor:
                current_scope = editor.get(CaseEvaluationScope, scope_id)
                current_block = editor.get(CaseEvaluationScopeBlock, block_id)
                current_selection = editor.get(CaseEvaluationScopeSelection, selection_id)
                current_scope.limitation_text = "after"
                current_block.name = "after"
                current_selection.custom_description = "after"
                editor.commit()

            # Reassessment create is the actual backend mutation: Site lock,
            # source Case lock, owner validation, aggregate copy and audit.
            created = service.create_inspection_case(
                creator, site_id=site_id, gxp_type="GLP",
                line_code=None, production_line_id=None,
                applicable_standard=None, reason="canonical cached scope",
                source_case_id=source_id, user=user,
            )
            creator.commit()
            created_id = created["case_id"]

        with factory() as verify:
            copied = verify.scalar(select(CaseEvaluationScope).where(
                CaseEvaluationScope.case_id == created_id
            ))
            assert copied is not None
            assert copied.limitation_text == "after"
            copied_block = verify.scalar(select(CaseEvaluationScopeBlock).where(
                CaseEvaluationScopeBlock.case_evaluation_scope_id == copied.id
            ))
            assert copied_block is not None
            assert copied_block.name == "after"
            copied_selection = verify.scalar(select(CaseEvaluationScopeSelection).where(
                CaseEvaluationScopeSelection.block_id == copied_block.id
            ))
            assert copied_selection is not None
            assert copied_selection.custom_description == "after"
            assert copied.case_id == created_id
            assert verify.get(Case, source_id).state == CaseState.CERTIFIED
    finally:
        if engine is not None:
            engine.dispose()
        if created_schema:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
