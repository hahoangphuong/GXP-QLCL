from __future__ import annotations

import argparse
import json
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.session import session_scope
from backend.app.storage import StorageBindingLookupService, create_storage_service_from_env


DEFAULT_INPUT_PATH = ROOT / "artifacts" / "phase4" / "probe_triplets.template.json"
DEFAULT_DKKD_INPUT_PATH = ROOT / "artifacts" / "phase4" / "probe_dkkd_sites.template.json"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase4" / "nonprod_probe"


def load_probe_inputs(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Probe input file must contain a JSON array.")
    return payload


def run_inspection_probes(
    *,
    database_url: str,
    probe_inputs: list[dict[str, Any]],
    storage_env: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    storage = create_storage_service_from_env(storage_env)
    lookup = StorageBindingLookupService(storage)
    results: list[dict[str, Any]] = []

    with session_scope(database_url) as session:
        for item in probe_inputs:
            result = lookup.get_inspection_folder(
                session,
                case_id=item.get("case_id"),
                year=int(item["year"]),
                site_legacy_id=int(item["site_legacy_id"]),
                inspection_legacy_code=str(item["inspection_legacy_code"]),
            )
            session.flush()
            results.append(
                {
                    "label": item.get("label"),
                    "case_id": item.get("case_id"),
                    "year": int(item["year"]),
                    "site_legacy_id": int(item["site_legacy_id"]),
                    "inspection_legacy_code": str(item["inspection_legacy_code"]),
                    "expected_status": item.get("expected_status"),
                    "status": result.resolution.status.value,
                    "source": result.source,
                    "relative_path": result.resolution.relative_path,
                    "candidate_count": result.resolution.candidate_count,
                    "detail": result.resolution.detail,
                    "binding_relative_path": None if result.binding is None else result.binding.relative_path,
                    "storage_class": storage.config.storage_class,
                }
            )
    return results


def run_dkkd_probes(
    *,
    database_url: str,
    probe_inputs: list[dict[str, Any]],
    storage_env: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    storage = create_storage_service_from_env(storage_env)
    lookup = StorageBindingLookupService(storage)
    results: list[dict[str, Any]] = []

    with session_scope(database_url) as session:
        for item in probe_inputs:
            result = lookup.get_dkkd_folder(
                session,
                case_id=item.get("case_id"),
                site_legacy_id=int(item["site_legacy_id"]),
            )
            session.flush()
            results.append(
                {
                    "label": item.get("label"),
                    "case_id": item.get("case_id"),
                    "site_legacy_id": int(item["site_legacy_id"]),
                    "expected_status": item.get("expected_status"),
                    "status": result.resolution.status.value,
                    "source": result.source,
                    "relative_path": result.resolution.relative_path,
                    "candidate_count": result.resolution.candidate_count,
                    "detail": result.resolution.detail,
                    "storage_class": storage.config.storage_class,
                }
            )
    return results


def run_write_probe(
    *,
    scratch_relative_path: str,
    storage_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    storage = create_storage_service_from_env(storage_env)
    folder = storage.create_folder(scratch_relative_path)
    filename = f"{scratch_relative_path.rstrip('/')}/probe.txt"
    written = storage.write_stream(filename, BytesIO(b"phase4-nonprod-probe"))
    copied = storage.copy(filename, f"{scratch_relative_path.rstrip('/')}/probe-copy.txt")
    moved = storage.move(
        f"{scratch_relative_path.rstrip('/')}/probe-copy.txt",
        f"{scratch_relative_path.rstrip('/')}/archive/probe-copy.txt",
    )
    renamed = storage.rename(f"{scratch_relative_path.rstrip('/')}/archive/probe-copy.txt", "probe-final.txt")
    checksum = storage.checksum(filename)
    return {
        "scratch_relative_path": scratch_relative_path,
        "folder_relative_path": folder.relative_path,
        "written_relative_path": written.relative_path,
        "copied_relative_path": copied.relative_path,
        "moved_relative_path": moved.relative_path,
        "renamed_relative_path": renamed.relative_path,
        "checksum": checksum,
    }


def build_markdown(
    *,
    inspection_results: list[dict[str, Any]],
    dkkd_results: list[dict[str, Any]],
    write_probe: dict[str, Any] | None,
    input_path: Path,
    dkkd_input_path: Path | None,
) -> str:
    lines = [
        "# Phase 4 Non-Production Storage Probe",
        "",
        f"- Probe input: `{input_path}`",
        f"- Inspection triplets checked: `{len(inspection_results)}`",
        f"- DDKD site probes checked: `{len(dkkd_results)}`",
        "",
        "## Inspection Results",
        "",
        "| Label | Year | Site ID | Inspection Code | Status | Source | Relative Path |",
        "|---|---:|---:|---|---|---|---|",
    ]
    for row in inspection_results:
        lines.append(
            f"| {row.get('label') or ''} | `{row['year']}` | `{row['site_legacy_id']}` | "
            f"`{row['inspection_legacy_code']}` | `{row['status']}` | `{row['source']}` | "
            f"`{row['relative_path'] or ''}` |"
        )
    lines.append("")
    if dkkd_results:
        lines.extend(
            [
                "## DDKD Results",
                "",
                f"- DDKD probe input: `{dkkd_input_path}`",
                "",
                "| Label | Site ID | Status | Source | Relative Path |",
                "|---|---:|---|---|---|",
            ]
        )
        for row in dkkd_results:
            lines.append(
                f"| {row.get('label') or ''} | `{row['site_legacy_id']}` | `{row['status']}` | "
                f"`{row['source']}` | `{row['relative_path'] or ''}` |"
            )
        lines.append("")
    if write_probe is not None:
        lines.extend(
            [
                "## Write Probe",
                "",
                f"- Scratch path: `{write_probe['scratch_relative_path']}`",
                f"- Written file: `{write_probe['written_relative_path']}`",
                f"- Renamed file: `{write_probe['renamed_relative_path']}`",
                f"- Checksum: `{write_probe['checksum']}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe non-production storage behavior for Phase 4 validation.")
    parser.add_argument("--database-url", default="sqlite:///artifacts/phase2/staging_readonly.db")
    parser.add_argument("--input", default=str(DEFAULT_INPUT_PATH))
    parser.add_argument("--dkkd-input", default=str(DEFAULT_DKKD_INPUT_PATH))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--scratch-relative-path", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dkkd_input_path = Path(args.dkkd_input)

    inspection_results = run_inspection_probes(
        database_url=args.database_url,
        probe_inputs=load_probe_inputs(input_path),
    )
    dkkd_results = run_dkkd_probes(
        database_url=args.database_url,
        probe_inputs=load_probe_inputs(dkkd_input_path),
    )
    write_probe = None
    if args.scratch_relative_path:
        write_probe = run_write_probe(scratch_relative_path=args.scratch_relative_path)

    summary = {
        "database_url": args.database_url,
        "input_path": str(input_path),
        "dkkd_input_path": str(dkkd_input_path),
        "inspection_results": inspection_results,
        "dkkd_results": dkkd_results,
        "write_probe": write_probe,
    }
    json_path = out_dir / "probe_report.json"
    md_path = out_dir / "probe_report.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        build_markdown(
            inspection_results=inspection_results,
            dkkd_results=dkkd_results,
            write_probe=write_probe,
            input_path=input_path,
            dkkd_input_path=dkkd_input_path,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
