from __future__ import annotations

import json
import shutil
from pathlib import Path
from time import sleep
from uuid import uuid4

import pythoncom
import win32com.client


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "artifacts" / "phase6"
JSON_OUT = OUT_DIR / "word_desktop_harness.json"
MD_OUT = OUT_DIR / "word_desktop_harness.md"


def _quit_word(app) -> None:
    try:
        app.Quit()
    except Exception:
        pass


def run_harness() -> dict[str, object]:
    pythoncom.CoInitialize()
    smoke_root = OUT_DIR / "_word_desktop_harness" / uuid4().hex
    smoke_root.mkdir(parents=True, exist_ok=True)
    doc_path = smoke_root / "phase6-word-harness.docx"

    app_one = None
    doc_one = None
    doc_verify = None
    try:
        app_one = win32com.client.DispatchEx("Word.Application")
        app_one.Visible = False
        app_one.DisplayAlerts = 0
        created = app_one.Documents.Add()
        created.Content.Text = "phase6-initial"
        created.SaveAs(str(doc_path), FileFormat=16)
        created.Close(False)

        doc_one = app_one.Documents.Open(str(doc_path), ReadOnly=False, AddToRecentFiles=False)
        doc_one.Content.Text = "phase6-updated"
        doc_one.Save()
        doc_one.Close(False)
        doc_one = None

        doc_verify = app_one.Documents.Open(str(doc_path), ReadOnly=True, AddToRecentFiles=False)
        verification_text = doc_verify.Content.Text.strip()
        doc_verify.Close(False)
        doc_verify = None

        return {
            "generated_on": "2026-08-14",
            "word_com_available": True,
            "document_created": doc_path.exists(),
            "document_updated_text_verified": verification_text == "phase6-updated",
            "verified_text": verification_text,
            "lock_behavior_observed": False,
            "lock_behavior_note": "Not exercised in the local harness; real SMB/file-lock behavior remains a separate Phase 6 evidence item.",
            "harness_scope": [
                "local filesystem open/edit/save",
                "single Word instance reopen verification",
            ],
        }
    finally:
        for doc in [doc_verify, doc_one]:
            if doc is not None:
                try:
                    doc.Close(False)
                except Exception:
                    pass
        if app_one is not None:
            _quit_word(app_one)
        sleep(1.0)
        if smoke_root.exists():
            try:
                shutil.rmtree(smoke_root)
            except PermissionError:
                pass
        pythoncom.CoUninitialize()


def render_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Phase 6 Word Desktop Harness",
        "",
        f"- Generated on: `{report['generated_on']}`",
        f"- Word COM available: `{report['word_com_available']}`",
        f"- Document created: `{report['document_created']}`",
        f"- Updated text verified: `{report['document_updated_text_verified']}`",
        f"- Verified text: `{report['verified_text']}`",
        f"- Lock behavior observed: `{report['lock_behavior_observed']}`",
        f"- Lock behavior note: `{report['lock_behavior_note']}`",
        "",
        "## Scope",
        "",
    ]
    for item in report["harness_scope"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = run_harness()
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
