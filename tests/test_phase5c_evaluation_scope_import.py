import copy
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import Base
from backend.app.db.models.phase1 import (
    Case,
    CaseEvaluationScope,
    CaseEvaluationScopeBlock,
    CaseEvaluationScopeSelection,
    CaseEvaluationScopeUnkeyedEntry,
    EvaluationScopeTaxonomyNode,
    EvaluationScopeTaxonomyVersion,
    Company,
    Site,
)
from backend.app.domain import phase2_import as phase2_import_module
from backend.app.domain.phase2_import import (
    ImportCollisionError,
    _load_evaluation_scope_taxonomy,
    import_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]
REAL_SNAPSHOT_PATH = ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json"
REAL_TAXONOMY_PATH = ROOT / "artifacts" / "legacy_snapshot" / "evaluation_scope_taxonomy.json"


def _snapshot(scope: str, *, gxp_type: str = "GMP") -> dict[str, list[dict[str, str]]]:
    return {
        "db.cty": [{"ID": "1", "TÊN CÔNG TY": "Company A"}],
        "db.cso": [{"ID": "10", "ID Cty": "1", "TÊN CƠ SỞ": "Site A"}],
        "db.ktra": [
            {
                "ID": "100",
                "LOẠI KT": gxp_type,
                "ID CƠ SỞ": "10",
                "PHẠM VI KIỂM TRA": scope,
            }
        ],
        "db.cc": [],
        "db.dkkd": [],
        "db.Tdoi": [],
        "db.Tdoi2": [],
    }


def _import(scope: str, *, gxp_type: str = "GMP") -> tuple[Session, object]:
    engine = create_engine("sqlite:///:memory:", future=True)
    session = Session(engine)
    import_snapshot(session, _snapshot(scope, gxp_type=gxp_type))
    session.commit()
    return session, engine


def _semantic_counts(session: Session) -> dict[str, int]:
    return {
        "versions": session.scalar(select(func.count()).select_from(EvaluationScopeTaxonomyVersion)),
        "nodes": session.scalar(select(func.count()).select_from(EvaluationScopeTaxonomyNode)),
        "aggregates": session.scalar(select(func.count()).select_from(CaseEvaluationScope)),
        "blocks": session.scalar(select(func.count()).select_from(CaseEvaluationScopeBlock)),
        "selections": session.scalar(select(func.count()).select_from(CaseEvaluationScopeSelection)),
        "unkeyed": session.scalar(select(func.count()).select_from(CaseEvaluationScopeUnkeyedEntry)),
    }


def test_structured_scope_preserves_authoritative_fidelity_and_case_linkage():
    raw = "Rendered prose\r\n(*Aggregate limit*)\r\n{Block name¶1: Changed\r- free text¿Block note§Second¶1.1:}*"
    session, engine = _import(raw)
    try:
        case = session.scalar(select(Case).where(Case.legacy_inspection_id == 100))
        scope = session.scalar(select(CaseEvaluationScope))
        blocks = list(session.scalars(select(CaseEvaluationScopeBlock).order_by(CaseEvaluationScopeBlock.ordinal)))
        selections = list(session.scalars(select(CaseEvaluationScopeSelection).order_by(CaseEvaluationScopeSelection.source_order)))
        unkeyed = list(session.scalars(select(CaseEvaluationScopeUnkeyedEntry)))

        assert scope.case_id == case.id
        assert scope.source_classification == "STRUCTURED_VALID"
        assert scope.raw_legacy_value == raw
        assert scope.rendered_prose == "Rendered prose"
        assert scope.limitation_text == "Aggregate limit"
        assert scope.row_version == 1
        assert [(block.ordinal, block.name, block.note) for block in blocks] == [
            (1, "Block name", "Block note"),
            (2, "Second", None),
        ]
        assert [(item.source_order, item.custom_description, item.node_key_snapshot) for item in selections] == [
            (1, "Changed", "1"),
            (1, "", "1.1"),
        ]
        assert all(item.taxonomy_description_snapshot for item in selections)
        assert [(item.source_order, item.text) for item in unkeyed] == [(2, "- free text")]
    finally:
        session.close()
        engine.dispose()


def test_prose_only_gmpbb_does_not_invent_gmp_taxonomy_binding():
    session, engine = _import("Legacy prose without a structured selection", gxp_type="GMPbb")
    try:
        scope = session.scalar(select(CaseEvaluationScope))
        assert scope.source_classification == "PROSE_ONLY"
        assert scope.taxonomy_version_id is None
        assert session.scalar(select(func.count()).select_from(CaseEvaluationScopeSelection)) == 0
    finally:
        session.close()
        engine.dispose()


def test_unknown_structured_node_fails_closed():
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(ImportCollisionError, match="STRUCTURED_PARTIAL"):
        import_snapshot(session, _snapshot("{999: not in authoritative taxonomy}*"))
    engine.dispose()


def test_taxonomy_hash_mismatch_fails_closed(monkeypatch, tmp_path: Path):
    artifact = json.loads(REAL_TAXONOMY_PATH.read_text(encoding="utf-8"))
    artifact["named_ranges"]["PVCN_GMP"]["rows"][0]["description"] = "tampered"
    tampered = tmp_path / "taxonomy.json"
    tampered.write_text(json.dumps(artifact), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "EVALUATION_SCOPE_TAXONOMY_PATH", tampered)
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session, pytest.raises(ValueError, match="semantic hash"):
        _load_evaluation_scope_taxonomy(session)
    engine.dispose()


def test_taxonomy_versions_are_immutable_and_same_hash_is_reused(monkeypatch, tmp_path: Path):
    artifact = json.loads(REAL_TAXONOMY_PATH.read_text(encoding="utf-8"))
    first = tmp_path / "first.json"
    first.write_text(json.dumps(artifact), encoding="utf-8")
    monkeypatch.setattr(phase2_import_module, "EVALUATION_SCOPE_TAXONOMY_PATH", first)
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _artifact, version = _load_evaluation_scope_taxonomy(session)
        first_node = session.scalar(select(EvaluationScopeTaxonomyNode).where(EvaluationScopeTaxonomyNode.taxonomy_version_id == version.id))
        original_description = first_node.description
        _artifact, reused = _load_evaluation_scope_taxonomy(session)
        assert reused.id == version.id

        changed = copy.deepcopy(artifact)
        changed["named_ranges"]["PVCN_GMP"]["rows"][0]["description"] = "new taxonomy description"
        from backend.app.domain.evaluation_scope import taxonomy_content_hash

        changed["taxonomy_content_sha256"] = taxonomy_content_hash(changed["named_ranges"])
        second = tmp_path / "second.json"
        second.write_text(json.dumps(changed), encoding="utf-8")
        monkeypatch.setattr(phase2_import_module, "EVALUATION_SCOPE_TAXONOMY_PATH", second)
        _artifact, newer = _load_evaluation_scope_taxonomy(session)
        session.flush()

        assert newer.id != version.id
        assert session.get(EvaluationScopeTaxonomyNode, first_node.id).description == original_description
        assert session.scalar(select(func.count()).select_from(EvaluationScopeTaxonomyVersion)) == 2
    engine.dispose()


def test_taxonomy_seed_uses_one_version_lookup_and_no_per_node_selects():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    try:
        with Session(engine) as session:
            _artifact, version = _load_evaluation_scope_taxonomy(session)
            session.flush()
            assert session.scalar(select(func.count()).select_from(EvaluationScopeTaxonomyNode)) == 401
            assert version.id
        select_count = sum(statement.lstrip().upper().startswith("SELECT") for statement in statements)
        # Version reuse is looked up once; node parent resolution uses the in-memory batch.
        assert select_count <= 2
    finally:
        event.remove(engine, "before_cursor_execute", capture_statement)
        engine.dispose()


def test_full_rebuilds_on_independent_clean_databases_are_semantically_equal():
    raw = "Rendered\r\n{1: exact\r2: second}*"
    first_session, first_engine = _import(raw)
    second_session, second_engine = _import(raw)
    try:
        assert _semantic_counts(first_session) == _semantic_counts(second_session)
        assert _semantic_counts(first_session) == {
            "versions": 1,
            "nodes": 401,
            "aggregates": 1,
            "blocks": 1,
            "selections": 2,
            "unkeyed": 0,
        }
    finally:
        first_session.close()
        first_engine.dispose()
        second_session.close()
        second_engine.dispose()


def test_real_artifact_reconciliation_counts():
    snapshot = json.loads(REAL_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    engine = create_engine("sqlite:///:memory:", future=True)
    with Session(engine) as session:
        import_snapshot(session, snapshot)
        session.commit()
        aggregates = list(session.scalars(select(CaseEvaluationScope)))
        blocks = list(session.scalars(select(CaseEvaluationScopeBlock)))

        assert session.scalar(select(func.count()).select_from(EvaluationScopeTaxonomyVersion)) == 1
        assert session.scalar(select(func.count()).select_from(EvaluationScopeTaxonomyNode).where(EvaluationScopeTaxonomyNode.gxp_type == "GMP")) == 112
        assert session.scalar(select(func.count()).select_from(EvaluationScopeTaxonomyNode).where(EvaluationScopeTaxonomyNode.gxp_type == "GLP")) == 237
        assert session.scalar(select(func.count()).select_from(EvaluationScopeTaxonomyNode).where(EvaluationScopeTaxonomyNode.gxp_type == "GSP")) == 52
        assert session.scalar(select(func.count()).select_from(EvaluationScopeTaxonomyNode)) == 401
        assert sum(scope.source_classification == "STRUCTURED_VALID" for scope in aggregates) == 677
        assert sum(scope.source_classification == "PROSE_ONLY" for scope in aggregates) == 819
        assert len(aggregates) == 1496
        assert session.scalar(select(func.count()).select_from(CaseEvaluationScopeSelection)) == 9762
        assert sum(1 for scope in aggregates if sum(block.case_evaluation_scope_id == scope.id for block in blocks) > 1) == 22
        assert sum(block.name is not None for block in blocks) == 54
        assert sum(block.note is not None for block in blocks) == 12
        assert sum(scope.limitation_text is not None for scope in aggregates) == 454
        assert session.scalar(select(func.count()).select_from(CaseEvaluationScopeUnkeyedEntry)) == 903

        raw_rows = [row.get("PHẠM VI KIỂM TRA", "") for row in snapshot["db.ktra"]]
        assert sum(not str(value).strip() for value in raw_rows) == 47
    engine.dispose()


def test_postgresql_migration_constraints_when_disposable_url_is_supplied():
    database_url = os.environ.get("C5C_POSTGRES_URL")
    if not database_url:
        pytest.skip("C5C_POSTGRES_URL is required for disposable PostgreSQL migration validation")

    engine = create_engine(database_url, future=True)
    try:
        with Session(engine) as session:
            assert session.scalar(text("SELECT version_num FROM alembic_version")) == "20260901_0007"
            first = EvaluationScopeTaxonomyVersion(
                taxonomy_content_sha256="a" * 64,
                source_workbook_sha256="b" * 64,
                schema_version="test",
            )
            second = EvaluationScopeTaxonomyVersion(
                taxonomy_content_sha256="c" * 64,
                source_workbook_sha256="d" * 64,
                schema_version="test",
            )
            session.add_all([first, second])
            session.flush()
            root_gmp = EvaluationScopeTaxonomyNode(
                taxonomy_version_id=first.id,
                gxp_type="GMP",
                source_name="PVCN_GMP",
                node_key="1",
                description="GMP root",
                source_order=1,
                source_excel_row=1,
            )
            root_glp = EvaluationScopeTaxonomyNode(
                taxonomy_version_id=first.id,
                gxp_type="GLP",
                source_name="PVCN_GLP",
                node_key="1",
                description="GLP root",
                source_order=1,
                source_excel_row=1,
            )
            session.add_all([root_gmp, root_glp])
            session.flush()
            child = EvaluationScopeTaxonomyNode(
                taxonomy_version_id=first.id,
                parent_node_id=root_gmp.id,
                gxp_type="GMP",
                source_name="PVCN_GMP",
                node_key="1.1",
                description="GMP child",
                source_order=2,
                source_excel_row=2,
            )
            session.add(child)
            session.flush()

            company = Company(legal_name="Migration validation company")
            session.add(company)
            session.flush()
            site = Site(company_id=company.id, site_name="Migration validation site")
            session.add(site)
            session.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state="application_received")
            session.add(case)
            session.flush()
            scope = CaseEvaluationScope(
                case_id=case.id,
                taxonomy_version_id=first.id,
                source_classification="STRUCTURED_VALID",
                raw_legacy_value="{1: test}*",
            )
            session.add(scope)
            session.flush()
            assert scope.row_version == 1
            session.commit()

        with Session(engine) as session:
            root_gmp = session.scalar(select(EvaluationScopeTaxonomyNode).where(EvaluationScopeTaxonomyNode.gxp_type == "GMP", EvaluationScopeTaxonomyNode.node_key == "1"))
            second = session.scalar(select(EvaluationScopeTaxonomyVersion).where(EvaluationScopeTaxonomyVersion.taxonomy_content_sha256 == "c" * 64))
            session.add(
                EvaluationScopeTaxonomyNode(
                    taxonomy_version_id=second.id,
                    parent_node_id=root_gmp.id,
                    gxp_type="GMP",
                    source_name="PVCN_GMP",
                    node_key="1.1",
                    description="cross-version parent",
                    source_order=1,
                    source_excel_row=1,
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            first = session.scalar(select(EvaluationScopeTaxonomyVersion).where(EvaluationScopeTaxonomyVersion.taxonomy_content_sha256 == "a" * 64))
            session.add(
                EvaluationScopeTaxonomyNode(
                    taxonomy_version_id=first.id,
                    parent_node_id=root_gmp.id,
                    gxp_type="GLP",
                    source_name="PVCN_GLP",
                    node_key="1.1",
                    description="cross-gxp parent",
                    source_order=2,
                    source_excel_row=2,
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()

            first = session.scalar(select(EvaluationScopeTaxonomyVersion).where(EvaluationScopeTaxonomyVersion.taxonomy_content_sha256 == "a" * 64))
            session.add(
                EvaluationScopeTaxonomyNode(
                    taxonomy_version_id=first.id,
                    gxp_type="GMP",
                    source_name="PVCN_GMP",
                    node_key="1",
                    description="duplicate key",
                    source_order=99,
                    source_excel_row=99,
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
    finally:
        engine.dispose()
