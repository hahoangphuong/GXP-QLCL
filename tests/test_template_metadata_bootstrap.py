from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Base
from backend.app.db.models.phase1 import TemplateBinding, TemplateDefinition
from backend.app.db.session import build_engine
from backend.app.document import seed_runtime
from backend.app.document.seed_runtime import TemplateSeedError, load_template_seed_artifact
from backend.app.document.template_binary import assign_template_binary_locator
from backend.app.document.template_metadata_bootstrap import (
    TemplateMetadataReadinessError,
    bootstrap_default_template_metadata,
    verify_default_template_metadata,
)
from backend.app.document import template_metadata_bootstrap
from tools.bootstrap_template_metadata import bootstrap_template_metadata


ROOT = Path(__file__).resolve().parents[1]


def _session(tmp_path: Path) -> Session:
    engine = build_engine(f"sqlite:///{(tmp_path / 'metadata.db').as_posix()}")
    Base.metadata.create_all(engine)
    return Session(engine)


def _canonical_payload() -> dict[str, list[dict[str, object]]]:
    return load_template_seed_artifact(seed_runtime.phase_artifact_path("phase5", "template_seed.curated.json"))


def _first_definition(session: Session) -> TemplateDefinition:
    seed = _canonical_payload()["template_definitions"][0]
    definition = session.scalar(
        select(TemplateDefinition).where(
            TemplateDefinition.family_code == str(seed["family_code"]),
            TemplateDefinition.template_name == str(seed["template_name"]),
        )
    )
    assert definition is not None
    return definition


def _first_binding(session: Session) -> TemplateBinding:
    seed = _canonical_payload()["template_bindings"][0]
    definition = session.scalar(
        select(TemplateDefinition).where(
            TemplateDefinition.family_code == str(seed["family_code"]),
            TemplateDefinition.template_name == str(seed["template_name"]),
        )
    )
    assert definition is not None
    statement = select(TemplateBinding).where(
        TemplateBinding.family_code == str(seed["family_code"]),
        TemplateBinding.template_definition_id == definition.id,
        TemplateBinding.storage_scope == str(seed["storage_scope"]),
    )
    statement = statement.where(
        TemplateBinding.gxp_type.is_(None)
        if seed["gxp_type"] is None
        else TemplateBinding.gxp_type == str(seed["gxp_type"])
    )
    statement = statement.where(
        TemplateBinding.legacy_mode.is_(None)
        if seed["legacy_mode"] is None
        else TemplateBinding.legacy_mode == str(seed["legacy_mode"])
    )
    binding = session.scalar(statement)
    assert binding is not None
    return binding


def test_empty_database_bootstraps_canonical_subset_idempotently(tmp_path: Path) -> None:
    session = _session(tmp_path)
    try:
        first, readiness = bootstrap_default_template_metadata(session)
        session.commit()
        assert first.template_definitions_created == len(_canonical_payload()["template_definitions"])
        assert first.template_bindings_created == len(_canonical_payload()["template_bindings"])
        assert readiness.canonical_template_definitions == len(_canonical_payload()["template_definitions"])
        assert readiness.canonical_template_bindings == len(_canonical_payload()["template_bindings"])

        second, _ = bootstrap_default_template_metadata(session)
        session.commit()
        assert second.template_definitions_created == 0
        assert second.template_definitions_updated == 0
        assert second.template_bindings_created == 0
        assert second.template_bindings_updated == 0
    finally:
        session.close()


def test_bootstrap_repairs_only_safe_inactive_rows(tmp_path: Path) -> None:
    session = _session(tmp_path)
    try:
        bootstrap_default_template_metadata(session)
        definition = _first_definition(session)
        binding = _first_binding(session)
        definition.is_active = False
        binding.is_active = False
        session.commit()

        summary, _ = bootstrap_default_template_metadata(session)
        session.commit()
        assert summary.template_definitions_updated == 1
        assert summary.template_bindings_updated == 1
    finally:
        session.close()


def test_bootstrap_rejects_conflicting_semantic_row_without_overwrite(tmp_path: Path) -> None:
    session = _session(tmp_path)
    try:
        bootstrap_default_template_metadata(session)
        definition = _first_definition(session)
        definition.bookmark_contract = "{\"unexpected\": true}"
        session.commit()

        with pytest.raises(TemplateSeedError, match="bookmark_contract"):
            bootstrap_default_template_metadata(session)
        session.rollback()
        assert session.get(TemplateDefinition, definition.id).bookmark_contract == "{\"unexpected\": true}"
    finally:
        session.close()


def test_readiness_detects_missing_definition_binding_and_semantic_drift(tmp_path: Path) -> None:
    session = _session(tmp_path)
    try:
        bootstrap_default_template_metadata(session)
        definition = _first_definition(session)
        session.delete(definition)
        session.commit()
        with pytest.raises(TemplateMetadataReadinessError, match="exactly once"):
            verify_default_template_metadata(session)

        session.rollback()
        bootstrap_default_template_metadata(session)
        binding = _first_binding(session)
        session.delete(binding)
        session.commit()
        with pytest.raises(TemplateMetadataReadinessError, match="exactly once"):
            verify_default_template_metadata(session)
    finally:
        session.close()


def test_readiness_allows_runtime_extension_without_count_constraint(tmp_path: Path) -> None:
    session = _session(tmp_path)
    try:
        bootstrap_default_template_metadata(session)
        definition = _first_definition(session)
        assign_template_binary_locator(
            session,
            template_definition_id=definition.id,
            storage_root="template",
            storage_relative_path="runtime-extension.dotx",
            original_filename="runtime-extension.dotx",
            checksum_sha256="a" * 64,
        )
        session.add(
            TemplateBinding(
                family_code=definition.family_code,
                template_definition_id=definition.id,
                gxp_type="RUNTIME_EXTENSION",
                legacy_mode=None,
                storage_scope="inspection_folder",
                is_active=True,
            )
        )
        session.commit()
        summary = verify_default_template_metadata(session)
        assert summary.canonical_template_bindings == len(_canonical_payload()["template_bindings"])
    finally:
        session.close()


def test_malformed_seed_artifact_fails_before_database_mutation(tmp_path: Path, monkeypatch) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text(json.dumps({"template_definitions": [{}], "template_bindings": []}), encoding="utf-8")
    with pytest.raises(TemplateSeedError, match="malformed"):
        load_template_seed_artifact(malformed)

    database_url = f"sqlite:///{(tmp_path / 'cli.db').as_posix()}"
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(seed_runtime, "phase_artifact_path", lambda *_: malformed)
    with pytest.raises(Exception):
        bootstrap_template_metadata(database_url=database_url)
    with Session(engine) as session:
        assert session.scalars(select(TemplateDefinition)).all() == []


def test_bootstrap_cli_dry_run_rolls_back(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'dry-run.db').as_posix()}"
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    bootstrap_template_metadata(database_url=database_url, dry_run=True)
    with Session(engine) as session:
        assert session.scalars(select(TemplateDefinition)).all() == []


def test_bootstrap_tool_rolls_back_when_seed_fails_after_a_staged_definition(tmp_path: Path, monkeypatch) -> None:
    payload = _canonical_payload()
    broken = {
        "template_definitions": [dict(payload["template_definitions"][0]), dict(payload["template_definitions"][1])],
        "template_bindings": [],
    }
    broken["template_definitions"][1]["variant_type"] = "not_a_variant"
    artifact = tmp_path / "broken-after-stage.json"
    artifact.write_text(json.dumps(broken), encoding="utf-8")
    monkeypatch.setattr(seed_runtime, "phase_artifact_path", lambda *_: artifact)
    monkeypatch.setattr(template_metadata_bootstrap, "phase_artifact_path", lambda *_: artifact)

    database_url = f"sqlite:///{(tmp_path / 'rollback.db').as_posix()}"
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    with pytest.raises(Exception):
        bootstrap_template_metadata(database_url=database_url)
    with Session(engine) as session:
        assert session.scalars(select(TemplateDefinition)).all() == []
