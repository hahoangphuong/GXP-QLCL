from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_APP = ROOT / "backend" / "app"
LEGACY_RENDERER = "render_evaluation_scope_summary"
LEGACY_OWNER = BACKEND_APP / "domain" / "evaluation_scope.py"


def _legacy_renderer_references(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    references: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == LEGACY_RENDERER:
                    references.append(f"import:{node.lineno}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == LEGACY_RENDERER:
                references.append(f"call:{node.lineno}")
            elif isinstance(func, ast.Attribute) and func.attr == LEGACY_RENDERER:
                references.append(f"call:{node.lineno}")
    return references


def test_production_code_cannot_reintroduce_legacy_evaluation_scope_renderer():
    offenders: dict[str, list[str]] = {}
    for path in sorted(BACKEND_APP.rglob("*.py")):
        if path == LEGACY_OWNER:
            continue
        references = _legacy_renderer_references(path)
        if references:
            offenders[str(path.relative_to(ROOT))] = references

    assert offenders == {}, (
        "The old canonical evaluation-scope renderer is retired from production "
        f"ownership; use compile_vba_readable_scope instead. Offenders: {offenders}"
    )


def test_catalog_owns_structured_summary_through_vba_renderer_only():
    catalog = BACKEND_APP / "services" / "catalog.py"
    tree = ast.parse(catalog.read_text(encoding="utf-8"), filename=str(catalog))

    imported_from_vba_owner = False
    legacy_imported = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names = {alias.name for alias in node.names}
            if (
                node.module == "backend.app.domain.evaluation_scope_vba_renderer"
                and "compile_vba_readable_scope" in names
            ):
                imported_from_vba_owner = True
            if LEGACY_RENDERER in names:
                legacy_imported = True

    assert imported_from_vba_owner is True
    assert legacy_imported is False
