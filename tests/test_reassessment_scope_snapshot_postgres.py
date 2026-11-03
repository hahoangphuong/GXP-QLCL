"""PostgreSQL concurrency: reassessment must copy one coherent source scope.

A CERTIFIED source permits reassessment creation (not an OPEN_CASE_STATE)
and still permits structured Evaluation Scope edits (not a TERMINAL_CASE_STATE).
The creator locks Site; the editor locks Case. Interleave the copy between
loading source-scope metadata and fetching its child blocks.
"""
from __future__ import annotations

import os
from threading import Event, Thread
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    Case, CaseEvaluationScope, CaseEvaluationScopeBlock,
    CaseEvaluationScopeSelection, Company, EvaluationScopeTaxonomyNode,
    EvaluationScopeTaxonomyVersion, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


def test_reassessment_copies_consistent_scope_while_certified_source_is_edited():
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test required; no mutation performed.")
    schema = "reassessment_scope_copy_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = None
    created_schema = False
    reader_at_blocks = Event()
    continue_copy = Event()
    writer_finished = Event()
    result: dict[str, object] = {}
    threads: list[Thread] = []
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created_schema = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as setup:
            company = Company(legal_name="Synthetic reassessment " + schema)
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="Synthetic source site")
            setup.add(site)
            setup.flush()
            source = Case(site_id=site.id, gxp_type="GLP", state=CaseState.CERTIFIED)
            setup.add(source)
            version = EvaluationScopeTaxonomyVersion(
                taxonomy_content_sha256="c" * 64,
                source_workbook_sha256="d" * 64,
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
                case_id=source.id, taxonomy_version_id=version.id,
                source_classification="STRUCTURED_VALID",
                raw_legacy_value="synthetic authoritative scope source",
                limitation_text="original",
            )
            setup.add(scope)
            setup.flush()
            block = CaseEvaluationScopeBlock(
                case_evaluation_scope_id=scope.id, ordinal=1, name="original",
            )
            setup.add(block)
            setup.flush()
            setup.add(CaseEvaluationScopeSelection(
                block_id=block.id, taxonomy_node_id=node.id, source_order=1,
                custom_description="", node_key_snapshot=node.node_key,
                taxonomy_description_snapshot=node.description,
            ))
            setup.commit()
            site_id, source_id, node_id, scope_version = site.id, source.id, node.id, scope.row_version

        service = CaseWorkflowService()
        user = build_authenticated_user("synthetic-reassessment", "manager")

        def create_copy():
            try:
                with factory() as contender:
                    def block_read_hook(conn, cursor, statement, parameters, context, executemany):
                        if (
                            "case_evaluation_scope_block" in statement.lower()
                            and "ORDER BY" in statement.upper()
                            and not reader_at_blocks.is_set()
                        ):
                            reader_at_blocks.set()
                            if not continue_copy.wait(timeout=20):
                                raise AssertionError("Timed out releasing scope copy read")
                    event.listen(contender.connection(), "before_cursor_execute", block_read_hook)
                    created = service.create_inspection_case(
                        contender, site_id=site_id, gxp_type="GLP",
                        line_code=None, production_line_id=None,
                        applicable_standard=None, reason="synthetic reassessment",
                        source_case_id=source_id, user=user,
                    )
                    contender.commit()
                    result["created_case_id"] = created["case_id"]
            except BaseException as exc:
                result["reader_error"] = repr(exc)
                reader_at_blocks.set()
                continue_copy.set()

        def edit_source():
            try:
                with factory() as editor:
                    service.upsert_evaluation_scope(
                        editor, case_id=source_id, expected_version=scope_version,
                        limitation_text="edited",
                        blocks=[{
                            "name": "edited", "note": None,
                            "selections": [{
                                "taxonomy_node_id": node_id, "custom_description": "",
                            }],
                        }],
                        reason="synthetic concurrent scope update", user=user,
                    )
                    editor.commit()
            except BaseException as exc:
                result["writer_error"] = repr(exc)
            finally:
                writer_finished.set()

        reader = Thread(target=create_copy, name="scope-copy-reader")
        reader.start()
        threads.append(reader)
        assert reader_at_blocks.wait(timeout=20), "Copy never reached source-block SELECT"
        assert "reader_error" not in result, result

        writer = Thread(target=edit_source, name="scope-editor")
        writer.start()
        threads.append(writer)
        # If source Case is not locked by the copy, this edit commits before
        # the copy proceeds, exposing a mixed-version aggregate. With an owner
        # lock, the editor must wait until the copy transaction commits.
        writer_completed_before_copy = writer_finished.wait(timeout=4)
        continue_copy.set()
        reader.join(timeout=20)
        writer.join(timeout=20)
        assert not reader.is_alive() and not writer.is_alive(), "Concurrent operations did not finish"
        assert "reader_error" not in result, result
        assert "writer_error" not in result, result
        assert writer_finished.is_set()
        assert "created_case_id" in result, result

        with factory() as verify:
            copied = verify.scalar(select(CaseEvaluationScope).where(
                CaseEvaluationScope.case_id == result["created_case_id"]
            ))
            assert copied is not None
            copied_blocks = list(verify.scalars(select(CaseEvaluationScopeBlock).where(
                CaseEvaluationScopeBlock.case_evaluation_scope_id == copied.id
            )))
            assert len(copied_blocks) == 1
            observed_pair = (copied.limitation_text, copied_blocks[0].name)
            assert observed_pair in {("original", "original"), ("edited", "edited")}, (
                f"Torn reassessment scope snapshot: {observed_pair}; "
                f"editor_committed_before_block_fetch={writer_completed_before_copy}"
            )
            source_after = verify.scalar(select(CaseEvaluationScope).where(
                CaseEvaluationScope.case_id == source_id
            ))
            assert source_after.limitation_text == "edited"
    finally:
        continue_copy.set()
        for thread in threads:
            thread.join(timeout=22)
        if engine is not None:
            engine.dispose()
        if created_schema:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
