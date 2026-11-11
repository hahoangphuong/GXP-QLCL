/** Real Chromium operator clicks against an independently seeded disposable Case.
 * Every write travels through the mounted frontend and live FastAPI/PostgreSQL.
 * This does not authenticate Google OIDC or assert legally issued certificates.
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

if (process.env.GXP_CROSS_HEAD_DISPOSABLE_GATE !== "1") throw Error("Disposable opt-in missing.");
const origin = "http://127.0.0.1:4173";
const fixture = JSON.parse(readFileSync(process.env.GXP_CROSS_HEAD_FIXTURE_JSON, "utf8"));
if (!fixture.operator_case || !fixture.operator_site) throw Error("Operator Case fixture missing.");
const artifactDir = process.env.GXP_CROSS_HEAD_SCREENSHOTS;
const playwrightDir = process.env.GXP_CROSS_HEAD_PW_DIR;
if (!artifactDir || !playwrightDir) throw Error("Required isolated browser paths missing.");
mkdirSync(artifactDir, {recursive:true});
const require = createRequire(join(playwrightDir, "bootstrap.cjs"));
const {chromium} = require("playwright");
const browser = await chromium.launch({headless:true});
const states = [
  ["application_received", "Đã tiếp nhận hồ sơ"],
  ["under_assessment", "Đang thẩm định"],
  ["planned", "Đã lập kế hoạch"],
  ["decision_issued", "Đã ban hành quyết định"],
  ["inspection_in_progress", "Đang kiểm tra"],
  ["inspection_completed", "Đã hoàn tất kiểm tra"],
];
const headers = {"x-auth-user":"ci-browser-operator", "x-auth-role":"inspector"};
let context;
try {
  context = await browser.newContext({viewport:{width:1366,height:768},acceptDownloads:false});
  await context.addInitScript(() => {
    localStorage.setItem("gxp-operator-shell-auth", JSON.stringify({
      username:"ci-browser-operator",role:"inspector",
    }));
  });
  const page = await context.newPage();
  const networkMutations = [];
  const errors = [];
  page.on("pageerror", err => errors.push(err.message));
  page.on("request", req => {
    if (req.url().startsWith(origin+"/api/") && !["GET","HEAD","OPTIONS"].includes(req.method())) {
      networkMutations.push({method:req.method(),path:new URL(req.url()).pathname});
    }
  });
  await page.route("**/*", route => {
    const url=route.request().url();
    if (url.startsWith(origin+"/") || url.startsWith("data:") || url.startsWith("blob:")) return route.continue();
    throw Error("Operator browser attempted non-loopback network request.");
  });
  const api = async (path) => {
    const response = await context.request.get(origin+"/api"+path,{headers});
    assert.equal(response.status(),200, "GET "+path+" returned "+response.status());
    return response.json();
  };
  try {
    const before = await api("/cases/"+fixture.operator_case+"/workspace");
    assert.equal(before.case_summary.id,fixture.operator_case);
    assert.equal(before.case_summary.site_id,fixture.operator_site);
    assert.equal(before.case_summary.state,"draft");
    const firstVersion = before.case_summary.row_version;
    const firstReport = await api("/reports/cases?gxp_type=GMP&q=Browser%20Operator%20CI");
    assert.ok(firstReport.items.some(item => item.case_id===fixture.operator_case && item.state==="draft"),
      "Operator Case must be visible in canonical active report before mutation");

    const response = await page.goto(origin+"/cases/"+encodeURIComponent(fixture.operator_case),
      {waitUntil:"domcontentloaded"});
    assert.equal(response?.status(),200);
    await page.waitForURL(url => url.pathname==="/search"
      && url.searchParams.get("history_id")===fixture.operator_case,{timeout:30000});
    await page.getByRole("tab",{name:"Các đợt kiểm tra & thay đổi"}).click();
    await page.getByRole("button",{name:"Kiểm tra thực tế",exact:true}).click();
    const lifecycle = page.locator("[data-case-lifecycle]");
    await lifecycle.waitFor({state:"visible",timeout:30000});

    for (const [state,label] of states) {
      const target=lifecycle.getByRole("button",{name:"Chuyển: "+label,exact:true});
      await target.waitFor({state:"visible",timeout:20000});
      assert.equal(await target.isEnabled(),true, "Operator transition unavailable: "+state);
      await lifecycle.getByRole("textbox",{name:"Lý do chuyển trạng thái"})
        .fill("CI synthetic browser transition "+state);
      await target.click();
      // Wait for a verified canonical re-read, not an optimistic status guess.
      await page.waitForFunction(async ({caseId,expected}) => {
        const response = await fetch("/api/cases/"+encodeURIComponent(caseId)+"/workspace",
          {headers:{"x-auth-user":"ci-browser-operator","x-auth-role":"inspector"}});
        if (!response.ok) return false;
        const body=await response.json();
        return body.case_summary?.id===caseId && body.case_summary.state===expected;
      },{caseId:fixture.operator_case,expected:state},{timeout:30000});
      const report = await api("/reports/cases?gxp_type=GMP&q=Browser%20Operator%20CI");
      const row=report.items.find(item=>item.case_id===fixture.operator_case);
      assert.ok(row,"Missing canonical Case after "+state);
      assert.equal(row.site_id,fixture.operator_site);
      assert.equal(row.state,state,"Stale report after "+state);
    }
    assert.deepEqual(networkMutations,states.map(()=>({
      method:"POST",path:"/api/cases/"+fixture.operator_case+"/transition",
    })), "Browser must submit one exact Case POST per verified operator action");
    // A stale command from before these transitions must be rejected without
    // silently replaying a prior Case state.
    const stale = await context.request.post(origin+"/api/cases/"+fixture.operator_case+"/transition",{
      headers:{...headers,"content-type":"application/json"},
      data:{target_state:"application_received",expected_version:firstVersion,reason:"stale CI probe"},
    });
    assert.equal(stale.status(),409);
    assert.equal((await api("/cases/"+fixture.operator_case+"/workspace")).case_summary.state,
      "inspection_completed");
    assert.deepEqual(errors,[]);
    process.stdout.write("OPERATOR_CASE_TRANSITION_REPORT_PASS steps="+states.length+"\n");
  } catch (error) {
    await page.screenshot({path:join(artifactDir,"operator-case-mutation-failed.png"),fullPage:true}).catch(()=>{});
    process.stderr.write("OPERATOR_CASE_TRANSITION_REPORT_FAILED "+String(error?.stack||error)+"\n");
    process.stderr.write("Operator browser errors "+JSON.stringify(errors)+"\n");
    process.stderr.write("Operator mutations "+JSON.stringify(networkMutations)+"\n");
    throw error;
  }
} finally {
  await context?.close();
  await browser.close();
}
