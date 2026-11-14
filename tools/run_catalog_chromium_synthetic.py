#!/usr/bin/env python3
"""Real Chromium, wholly intercepted synthetic HTTP: Company->Site->Line->Case.

This runner starts at the actual Company/Site operator dialog, not a direct
initial Case fixture. No cloud, credentials, actual backend or protected DB.
Unknown/unlisted API calls fail closed.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:4173"
FIXTURE = BASE + "/catalog-journey-browser-fixture.html"


def run(browser, *, uncertain_stage: str | None = None) -> None:
    """One isolated session; inject ambiguous write plus first failed GET."""
    assert uncertain_stage in (None, "company", "site", "line")
    context = browser.new_context(viewport={"width": 390, "height": 700})
    page = context.new_page()
    creates: dict[str, dict] = {}
    readbacks: list[str] = []
    requests: list[str] = []
    errors: list[str] = []
    first_failed_reads: set[str] = set()
    post_attempts: dict[str, int] = {"company": 0, "site": 0, "line": 0, "case": 0}

    def mutation_result(kind, payload, success):
        post_attempts[kind] += 1
        if kind == uncertain_stage:
            # The server committed the create but transport did not report it.
            return ok({"detail": "ambiguous synthetic committed POST"}, 503)
        return ok(success, 201)

    def intercept(route):
        req = route.request
        url = urlsplit(req.url)
        path = url.path.removeprefix("/api")
        method = req.method
        requests.append(method + " " + path)
        if req.headers.get("x-auth-user") != "synthetic.operator":
            errors.append("wrong auth on " + path)
            return route.fulfill(status=403, json={"detail": "synthetic auth rejected"})

        def ok(data, status=200):
            return route.fulfill(status=status, json=data)

        def read(kind, payload, result):
            assert payload is not None, f"GET before persisted {kind}"
            readbacks.append(kind)
            if kind == uncertain_stage and kind not in first_failed_reads:
                first_failed_reads.add(kind)
                return ok({"detail": "temporary canonical readback error"}, 503)
            return ok(result)

        if method == "POST" and path == "/companies":
            payload = req.post_data_json
            if "company" in creates:
                errors.append("duplicate company POST")
                return ok({"detail": "duplicate"}, 409)
            creates["company"] = payload
            return mutation_result("company", payload, {"id": payload["company_id"]})
        company = creates.get("company")
        company_id = company["company_id"] if company else None
        if method == "GET" and company and path == f"/companies/{company_id}":
            return read("company", company, {
                "id": company_id, "legal_name": company["legal_name"],
                "legal_address": company["legal_address"],
                "english_name": company.get("english_name"),
                "short_name": company.get("short_name"),
                "legal_address_en": company.get("legal_address_en"),
                "is_inactive": False,
            })

        if method == "POST" and company and path == f"/companies/{company_id}/sites":
            payload = req.post_data_json
            if "site" in creates:
                errors.append("duplicate site POST")
                return ok({"detail": "duplicate"}, 409)
            creates["site"] = payload
            return mutation_result("site", payload, {"id": payload["site_id"]})
        site = creates.get("site")
        site_id = site["site_id"] if site else None
        if method == "GET" and site and path == f"/sites/{site_id}":
            return read("site", site, {
                "id": site_id, "company_id": company_id,
                "site_name": site["site_name"], "site_address": site["site_address"],
                "site_name_en": site.get("site_name_en"), "site_address_en": site.get("site_address_en"),
                "province_name": site.get("province_name"), "short_name": site.get("short_name"),
            })
        if method == "GET" and site and path == f"/sites/{site_id}/production-lines":
            line = creates.get("line")
            return ok([{
                "id": line["production_line_id"], "site_id": site_id,
                "code": line["code"], "effective_from": line["effective_from"],
                "effective_to": line.get("effective_to"), "row_version": 1,
            }] if line else [])
        if method == "POST" and site and path == f"/sites/{site_id}/production-lines":
            payload = req.post_data_json
            if "line" in creates:
                errors.append("duplicate physical line POST")
                return ok({"detail": "duplicate"}, 409)
            creates["line"] = payload
            return mutation_result("line", payload, {"id": payload["production_line_id"], "audit_event_id": "synthetic-audit"})
        line = creates.get("line")
        line_id = line["production_line_id"] if line else None
        if method == "GET" and line and path == f"/production-lines/{line_id}":
            return read("line", line, {
                "id": line_id, "site_id": site_id, "code": line["code"],
                "effective_from": line["effective_from"],
                "effective_to": line.get("effective_to"), "row_version": 1,
            })

        if method == "GET" and site and path == f"/sites/{site_id}/workspace":
            q = parse_qs(url.query)
            gxp = q.get("gxp_type", [None])[0]
            selected_line = q.get("production_line_id", [None])[0]
            if gxp != "GMP" or selected_line not in (None, line_id):
                errors.append("wrong readiness query " + str(q))
                return ok({"detail": "wrong context"}, 409)
            available = selected_line == line_id and line_id is not None
            return ok({
                "summary": {"site_id": site_id, "selected_gxp_type": gxp,
                            "selected_production_line_id": selected_line},
                "action_readiness": [{
                    "action_key": "create_initial_case", "label": "Hồ sơ mới",
                    "readiness_status": "available" if available else "unavailable",
                    "detail": "Selected physical UUID verified" if available else "Choose canonical physical UUID",
                    "required_permissions": ["case.edit"],
                }],
            })
        if method == "POST" and site and path == f"/sites/{site_id}/inspection-cases/initial":
            payload = req.post_data_json
            if "case" in creates:
                errors.append("duplicate case POST")
                return ok({"detail": "duplicate"}, 409)
            if payload["production_line_id"] != line_id or payload["gxp_type"] != "GMP":
                errors.append("wrong physical line Case owner")
                return ok({"detail": "wrong context"}, 409)
            creates["case"] = payload
            return mutation_result("case", payload, {"case_id": payload["case_id"]})
        case = creates.get("case")
        case_id = case["case_id"] if case else None
        if method == "GET" and case and path == f"/cases/{case_id}":
            return read("case", case, {
                "id": case_id, "site_id": site_id, "gxp_type": "GMP",
                "production_line_id": line_id, "inspection_type": case["inspection_type"],
                "applicable_standard": case["applicable_standard"], "state": "draft",
                "legacy_inspection_id": None, "legacy_inspection_code": None,
            })
        if method == "GET" and case and path == f"/cases/{case_id}/workspace":
            return read("workspace", case, {"case_summary": {
                "id": case_id, "site_id": site_id, "gxp_type": "GMP",
                "state": "draft", "production_line_id": line_id,
                "production_line_code": line["code"],
                "production_line_identity_state": "canonical",
            }})

        errors.append("unexpected " + method + " " + path)
        return ok({"detail": "Unexpected API request"}, 501)

    page.route("**/api/**", intercept)
    try:
        page.goto(FIXTURE, wait_until="domcontentloaded")
        page.get_by_label("Tên pháp nhân").fill("Synthetic New Company")
        page.get_by_label("Địa chỉ pháp lý").fill("Synthetic Legal Address")
        page.get_by_role("button", name="Tạo Công ty").click()
        if uncertain_stage == "company":
            page.get_by_text("Chưa xác minh:", exact=False).wait_for()
            assert page.get_by_role("button", name="Đang xác minh...").is_disabled()
            assert post_attempts["company"] == 1
            page.get_by_role("button", name="Đọc lại canonical").click()
        page.get_by_text("Đã xác minh Công ty canonical", exact=False).wait_for()
        assert "company" in creates and readbacks.count("company") >= 1
        page.get_by_label("Tên cơ sở", exact=True).fill("Synthetic New Site")
        page.get_by_label("Địa chỉ cơ sở", exact=True).fill("Synthetic Site Address")
        page.get_by_role("button", name="Tạo Cơ sở").click()
        if uncertain_stage == "site":
            page.get_by_text("Chưa xác minh:", exact=False).wait_for()
            assert post_attempts["site"] == 1
            page.get_by_role("button", name="Đọc lại canonical").click()
        page.get_by_role("heading", name="Dây chuyền sản xuất vật lý mới").wait_for()
        assert "site" in creates and readbacks.count("site") >= 1
        page.get_by_label("Mã dây chuyền vật lý").fill("L1")
        page.get_by_label("Hiệu lực từ").fill("2026-11-14")
        page.get_by_label("Bằng chứng định danh vật lý").fill("PHYSICAL-SOURCE-001")
        page.get_by_label("Lý do khai báo dây chuyền").fill("Synthetic physical line evidence")
        page.get_by_label("Xác nhận định danh vật lý độc lập").check()
        page.get_by_role("button", name="Tạo dây chuyền vật lý").click()
        if uncertain_stage == "line":
            page.get_by_text("Chưa xác minh được kết quả:", exact=False).wait_for()
            assert page.get_by_role("button", name="Đã khóa intent").is_disabled()
            assert post_attempts["line"] == 1
            page.get_by_role("button", name="Đọc lại canonical").click()
        page.get_by_text("Đã xác minh dây chuyền UUID", exact=False).wait_for()
        assert "line" in creates and readbacks.count("line") >= 1
        page.get_by_role("button", name="Đóng").click()
        page.get_by_role("heading", name="Hồ sơ kiểm tra đầu tiên").wait_for()
        page.get_by_label("Loại GxP cho hồ sơ mới").select_option("GMP")
        page.get_by_label("ProductionLine UUID").select_option(creates["line"]["production_line_id"])
        page.get_by_label("Loại kiểm tra hồ sơ đầu tiên").fill("Mới")
        page.get_by_label("Tiêu chuẩn áp dụng").fill("WHO-GMP")
        page.get_by_label("Lý do tạo hồ sơ đầu tiên").fill("Synthetic first Case")
        page.get_by_label("Xác nhận chỉ tạo Case Draft").check()
        submit = page.get_by_role("button", name="Tạo hồ sơ Draft")
        page.wait_for_function(
            "() => {const b=Array.from(document.querySelectorAll('button')).find(x=>x.textContent?.trim()==='Tạo hồ sơ Draft');return !!b&&!b.disabled;}"
        )
        submit.click()
        page.get_by_text("Case nháp canonical đã xác minh:", exact=False).wait_for()
        assert "case" in creates and readbacks.count("case") >= 1
        assert "workspace" not in readbacks, "Case workspace opened without explicit action"
        page.get_by_role("button", name="Mở Case workspace").click()
        dest = page.get_by_test_id("workspace-destination")
        dest.wait_for()
        parsed = urlsplit(BASE + dest.inner_text())
        query = parse_qs(parsed.query)
        assert parsed.path == "/search" and query.get("history_id") == [creates["case"]["case_id"]]
        assert query.get("site_id") == [creates["site"]["site_id"]]
        assert query.get("production_line_id") == [creates["line"]["production_line_id"]]
        assert query.get("gxp_type") == ["GMP"] and query.get("line_code") == ["L1"]
        assert len(creates) == 4 and not errors, (creates, errors)
        assert post_attempts == {"company": 1, "site": 1, "line": 1, "case": 1}, post_attempts
        if uncertain_stage:
            assert uncertain_stage in first_failed_reads
            assert readbacks.count(uncertain_stage) >= 2, (uncertain_stage, readbacks)
        assert all(readbacks.count(k) >= 1 for k in ["company", "site", "line", "case", "workspace"])
        print(json.dumps({
            "scenario": "company-site-physical-initial-case" + (
                "-unknown-" + uncertain_stage if uncertain_stage else ""
            ),
            "status": "PASS", "physical_line_code": "L1",
            "distinct_uuid_count": len({creates["company"]["company_id"], creates["site"]["site_id"], creates["line"]["production_line_id"], creates["case"]["case_id"]}),
            "created_owners": list(creates), "readbacks": readbacks,
            "post_attempts": post_attempts, "failed_first_readbacks": sorted(first_failed_reads),
            "requests": requests,
        }, ensure_ascii=False))
    except BaseException:
        evidence = Path("browser-evidence")
        evidence.mkdir(exist_ok=True)
        page.screenshot(path=str(evidence / f"catalog-full-journey-{uncertain_stage or 'normal'}.png"), full_page=True)
        (evidence / f"catalog-full-journey-{uncertain_stage or 'normal'}.json").write_text(json.dumps(
            {"requests": requests, "created": creates, "readbacks": readbacks, "errors": errors}, indent=2
        ), encoding="utf-8")
        raise
    finally:
        context.close()


if __name__ == "__main__":
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for uncertain_stage in (None, "company", "site", "line"):
                run(browser, uncertain_stage=uncertain_stage)
        finally:
            browser.close()
