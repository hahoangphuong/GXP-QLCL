from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models.phase1 import StorageBinding
from tools.probe_phase4_storage_nonprod import run_dkkd_probes, run_inspection_probes, run_write_probe


def test_run_inspection_probes_reports_binding_backed_resolution(tmp_path: Path):
    inspection_root = tmp_path / "inspection-root"
    inspection_root.mkdir()
    (inspection_root / "2026" / "Folder - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)

    db_path = tmp_path / "probe.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            StorageBinding(
                case_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                year=2026,
                site_legacy_id=103,
                inspection_legacy_code="KT-1376-GMP",
                relative_path="2026/Folder - (ID-103) - (KT-1376-GMP)",
                observed_folder_label="Folder - (ID-103) - (KT-1376-GMP)",
                storage_class="synology_private_share_nonprod",
            )
        )
        session.commit()

    results = run_inspection_probes(
        database_url=str(engine.url),
        probe_inputs=[
            {
                "label": "known",
                "case_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "year": 2026,
                "site_legacy_id": 103,
                "inspection_legacy_code": "KT-1376-GMP",
            }
        ],
        storage_env={
            "STORAGE_INSPECTION_ROOT": str(inspection_root),
            "STORAGE_CLASS": "synology_private_share_nonprod",
        },
    )

    assert len(results) == 1
    assert results[0]["status"] == "resolved"
    assert results[0]["source"] == "binding"


def test_run_write_probe_exercises_scratch_area(tmp_path: Path):
    inspection_root = tmp_path / "inspection-root"
    inspection_root.mkdir()

    result = run_write_probe(
        scratch_relative_path="scratch/probe-001",
        storage_env={"STORAGE_INSPECTION_ROOT": str(inspection_root)},
    )

    assert result["folder_relative_path"] == "scratch/probe-001"
    assert result["written_relative_path"] == "scratch/probe-001/probe.txt"
    assert result["renamed_relative_path"] == "scratch/probe-001/archive/probe-final.txt"


def test_run_dkkd_probes_reports_live_resolution(tmp_path: Path):
    inspection_root = tmp_path / "inspection-root"
    dkkd_root = tmp_path / "dkkd-root"
    inspection_root.mkdir()
    dkkd_root.mkdir()
    (dkkd_root / "US Pharma - 12 Street (91)").mkdir(parents=True)

    db_path = tmp_path / "probe.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)

    results = run_dkkd_probes(
        database_url=str(engine.url),
        probe_inputs=[
            {
                "label": "known-dkkd",
                "case_id": None,
                "site_legacy_id": 91,
            }
        ],
        storage_env={
            "STORAGE_INSPECTION_ROOT": str(inspection_root),
            "STORAGE_DKKD_ROOT": str(dkkd_root),
            "STORAGE_CLASS": "synology_private_share_nonprod",
        },
    )

    assert len(results) == 1
    assert results[0]["status"] == "resolved"
    assert results[0]["source"] == "live_resolution"
    assert results[0]["relative_path"] == "US Pharma - 12 Street (91)"
