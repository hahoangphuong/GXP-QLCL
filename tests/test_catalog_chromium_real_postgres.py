"""Chromium + real FastAPI + isolated migrated PostgreSQL catalog journey.

No Playwright API mocking or browser route interception. Vite forwards /api
to the real localhost FastAPI application. Only the development header-stub
identity is used. Shared pg_engine refuses non-disposable remote databases.
This gate is opt-in; CI installs Chromium and turns it on explicitly.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import AuditEvent, Case, Certificate, Company, ProductionLine, Site
from test_canonical_workflow_postgres import pg_engine


VITE_URL = "http://127.0.0.1:4173/catalog-journey-browser-fixture.html"
BACKEND_PORT = 8000


def _port_in_use(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture
def live_backend(pg_engine):
    if os.environ.get("GXP_CATALOG_REAL_BROWSER") != "1":
        pytest.skip("explicit real-browser disposable PostgreSQL gate required")
    if _port_in_use(BACKEND_PORT):
        pytest.fail("Refusing to use or terminate unknown process on localhost:8000")
    env = {
        **os.environ,
        "DATABASE_URL": pg_engine.url.render_as_string(hide_password=False),
        "APP_ENV": "development",
        "AUTH_MODE": "header_stub",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app",
         "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(100):
            if process.poll() is not None:
                stderr = process.stderr.read().decode(errors="replace")[-4000:]
                pytest.fail("FastAPI exited during startup: " + stderr)
            try:
                with urlopen("http://127.0.0.1:8000/openapi.json", timeout=0.4) as response:
                    if response.status == 200:
                        break
            except (OSError, HTTPError):
                time.sleep(0.15)
        else:
            pytest.fail("FastAPI readiness timeout")
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        if process.stderr:
            process.stderr.close()


def _rows(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_chromium_real_http_first_case_full_operator_journey(pg_engine, live_backend):
    # Playwright is installed only by the path-scoped browser job. Import at
    # execution time so normal backend pytest shards can still collect this file.
    from playwright.sync_api import sync_playwright

    with Session(pg_engine) as db:
        before = {m: _rows(db, m) for m in (Company, Site, ProductionLine, Case, Certificate, AuditEvent)}
    writes = {}
    requested = []
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 700})
        page = context.new_page()
        page.set_default_timeout(15000)

        def record_request(request):
            route = urlsplit(request.url).path
            if not route.startswith("/api/"):
                return
            requested.append(request.method + " " + route)
            if request.method == "POST":
                if route == "/api/companies":
                    kind = "company"
                elif route.endswith("/sites"):
                    kind = "site"
                elif route.endswith("/production-lines"):
                    kind = "line"
                elif route.endswith("/inspection-cases/initial"):
                    kind = "case"
                else:
                    errors.append("Unexpected POST " + route)
                    return
                if kind in writes:
                    errors.append("Repeated POST for " + kind)
                writes[kind] = request.post_data_json

        page.on("request", record_request)
        try:
            page.goto(VITE_URL, wait_until="domcontentloaded")
            page.get_by_label("Tên pháp nhân").fill("Synthetic Live HTTP Company")
            page.get_by_label("Địa chỉ pháp lý").fill("Synthetic legal address")
            page.get_by_role("button", name="Tạo Công ty").click()
            page.get_by_text("Đã xác minh Công ty canonical", exact=False).wait_for()

            page.get_by_label("Tên cơ sở", exact=True).fill("Synthetic Live HTTP Site")
            page.get_by_label("Địa chỉ cơ sở", exact=True).fill("Synthetic site address")
            page.get_by_role("button", name="Tạo Cơ sở").click()
            page.get_by_role("heading", name="Dây chuyền sản xuất vật lý mới").wait_for()

            page.get_by_label("Mã dây chuyền vật lý").fill("L1")
            page.get_by_label("Hiệu lực từ").fill("2026-11-14")
            page.get_by_label("Bằng chứng định danh vật lý").fill("SYNTHETIC-LIVE-PHYSICAL-EVIDENCE")
            page.get_by_label("Lý do khai báo dây chuyền").fill("Synthetic physical evidence")
            page.get_by_label("Xác nhận định danh vật lý độc lập").check()
            page.get_by_role("button", name="Tạo dây chuyền vật lý").click()
            page.get_by_text("Đã xác minh dây chuyền UUID", exact=False).wait_for()
            page.get_by_role("button", name="Đóng").click()

            page.get_by_role("heading", name="Hồ sơ kiểm tra đầu tiên").wait_for()
            page.get_by_label("Loại GxP cho hồ sơ mới").select_option("GMP")
            page.get_by_label("ProductionLine UUID").select_option(writes["line"]["production_line_id"])
            page.get_by_label("Loại kiểm tra hồ sơ đầu tiên").fill("Mới")
            page.get_by_label("Tiêu chuẩn áp dụng").fill("WHO-GMP")
            page.get_by_label("Lý do tạo hồ sơ đầu tiên").fill("Synthetic live HTTP first Case")
            page.get_by_label("Xác nhận chỉ tạo Case Draft").check()
            page.get_by_role("button", name="Tạo hồ sơ Draft").click()
            page.get_by_text("Case nháp canonical đã xác minh:", exact=False).wait_for()

            assert len(writes) == 4 and not errors, (writes, errors)
            ids = (
                writes["company"]["company_id"],
                writes["site"]["site_id"],
                writes["line"]["production_line_id"],
                writes["case"]["case_id"],
            )
            assert len(set(ids)) == 4
            assert writes["case"]["production_line_id"] == ids[2]
            assert "GET /api/cases/" + ids[3] in requested
            assert not any("/workspace" in item for item in requested), (
                "Workspace opened before explicit operator action", requested
            )
            page.get_by_role("button", name="Mở Case workspace").click()
            destination = page.get_by_test_id("workspace-destination")
            destination.wait_for()
            url = urlsplit("http://127.0.0.1" + destination.inner_text())
            query = parse_qs(url.query)
            assert url.path == "/search"
            assert query["history_id"] == [ids[3]]
            assert query["site_id"] == [ids[1]]
            assert query["production_line_id"] == [ids[2]]
            assert query["gxp_type"] == ["GMP"]
            assert query["line_code"] == ["L1"]
            assert "GET /api/cases/" + ids[3] + "/workspace" in requested
        except BaseException:
            out = Path("browser-evidence")
            out.mkdir(exist_ok=True)
            page.screenshot(path=str(out / "catalog-real-http-postgres.png"), full_page=True)
            (out / "catalog-real-http-postgres.json").write_text(
                json.dumps({"requests": requested, "writes": writes, "errors": errors}, indent=2),
                encoding="utf-8",
            )
            raise
        finally:
            context.close()
            browser.close()

    with Session(pg_engine) as db:
        company = db.get(Company, ids[0])
        site = db.get(Site, ids[1])
        line = db.get(ProductionLine, ids[2])
        case = db.get(Case, ids[3])
        assert company is not None
        assert site is not None and site.company_id == company.id
        assert line is not None and line.site_id == site.id and line.code == "L1"
        assert case is not None and case.site_id == site.id
        assert case.production_line_id == line.id and case.gxp_type == "GMP"
        assert case.row_version == 1 and case.legacy_inspection_id is None
        for model in (Company, Site, ProductionLine, Case):
            assert _rows(db, model) == before[model] + 1
        assert _rows(db, Certificate) == before[Certificate]
        assert _rows(db, AuditEvent) == before[AuditEvent] + 4
