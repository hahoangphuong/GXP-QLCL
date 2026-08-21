from pathlib import Path


def test_runtime_startup_paths_do_not_call_create_all():
    runtime_paths = [
        Path("backend/app/main.py"),
        Path("backend/app/config.py"),
        Path("backend/app/api/session.py"),
        Path("backend/app/api/routers/workflow.py"),
        Path("backend/app/api/routers/document.py"),
        Path("backend/app/api/routers/storage.py"),
    ]

    for path in runtime_paths:
        assert "create_all(" not in path.read_text(encoding="utf-8"), f"{path} must not manage runtime schema creation."
