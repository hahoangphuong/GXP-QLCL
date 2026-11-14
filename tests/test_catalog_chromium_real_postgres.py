"""Chromium + real FastAPI + isolated migrated PostgreSQL catalog journey.

Normal requests reach real FastAPI via Vite /api. Negative scenarios only
fault-inject browser-visible responses *after* real POST commits, and the
first exact UUID GET response; no business API or DB operation is mocked. Only the development header-stub
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


@pytest.mark.parametrize("ambiguous_stage", (None, "company", "site", "line", "case"),
                         ids=("normal", "ambiguous-company", "ambiguous-site", "ambiguous-line", "ambiguous-case"))
def test_chromium_real_http_first_case_full_operator_journey(pg_engine, live_backend, ambiguous_stage):
    # Playwright is installed only by the path-scoped browser job. Import at
    # execution time so normal backend pytest shards can still collect this file.
    from playwright.sync_api import sync_playwright

    with Session(pg_engine) as db:
        before = {m: _rows(db, m) for m in (Company, Site, ProductionLine, Case, Certificate, AuditEvent)}
    writes = {}
    requested = []
    errors = []
    injected = {"post": 0, "get": 0}
    verified_readbacks = []
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

        def fault_after_real_commit(route):
            """Forward the mutation to real FastAPI, then mask its response."""
            req = route.request
            path = urlsplit(req.url).path
            stage_post = {
                "company": "/api/companies",
                "site": "/api/companies/" + writes.get("company", {}).get("company_id", "") + "/sites",
                "line": "/api/sites/" + writes.get("site", {}).get("site_id", "") + "/production-lines",
                "case": "/api/sites/" + writes.get("site", {}).get("site_id", "") + "/inspection-cases/initial",
            }
            ids_by_stage = {
                "company": writes.get("company", {}).get("company_id"),
                "site": writes.get("site", {}).get("site_id"),
                "line": writes.get("line", {}).get("production_line_id"),
                "case": writes.get("case", {}).get("case_id"),
            }
            stage_get = {"company": "/api/companies/", "site": "/api/sites/",
                         "line": "/api/production-lines/", "case": "/api/cases/"}
            if ambiguous_stage and req.method == "POST" and path == stage_post[ambiguous_stage]:
                assert injected["post"] == 0, "Duplicate POST is forbidden"
                response = route.fetch()
                assert response.status == 200, (path, response.status, response.text())
                injected["post"] += 1
                route.fulfill(status=503, json={"detail": "Synthetic lost response after actual commit"})
                return
            if (ambiguous_stage and req.method == "GET"
                    and path == stage_get[ambiguous_stage] + str(ids_by_stage[ambiguous_stage])):
                verified_readbacks.append(path)
                if injected["get"] == 0:
                    injected["get"] += 1
                    route.fulfill(status=503, json={"detail": "Synthetic first canonical GET failure"})
                    return
            route.continue_()

        if ambiguous_stage:
            # Only the transport response is fault-injected. DB persistence is real.
            page.route("**/api/**", fault_after_real_commit)
        try:
            page.goto(VITE_URL, wait_until="domcontentloaded")
            page.get_by_label("Tên pháp nhân").fill("Synthetic Live HTTP Company")
            page.get_by_label("Địa chỉ pháp lý").fill("Synthetic legal address")
            page.get_by_role("button", name="Tạo Công ty").click()
            if ambiguous_stage == "company":
                page.get_by_text("Chưa xác minh:", exact=False).wait_for()
                page.get_by_role("button", name="Đọc lại canonical").click()
            page.get_by_text("Đã xác minh Công ty canonical", exact=False).wait_for()

            page.get_by_label("Tên cơ sở", exact=True).fill("Synthetic Live HTTP Site")
            page.get_by_label("Địa chỉ cơ sở", exact=True).fill("Synthetic site address")
            page.get_by_role("button", name="Tạo Cơ sở").click()
            if ambiguous_stage == "site":
                page.get_by_text("Chưa xác minh:", exact=False).wait_for()
                page.get_by_role("button", name="Đọc lại canonical").click()
            page.get_by_role("heading", name="Dây chuyền sản xuất vật lý mới").wait_for()

            page.get_by_label("Mã dây chuyền vật lý").fill("L1")
            page.get_by_label("Hiệu lực từ").fill("2026-11-14")
            page.get_by_label("Bằng chứng định danh vật lý").fill("SYNTHETIC-LIVE-PHYSICAL-EVIDENCE")
            page.get_by_label("Lý do khai báo dây chuyền").fill("Synthetic physical evidence")
            page.get_by_label("Xác nhận định danh vật lý độc lập").check()
            page.get_by_role("button", name="Tạo dây chuyền vật lý").click()
            if ambiguous_stage == "line":
                page.get_by_text("Chưa xác minh được kết quả:", exact=False).wait_for()
                page.get_by_role("button", name="Đọc lại canonical").click()
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
            if ambiguous_stage == "case":
                page.get_by_text("Chưa xác minh:", exact=False).wait_for()
                page.get_by_role("button", name="Đọc lại Case canonical").click()
            page.get_by_text("Case nháp canonical đã xác minh:", exact=False).wait_for()

            assert len(writes) == 4 and not errors, (writes, errors)
            if ambiguous_stage:
                assert injected == {"post": 1, "get": 1}, injected
                assert len(verified_readbacks) >= 2, verified_readbacks
            else:
                assert injected == {"post": 0, "get": 0}, injected
            ids = (
                writes["company"]["company_id"],
                writes["site"]["site_id"],
                writes["line"]["production_line_id"],
                writes["case"]["case_id"],
            )
            assert len(set(ids)) == 4
            assert writes["case"]["production_line_id"] == ids[2]
            assert "GET /api/cases/" + ids[3] in requested
            assert "GET /api/cases/" + ids[3] + "/workspace" not in requested, (
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
            page.screenshot(path=str(out / ("catalog-real-http-postgres-" + (ambiguous_stage or "normal") + ".png")), full_page=True)
            (out / ("catalog-real-http-postgres-" + (ambiguous_stage or "normal") + ".json")).write_text(
                json.dumps({"scenario": ambiguous_stage or "normal", "requests": requested, "writes": writes, "errors": errors, "faults": injected, "readbacks": verified_readbacks}, indent=2),
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


def test_company_committed_lost_response_survives_browser_reload_without_repost(pg_engine, live_backend):
    """The original exact-UUID intent survives a page reload in the same tab."""
    from playwright.sync_api import sync_playwright

    with Session(pg_engine) as db:
        before = {m: _rows(db, m) for m in (Company, Site, ProductionLine, Case, Certificate, AuditEvent)}
    writes = []
    fault = {"post": 0, "get": 0}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 700})
        page = context.new_page()
        page.set_default_timeout(15000)

        def record(request):
            if request.method == "POST" and urlsplit(request.url).path == "/api/companies":
                writes.append(request.post_data_json)

        def fault_after_commit(route):
            req = route.request
            path = urlsplit(req.url).path
            if req.method == "POST" and path == "/api/companies":
                assert fault["post"] == 0, "A reload must not replay POST"
                response = route.fetch()
                assert response.status == 200
                fault["post"] += 1
                route.fulfill(status=503, json={"detail": "response lost after real commit"})
                return
            if (req.method == "GET" and writes
                    and path == "/api/companies/" + writes[0]["company_id"]
                    and fault["get"] == 0):
                fault["get"] += 1
                route.fulfill(status=503, json={"detail": "first readback failed"})
                return
            route.continue_()

        page.on("request", record)
        page.route("**/api/**", fault_after_commit)
        try:
            page.goto(VITE_URL, wait_until="domcontentloaded")
            page.get_by_label("Tên pháp nhân").fill("Synthetic Reload Recovery Company")
            page.get_by_label("Địa chỉ pháp lý").fill("Synthetic tab-scoped address")
            page.get_by_role("button", name="Tạo Công ty").click()
            page.get_by_text("Chưa xác minh:", exact=False).wait_for()
            assert fault == {"post": 1, "get": 1}
            assert len(writes) == 1
            original_uuid = writes[0]["company_id"]

            page.reload(wait_until="domcontentloaded")
            page.get_by_text("Chưa xác minh:", exact=False).wait_for()
            assert page.get_by_role("button", name="Đang xác minh...").is_disabled()
            assert len(writes) == 1, "Reload reissued a Company POST"
            # The journal is not sufficient to approve the mutation: the
            # operator must perform a fresh authorized exact-UUID GET.
            page.get_by_role("button", name="Đọc lại canonical").click()
            page.get_by_text("Đã xác minh Công ty canonical", exact=False).wait_for()
            assert len(writes) == 1
            assert writes[0]["company_id"] == original_uuid
            assert fault == {"post": 1, "get": 1}
        except BaseException:
            evidence = Path("browser-evidence")
            evidence.mkdir(exist_ok=True)
            page.screenshot(path=str(evidence / "catalog-reload-company.png"), full_page=True)
            (evidence / "catalog-reload-company.json").write_text(
                json.dumps({"writes": writes, "faults": fault}, indent=2),
                encoding="utf-8",
            )
            raise
        finally:
            context.close()
            browser.close()

    with Session(pg_engine) as db:
        company = db.get(Company, original_uuid)
        assert company is not None
        assert company.legal_name == "Synthetic Reload Recovery Company"
        assert _rows(db, Company) == before[Company] + 1
        for model in (Site, ProductionLine, Case, Certificate):
            assert _rows(db, model) == before[model]
        assert _rows(db, AuditEvent) == before[AuditEvent] + 1


@pytest.mark.parametrize("journal_failure", ("corrupt", "unwritable"))
def test_corrupt_or_unwritable_catalog_journal_blocks_post(pg_engine, live_backend, journal_failure):
    """Untrusted journal may never silently become a fresh owner after reload."""
    from playwright.sync_api import sync_playwright

    with Session(pg_engine) as db:
        before = {m: _rows(db, m) for m in (Company, Site, ProductionLine, Case, Certificate, AuditEvent)}
    posts = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(15000)
        if journal_failure == "corrupt":
            page.add_init_script("""
              sessionStorage.setItem(
                'gxp-catalog-recovery-v1:synthetic-catalog-company-site',
                '{ invalid-json-and-unresolved-post'
              );
            """)
        else:
            page.add_init_script("""
              const original = Storage.prototype.setItem;
              Storage.prototype.setItem = function(key, value) {
                if (String(key).startsWith('gxp-catalog-recovery-v1:')) {
                  throw new DOMException('Simulated quota limit', 'QuotaExceededError');
                }
                return original.call(this, key, value);
              };
            """)
        page.on("request", lambda req: posts.append(req.url)
                if req.method == "POST" and urlsplit(req.url).path.startswith("/api/") else None)
        try:
            page.goto(VITE_URL, wait_until="domcontentloaded")
            if journal_failure == "unwritable":
                page.get_by_label("Tên pháp nhân").fill("Must not commit")
                page.get_by_label("Địa chỉ pháp lý").fill("No durable journal")
                page.get_by_role("button", name="Tạo Công ty").click()
            page.get_by_text("recovery journal", exact=False).wait_for()
            assert not posts, posts
            assert page.get_by_role("button", name="Tạo Công ty").is_disabled()
        except BaseException:
            out = Path("browser-evidence")
            out.mkdir(exist_ok=True)
            page.screenshot(path=str(out / ("journal-" + journal_failure + ".png")))
            raise
        finally:
            context.close()
            browser.close()
    with Session(pg_engine) as db:
        assert all(_rows(db, model) == before[model] for model in before)
