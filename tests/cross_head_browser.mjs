/** Chromium verifies the pinned Codex UI against disposable FastAPI/PostgreSQL.
 * No remote URL, production credentials or persistence beyond the CI runner.
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

if (process.env.GXP_CROSS_HEAD_DISPOSABLE_GATE !== "1") throw Error("Disposable CI opt-in required.");
const origin = "http://127.0.0.1:4173";
const fixture = JSON.parse(readFileSync(process.env.GXP_CROSS_HEAD_FIXTURE_JSON, "utf8"));
const artifacts = process.env.GXP_CROSS_HEAD_SCREENSHOTS;
if (!artifacts || !process.env.GXP_CROSS_HEAD_PW_DIR) throw Error("Missing CI paths.");
mkdirSync(artifacts, { recursive: true });
const require = createRequire(join(process.env.GXP_CROSS_HEAD_PW_DIR, "bootstrap.cjs"));
const { chromium } = require("playwright");
const browser = await chromium.launch({ headless: true });
const sizes = [
  {name:"desktop", width:1366, height:768},
  {name:"wide", width:1920, height:1080},
  {name:"mobile", width:390, height:844},
];
let failed = false;
try {
  for (const size of sizes) {
    const context = await browser.newContext({ viewport:size, acceptDownloads:false });
    await context.addInitScript(() => {
      localStorage.setItem("gxp-operator-shell-auth", JSON.stringify({
        username:"ci-browser-inspector", role:"inspector",
      }));
    });
    const page = await context.newPage();
    const calls = [], errors = [], mutations = [];
    page.on("request", req => {
      if (req.url().startsWith(origin + "/api/")) {
        calls.push(req.url());
        if (!["GET", "HEAD", "OPTIONS"].includes(req.method())) mutations.push(`${req.method()} ${req.url()}`);
      }
    });
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/*", route => {
      const url = route.request().url();
      if (url.startsWith(origin + "/") || url.startsWith("data:") || url.startsWith("blob:")) {
        return route.continue();
      }
      throw Error("Unexpected non-loopback browser network request.");
    });
    try {
      const response = await page.goto(origin + "/search?facility_name=Cross-head", {waitUntil:"domcontentloaded"});
      assert.equal(response?.status(), 200);
      await page.getByRole("tab", {name:"GMP",exact:true}).waitFor({state:"visible",timeout:20000});
      const row = page.locator(".facility-table tbody tr").first();
      await row.waitFor({state:"visible",timeout:20000});
      assert.match(await row.innerText(), /Cross.head CI synthetic/i);
      await row.click();
      const history = page.locator(".history-table tbody tr").first();
      await history.waitFor({state:"visible",timeout:20000});
      await history.click();
      await page.getByRole("tab", {name:"Các đợt kiểm tra & thay đổi"}).click();
      // A Case owns document navigation under the Hồ sơ workflow step.
      // "Tài liệu" is a different step used by Change Requests only.
      await page.getByRole("button", {name:"Hồ sơ đăng ký",exact:true}).click();
      await page.getByRole("table", {name:"Danh sách tài liệu liên quan"}).waitFor({state:"visible",timeout:20000});
      const selections = page.locator("button.document-select");
      assert.ok(await selections.count() > 0, "Expected synthetic document checklist");
      const first = selections.first();
      await first.focus();
      const beforeKeys = calls.length;
      await first.press("ArrowDown");
      await first.press("Home");
      await first.press("End");
      assert.equal(calls.length, beforeKeys, "Focus-only navigation triggered API calls");
      await first.focus();
      await first.press("Enter");
      await page.getByText("Chi tiết tài liệu", {exact:true}).waitFor();
      await page.screenshot({path:join(artifacts,size.name+".png"),fullPage:true});

      // Certificate -> owning Case must be independently verified by the
      // authorized Case workspace. Neither the URL hint nor the fixture's
      // Certificate number is an access or legal-issuance decision.
      const verifiedCase = new URL(`/cases/${fixture.case}`, origin);
      verifiedCase.searchParams.set("source_certificate_id", fixture.gxp_certificate);
      verifiedCase.searchParams.set("source_site_id", fixture.site);
      await page.goto(verifiedCase.toString(), {waitUntil:"domcontentloaded"});
      await page.waitForURL(url => url.pathname === "/search"
        && url.searchParams.get("history_id") === fixture.case, {timeout:30000});
      const verifiedWorkspace = new URL(page.url());
      assert.equal(verifiedWorkspace.searchParams.get("site_id"), fixture.site);
      assert.equal(verifiedWorkspace.searchParams.get("event_tab"), "Chứng nhận GxP");

      // Same Site is NOT sufficient: the sibling Case does not own this GCN.
      const unrelatedCase = new URL(`/cases/${fixture.other_case}`, origin);
      unrelatedCase.searchParams.set("source_certificate_id", fixture.gxp_certificate);
      unrelatedCase.searchParams.set("source_site_id", fixture.site);
      await page.goto(unrelatedCase.toString(), {waitUntil:"domcontentloaded"});
      await page.getByRole("alert").filter({hasText:"Case không khớp chứng nhận và Site canonical"})
        .waitFor({state:"visible",timeout:30000});
      assert.equal(new URL(page.url()).pathname, `/cases/${fixture.other_case}`);

      // Registration metadata is read-only, with distinct GxP and DDK
      // document owners. Never infer a signed original or download binary.
      await page.goto(origin+`/documents/certificates/${fixture.gxp_certificate}`, {waitUntil:"domcontentloaded"});
      await page.getByText("Synthetic unverified GxP metadata", {exact:true}).waitFor({state:"visible",timeout:30000});
      await page.getByText(/chưa xác minh tệp binary hoặc bản gốc đã ký/i).waitFor({state:"visible"});
      assert.equal(await page.getByRole("button", {name:/Tải|Ban hành|Lưu thay đổi/}).count(), 0);

      await page.goto(origin+`/documents/business-eligibility-certificates/${fixture.ddk_certificate}`,
        {waitUntil:"domcontentloaded"});
      await page.getByText("Synthetic unverified DDK metadata", {exact:true}).waitFor({state:"visible",timeout:30000});
      assert.equal(await page.getByText("Synthetic unverified GxP metadata", {exact:true}).count(), 0);
      assert.deepEqual(mutations, [], "Read-only Certificate -> Case -> metadata browser journey mutated data");
      process.stdout.write("CERTIFICATE_CASE_DOCUMENT_PASS "+size.name+"\n");
      assert.deepEqual(errors, []);
      assert.ok(calls.length > 0);
      process.stdout.write("BROWSER_PASS "+size.name+" "+size.width+"x"+size.height+" calls="+calls.length+"\n");
    } catch (e) {
      failed = true;
      await page.screenshot({path:join(artifacts,size.name+"-failed.png"),fullPage:true}).catch(()=>{});
      process.stderr.write("BROWSER_FAILED "+size.name+" "+String(e?.stack||e)+"\n");
      process.stderr.write("Browser errors: "+JSON.stringify(errors)+"\n");
      break;
    } finally {
      await context.close();
    }
  }
} finally {
  await browser.close();
}
if (failed) process.exitCode = 1;
