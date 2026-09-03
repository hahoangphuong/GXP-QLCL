from __future__ import annotations

from fastapi import HTTPException
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent,
    Case,
    CaseEvaluationScope,
    CaseEvaluationScopeBlock,
    CaseEvaluationScopeSelection,
    CaseEvaluationScopeUnkeyedEntry,
    Company,
    EvaluationScopeTaxonomyNode,
    EvaluationScopeTaxonomyVersion,
    Site,
)
from backend.app.services.catalog import CatalogReadService
from backend.app.services.workflow import CaseWorkflowService


def _user():
    return build_authenticated_user("scope.editor", "manager")


def _engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _seed_scope(session: Session, *, classification: str = "STRUCTURED_VALID", state: CaseState = CaseState.DRAFT, unkeyed: bool = False):
    company = Company(legal_name="Scope company")
    session.add(company)
    session.flush()
    site = Site(company_id=company.id, site_name="Scope site")
    session.add(site)
    session.flush()
    case = Case(site_id=site.id, gxp_type="GLP", scope_code="A", state=state, inspection_type="Định kỳ")
    session.add(case)
    version = EvaluationScopeTaxonomyVersion(taxonomy_content_sha256="a" * 64, source_workbook_sha256="b" * 64, schema_version="evaluation-scope-taxonomy/v1")
    session.add(version)
    session.flush()
    root = EvaluationScopeTaxonomyNode(taxonomy_version_id=version.id, gxp_type="GLP", source_name="PVCN_GLP", node_key="1", description="Root", hint="Root hint", main_topic="MAIN", short_render="Root", no_expand=None, source_order=1, source_excel_row=4)
    session.add(root)
    session.flush()
    child = EvaluationScopeTaxonomyNode(taxonomy_version_id=version.id, parent_node_id=root.id, gxp_type="GLP", source_name="PVCN_GLP", node_key="1.1", description="Child", hint=None, main_topic=None, short_render="Child $$", no_expand=None, source_order=2, source_excel_row=5)
    foreign = EvaluationScopeTaxonomyNode(taxonomy_version_id=version.id, gxp_type="GMP", source_name="PVCN_GMP", node_key="1", description="Foreign", hint=None, main_topic=None, short_render=None, no_expand=None, source_order=1, source_excel_row=124)
    session.add_all([child, foreign])
    session.flush()
    scope = CaseEvaluationScope(case_id=case.id, taxonomy_version_id=None if classification == "PROSE_ONLY" else version.id, source_classification=classification, raw_legacy_value="{1.1: legacy}*", rendered_prose="Văn bản lịch sử" if classification == "PROSE_ONLY" else None, limitation_text="Giới hạn cũ")
    session.add(scope)
    session.flush()
    first = CaseEvaluationScopeBlock(case_evaluation_scope_id=scope.id, ordinal=1, name="Khối một", note="Ghi chú một", raw_block_value="{1.1: legacy}*")
    second = CaseEvaluationScopeBlock(case_evaluation_scope_id=scope.id, ordinal=2, name="Khối hai", note="Ghi chú hai", raw_block_value="{1: legacy}*")
    session.add_all([first, second])
    session.flush()
    if classification != "PROSE_ONLY":
        session.add_all([
            CaseEvaluationScopeSelection(block_id=first.id, taxonomy_node_id=child.id, source_order=1, custom_description="Mô tả riêng", node_key_snapshot="1.1", taxonomy_description_snapshot="Child"),
            CaseEvaluationScopeSelection(block_id=second.id, taxonomy_node_id=root.id, source_order=1, custom_description="", node_key_snapshot="1", taxonomy_description_snapshot="Root"),
        ])
    if unkeyed:
        session.add(CaseEvaluationScopeUnkeyedEntry(block_id=first.id, source_order=2, text="Mục lịch sử chưa gắn khóa"))
    session.commit()
    return {"case_id": case.id, "site_id": site.id, "scope_id": scope.id, "version_id": version.id, "root_id": root.id, "child_id": child.id, "foreign_id": foreign.id}


def test_case_workspace_projects_structured_scope_exactly_and_locks_unkeyed_entries():
    engine = _engine()
    with Session(engine) as session:
        seeded = _seed_scope(session, unkeyed=True)
    with Session(engine) as session:
        payload = CatalogReadService().get_case_workspace(session, case_id=seeded["case_id"], user=_user())

    scope = payload["evaluation_scope"]
    assert scope["taxonomy_version_id"] == seeded["version_id"]
    assert scope["editable"] is False
    assert "chưa gắn taxonomy" in scope["read_only_reason"]
    assert [(node["key"], node["parent_key"], node["hint"]) for node in scope["taxonomy_nodes"]] == [("1", None, "Root hint"), ("1.1", "1", None)]
    assert [(block["ordinal"], block["name"], block["note"]) for block in scope["blocks"]] == [(1, "Khối một", "Ghi chú một"), (2, "Khối hai", "Ghi chú hai")]
    assert scope["blocks"][0]["selections"][0]["custom_description"] == "Mô tả riêng"
    assert scope["blocks"][1]["selections"][0]["custom_description"] == ""
    assert scope["blocks"][0]["unkeyed_entries"] == [{"source_order": 2, "text": "Mục lịch sử chưa gắn khóa"}]
    assert scope["summary_source"] == "canonical_projection"
    assert "« Khối một » (Ghi chú một)" in scope["summary_text"]
    assert "Mục lịch sử chưa gắn khóa" not in scope["summary_text"]


def test_case_workspace_never_passes_unkeyed_entries_to_vba_renderer(monkeypatch):
    engine = _engine()
    captured: dict[str, object] = {}

    def fake_compile_vba_readable_scope(*, blocks, taxonomy_nodes, limitation_text, gxp_type):
        captured["blocks"] = blocks
        captured["taxonomy_nodes"] = taxonomy_nodes
        captured["limitation_text"] = limitation_text
        captured["gxp_type"] = gxp_type
        return SimpleNamespace(text="Compiled without legacy unkeyed input")

    monkeypatch.setattr(
        "backend.app.services.catalog.compile_vba_readable_scope",
        fake_compile_vba_readable_scope,
    )

    with Session(engine) as session:
        seeded = _seed_scope(session, unkeyed=True)
    with Session(engine) as session:
        payload = CatalogReadService().get_case_workspace(
            session, case_id=seeded["case_id"], user=_user()
        )

    scope = payload["evaluation_scope"]
    assert scope["blocks"][0]["unkeyed_entries"] == [
        {"source_order": 2, "text": "Mục lịch sử chưa gắn khóa"}
    ]
    assert scope["summary_text"] == "Compiled without legacy unkeyed input"
    compiler_blocks = captured["blocks"]
    assert isinstance(compiler_blocks, list)
    assert compiler_blocks
    assert all("unkeyed_entries" not in block for block in compiler_blocks)


def test_case_workspace_projects_prose_only_as_read_only_without_tree_inference():
    engine = _engine()
    with Session(engine) as session:
        seeded = _seed_scope(session, classification="PROSE_ONLY")
    with Session(engine) as session:
        payload = CatalogReadService().get_case_workspace(session, case_id=seeded["case_id"], user=_user())

    scope = payload["evaluation_scope"]
    assert scope["source_classification"] == "PROSE_ONLY"
    assert scope["rendered_prose"] == "Văn bản lịch sử"
    assert scope["summary_text"] == "Văn bản lịch sử"
    assert scope["summary_source"] == "historical_prose"
    assert scope["taxonomy_nodes"] == []
    assert scope["editable"] is False


def test_case_workspace_reports_missing_aggregate_without_inventing_a_taxonomy_scope():
    engine = _engine()
    with Session(engine) as session:
        seeded = _seed_scope(session)
        scope = session.get(CaseEvaluationScope, seeded["scope_id"])
        assert scope is not None
        block_ids = list(session.scalars(select(CaseEvaluationScopeBlock.id).where(CaseEvaluationScopeBlock.case_evaluation_scope_id == scope.id)))
        session.query(CaseEvaluationScopeSelection).filter(CaseEvaluationScopeSelection.block_id.in_(block_ids)).delete(synchronize_session=False)
        session.query(CaseEvaluationScopeBlock).filter(CaseEvaluationScopeBlock.id.in_(block_ids)).delete(synchronize_session=False)
        session.delete(scope)
        session.commit()
    with Session(engine) as session:
        payload = CatalogReadService().get_case_workspace(session, case_id=seeded["case_id"], user=_user())

    scope_read = payload["evaluation_scope"]
    assert scope_read["id"] is None
    assert scope_read["taxonomy_nodes"] == []
    assert scope_read["editable"] is False


def test_structured_scope_mutation_validates_taxonomy_and_writes_one_aggregate_audit_event():
    engine = _engine()
    service = CaseWorkflowService()
    with Session(engine) as session:
        seeded = _seed_scope(session)

    with Session(engine) as session:
        result = service.upsert_evaluation_scope(session, case_id=seeded["case_id"], expected_version=1, limitation_text="Giới hạn mới", blocks=[
            {"name": "Khối A", "note": "Ghi chú A", "selections": [{"taxonomy_node_id": seeded["root_id"], "custom_description": ""}]},
            {"name": "Khối B", "note": None, "selections": [{"taxonomy_node_id": seeded["child_id"], "custom_description": "Tùy chỉnh"}]},
        ], reason="Cập nhật phạm vi", user=_user())
        session.commit()

        scope = session.get(CaseEvaluationScope, seeded["scope_id"])
        assert result["row_version"] == 2
        assert scope is not None and scope.row_version == 2 and scope.limitation_text == "Giới hạn mới"
        blocks = list(session.scalars(select(CaseEvaluationScopeBlock).where(CaseEvaluationScopeBlock.case_evaluation_scope_id == scope.id).order_by(CaseEvaluationScopeBlock.ordinal)))
        assert [(block.ordinal, block.name, block.note) for block in blocks] == [(1, "Khối A", "Ghi chú A"), (2, "Khối B", None)]
        selections_by_block = {
            block.id: list(session.scalars(select(CaseEvaluationScopeSelection).where(CaseEvaluationScopeSelection.block_id == block.id).order_by(CaseEvaluationScopeSelection.source_order)))
            for block in blocks
        }
        assert [item.custom_description for item in selections_by_block[blocks[0].id]] == [""]
        assert [item.custom_description for item in selections_by_block[blocks[1].id]] == ["Tùy chỉnh"]
        assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "case.evaluation_scope.update")) == 1

    with Session(engine) as session:
        payload = CatalogReadService().get_case_workspace(session, case_id=seeded["case_id"], user=_user())["evaluation_scope"]
        assert payload["rendered_prose"] is None
        assert payload["summary_source"] == "canonical_projection"
        assert "« Khối A » (Ghi chú A)" in payload["summary_text"]
        assert "Child Tùy chỉnh" in payload["summary_text"]
        assert "Giới hạn mới" in payload["summary_text"]

    with Session(engine) as session:
        with pytest.raises(HTTPException, match="Stale"):
            service.upsert_evaluation_scope(session, case_id=seeded["case_id"], expected_version=1, limitation_text=None, blocks=[{"name": None, "note": None, "selections": [{"taxonomy_node_id": seeded["root_id"], "custom_description": ""}]}], reason=None, user=_user())
        with pytest.raises(HTTPException, match="does not belong"):
            service.upsert_evaluation_scope(session, case_id=seeded["case_id"], expected_version=2, limitation_text=None, blocks=[{"name": None, "note": None, "selections": [{"taxonomy_node_id": seeded["foreign_id"], "custom_description": ""}]}], reason=None, user=_user())
        with pytest.raises(HTTPException, match="duplicate"):
            service.upsert_evaluation_scope(session, case_id=seeded["case_id"], expected_version=2, limitation_text=None, blocks=[{"name": None, "note": None, "selections": [{"taxonomy_node_id": seeded["root_id"], "custom_description": ""}, {"taxonomy_node_id": seeded["root_id"], "custom_description": ""}]}], reason=None, user=_user())


def test_prose_only_and_terminal_scope_mutations_fail_closed():
    service = CaseWorkflowService()
    for classification, state in (("PROSE_ONLY", CaseState.DRAFT), ("STRUCTURED_VALID", CaseState.CLOSED)):
        engine = _engine()
        with Session(engine) as session:
            seeded = _seed_scope(session, classification=classification, state=state)
        with Session(engine) as session:
            with pytest.raises(HTTPException):
                service.upsert_evaluation_scope(session, case_id=seeded["case_id"], expected_version=1, limitation_text=None, blocks=[{"name": None, "note": None, "selections": [{"taxonomy_node_id": seeded["root_id"], "custom_description": ""}]}], reason=None, user=_user())


def test_unkeyed_scope_mutation_fails_closed_without_deleting_historical_text():
    engine = _engine()
    service = CaseWorkflowService()
    with Session(engine) as session:
        seeded = _seed_scope(session, unkeyed=True)
    with Session(engine) as session:
        with pytest.raises(HTTPException, match="unkeyed"):
            service.upsert_evaluation_scope(session, case_id=seeded["case_id"], expected_version=1, limitation_text=None, blocks=[{"name": None, "note": None, "selections": [{"taxonomy_node_id": seeded["root_id"], "custom_description": ""}]}], reason=None, user=_user())
        assert session.scalar(select(CaseEvaluationScopeUnkeyedEntry.text)) == "Mục lịch sử chưa gắn khóa"


def test_reassessment_copies_exact_scope_snapshot_without_certificate_dependency():
    engine = _engine()
    service = CaseWorkflowService()
    with Session(engine) as session:
        seeded = _seed_scope(session, state=CaseState.CERTIFIED, unkeyed=True)
    with Session(engine) as session:
        created = service.create_inspection_case(session, site_id=seeded["site_id"], gxp_type="GLP", line_code="A", applicable_standard="OECD-GLP", reason="Tái đánh giá", user=_user(), source_case_id=seeded["case_id"])
        session.commit()
        copied = session.scalar(select(CaseEvaluationScope).where(CaseEvaluationScope.case_id == created["case_id"]))
        assert copied is not None and copied.id != seeded["scope_id"] and copied.taxonomy_version_id == seeded["version_id"]
        assert copied.limitation_text == "Giới hạn cũ"
        copied_blocks = list(session.scalars(select(CaseEvaluationScopeBlock).where(CaseEvaluationScopeBlock.case_evaluation_scope_id == copied.id).order_by(CaseEvaluationScopeBlock.ordinal)))
        assert [(block.ordinal, block.name, block.note) for block in copied_blocks] == [(1, "Khối một", "Ghi chú một"), (2, "Khối hai", "Ghi chú hai")]
        copied_selections = {
            block.id: list(session.scalars(select(CaseEvaluationScopeSelection).where(CaseEvaluationScopeSelection.block_id == block.id).order_by(CaseEvaluationScopeSelection.source_order)))
            for block in copied_blocks
        }
        assert [(item.node_key_snapshot, item.custom_description) for item in copied_selections[copied_blocks[0].id]] == [("1.1", "Mô tả riêng")]
        assert [(item.node_key_snapshot, item.custom_description) for item in copied_selections[copied_blocks[1].id]] == [("1", "")]
        assert session.scalar(select(CaseEvaluationScopeUnkeyedEntry.text).where(CaseEvaluationScopeUnkeyedEntry.block_id == copied_blocks[0].id)) == "Mục lịch sử chưa gắn khóa"


def test_reassessment_carries_prose_only_scope_as_prose_without_synthesizing_nodes():
    engine = _engine()
    service = CaseWorkflowService()
    with Session(engine) as session:
        seeded = _seed_scope(session, classification="PROSE_ONLY", state=CaseState.CERTIFIED)
    with Session(engine) as session:
        created = service.create_inspection_case(session, site_id=seeded["site_id"], gxp_type="GLP", line_code="A", applicable_standard="OECD-GLP", reason=None, user=_user(), source_case_id=seeded["case_id"])
        session.commit()
        copied = session.scalar(select(CaseEvaluationScope).where(CaseEvaluationScope.case_id == created["case_id"]))
        assert copied is not None
        assert copied.source_classification == "PROSE_ONLY"
        assert copied.taxonomy_version_id is None
        assert copied.rendered_prose == "Văn bản lịch sử"
        assert session.scalar(select(func.count()).select_from(CaseEvaluationScopeSelection)) == 0
