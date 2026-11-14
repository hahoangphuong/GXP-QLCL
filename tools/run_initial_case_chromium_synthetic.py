#!/usr/bin/env python3
"""Chromium-only synthetic UI evidence: no backend, OIDC or protected database.

Starts from a Vite-served, dev-only fixture using the production React
components and browser router. Every /api/* request is intercepted and
answered with explicit in-memory canonical objects. A request that is not
listed fails closed. This is NOT an authenticated end-to-end UAT test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

SITE = "synthetic-site-uuid"
COMPANY = "synthetic-company-uuid"
LINE = "synthetic-physical-line-uuid"
BASE = "http://127.0.0.1:4173"
FIXTURE = BASE + "/initial-case-browser-fixture.html"


def run_scenario(browser, *, line: bool, uncertain: bool = False, foreign: bool = False):
    ctx = browser.new_context(viewport={"width": 390 if line else 1280, "height": 700 if line else 900})
    page = ctx.new_page()
    payloads: list[dict] = []
    requests: list[str] = []
    api_errors: list[str] = []
    readback_attempts = 0

    def route_api(route):
        nonlocal readback_attempts
        req = route.request
        parsed = urlsplit(req.url)
        path = parsed.path.removeprefix("/api")
        query = parse_qs(parsed.query)
        requests.append(req.method + " " + path)
        if req.headers.get("x-auth-user") != "synthetic.operator":
            api_errors.append("No X-Auth-User on " + path)
            route.fulfill(status=403, json={"detail": "Missing synthetic auth"})
            return

        def okay(value, status=200):
            route.fulfill(status=status, json=value)

        if req.method == "GET" and path == f"/sites/{SITE}":
            return okay({"id": SITE, "site_name": "Synthetic Site", "company_id": COMPANY})
        if req.method == "GET" and path == f"/companies/{COMPANY}":
            return okay({"id": COMPANY, "legal_name": "Synthetic Company", "is_inactive": False})
        if req.method == "GET" and path == f"/sites/{SITE}/production-lines":
            return okay([{"id": LINE, "site_id": SITE, "code": "L1",
                          "effective_from": "2026-01-01", "effective_to": None, "row_version": 1}])
        if req.method == "GET" and path == f"/sites/{SITE}/workspace":
            selected = query.get("production_line_id", [None])[0]
            gxp = query.get("gxp_type", [None])[0]
            if gxp != "GMP" or selected not in (None, LINE):
                api_errors.append("Incorrect readiness context: " + str(query))
                return okay({"detail": "wrong context"}, 409)
            # GxP can be selected before the operator selects a physical line.
            # This is a valid intermediate GET, not admission authority for
            # the intended physical-line Case. Only its exact UUID gets ready.
            status = "available" if selected == (LINE if line else None) else "unavailable"
            return okay({"summary": {"site_id": SITE, "selected_gxp_type": "GMP",
                                     "selected_production_line_id": selected},
                         "action_readiness": [{"action_key": "create_initial_case",
                                               "label": "Hồ sơ mới",
                                               "readiness_status": status,
                                               "detail": "Synthetic canonical ready" if status == "available" else "Select physical UUID",
                                               "required_permissions": ["case.edit"]}]})
        if req.method == "POST" and path == f"/sites/{SITE}/inspection-cases/initial":
            p = req.post_data_json
            payloads.append(p)
            assert p["gxp_type"] == "GMP" and p["inspection_type"] == "Mới"
            assert p["production_line_id"] == (LINE if line else None)
            assert p["applicable_standard"] == "WHO-GMP"
            assert p["case_id"] and p["reason"] == "Synthetic Case creation"
            if len(payloads) > 1:
                api_errors.append("DUPLICATE POST for one intent")
                return okay({"detail": "Duplicate POST"}, 409)
            return okay({"detail": "unknown POST outcome"}, 503) if uncertain else okay({"case_id": p["case_id"]}, 201)
        if req.method == "GET" and payloads and path == f"/cases/{payloads[0]['case_id']}":
            readback_attempts += 1
            if uncertain and readback_attempts == 1:
                return okay({"detail": "synthetic transient GET error"}, 503)
            p = payloads[0]
            return okay({"id": p["case_id"], "site_id": SITE, "gxp_type": "GMP",
                         "production_line_id": p["production_line_id"],
                         "inspection_type": "Mới", "applicable_standard": "WHO-GMP",
                         "state": "draft", "legacy_inspection_id": None,
                         "legacy_inspection_code": None})
        if req.method == "GET" and payloads and path == f"/cases/{payloads[0]['case_id']}/workspace":
            p = payloads[0]
            return okay({"case_summary": {
                "id": "foreign-case" if foreign else p["case_id"],
                "site_id": "foreign-site" if foreign else SITE,
                "gxp_type": "GMP", "state": "draft",
                "production_line_id": p["production_line_id"],
                "production_line_code": "L1" if p["production_line_id"] else None,
                "production_line_identity_state": "canonical" if p["production_line_id"] else "facility_wide",
            }})
        api_errors.append("UNEXPECTED " + req.method + " " + path)
        return okay({"detail": "Unexpected synthetic API call"}, 501)

    page.route("**/api/**", route_api)
    scenario = f"{'physical' if line else 'facility'}{'-uncertain' if uncertain else ''}{'-foreign' if foreign else ''}"
    try:
        page.goto(FIXTURE, wait_until="domcontentloaded")
        page.get_by_label("Loại GxP cho hồ sơ mới").select_option("GMP")
        if line:
            page.get_by_label("ProductionLine UUID").select_option(LINE)
        page.get_by_label("Loại kiểm tra hồ sơ đầu tiên").fill("Mới")
        page.get_by_label("Tiêu chuẩn áp dụng").fill("WHO-GMP")
        page.get_by_label("Lý do tạo hồ sơ đầu tiên").fill("Synthetic Case creation")
        page.get_by_label("Xác nhận chỉ tạo Case Draft").check()
        submit = page.get_by_role("button", name="Tạo hồ sơ Draft")
        submit.wait_for(state="visible")
        page.wait_for_function(
            "() => { const b = Array.from(document.querySelectorAll('button')).find(x => x.textContent?.trim() === 'Tạo hồ sơ Draft'); return !!b && !b.disabled; }"
        )
        submit.click()
        if uncertain:
            page.get_by_role("button", name="Đọc lại Case canonical").wait_for()
            assert page.get_by_role("button", name="Đã khóa intent").is_disabled()
            assert len(payloads) == 1
            page.get_by_role("button", name="Đọc lại Case canonical").click()
        page.get_by_text("Case nháp canonical đã xác minh:", exact=False).wait_for()
        assert len(payloads) == 1, f"Expected one POST, got {len(payloads)}"
        assert not any(x.endswith("/workspace") and x.startswith("GET /cases/") for x in requests), "Premature workspace redirect"
        page.get_by_role("button", name="Mở Case workspace").click()
        if foreign:
            page.get_by_role("alert").get_by_text("Hồ sơ trả về không khớp định danh", exact=False).wait_for()
            assert page.get_by_test_id("workspace-destination").count() == 0
        else:
            dest = page.get_by_test_id("workspace-destination")
            dest.wait_for()
            actual = urlsplit(BASE + dest.inner_text())
            q = parse_qs(actual.query)
            assert actual.path == "/search" and q.get("history_id") == [payloads[0]["case_id"]]
            assert q.get("site_id") == [SITE] and q.get("gxp_type") == ["GMP"]
            assert q.get("production_line_id", [None])[0] == (LINE if line else None)
            assert q.get("line_code", [None])[0] == ("L1" if line else None)
        assert len(payloads) == 1 and not api_errors, api_errors
        print(json.dumps({"scenario": scenario, "status": "PASS", "posts": len(payloads),
                          "canonical_reads": readback_attempts, "requests": requests}, ensure_ascii=False))
    except BaseException:
        artifact = Path("browser-evidence")
        artifact.mkdir(exist_ok=True)
        page.screenshot(path=str(artifact / f"{scenario}.png"), full_page=True)
        (artifact / f"{scenario}.json").write_text(json.dumps(
            {"requests": requests, "post_payloads": payloads, "api_errors": api_errors}, indent=2
        ), encoding="utf-8")
        raise
    finally:
        ctx.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE)
    args = parser.parse_args()
    if args.base_url.rstrip("/") != BASE:
        raise SystemExit("This isolated smoke only accepts localhost Vite port 4173")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            run_scenario(browser, line=False)
            run_scenario(browser, line=True)
            run_scenario(browser, line=True, uncertain=True)
            run_scenario(browser, line=False, foreign=True)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
