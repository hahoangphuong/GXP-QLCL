/** The second Chromium leg continues the separately seeded operator Case.
 * It clicks actual outcome, CAPA, final evaluation and PCT/CT controls.
 * All writes go through the real frontend -> FastAPI -> disposable PostgreSQL.
 * Authentication is development header-stub, never Google OIDC/UAT.
 */
import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {readFileSync,mkdirSync} from "node:fs";
import {join} from "node:path";

if(process.env.GXP_CROSS_HEAD_DISPOSABLE_GATE!=="1") throw Error("Disposable browser gate required");
const origin="http://127.0.0.1:4173";
const fixture=JSON.parse(readFileSync(process.env.GXP_CROSS_HEAD_FIXTURE_JSON,"utf8"));
const {operator_case:caseId,operator_site:siteId}=fixture;
if(!caseId||!siteId) throw Error("Operator owner fixture missing");
const artifacts=process.env.GXP_CROSS_HEAD_SCREENSHOTS;
const driver=process.env.GXP_CROSS_HEAD_PW_DIR;
if(!artifacts||!driver) throw Error("Missing CI-only browser paths");
mkdirSync(artifacts,{recursive:true});
const require=createRequire(join(driver,"bootstrap.cjs"));
const {chromium}=require("playwright");
const browser=await chromium.launch({headless:true});
const identity={"x-auth-user":"ci-workflow-admin","x-auth-role":"admin"};
let context;
try {
  context=await browser.newContext({viewport:{width:1366,height:768},acceptDownloads:false});
  await context.addInitScript(()=>{
    localStorage.setItem("gxp-operator-shell-auth",JSON.stringify({
      username:"ci-workflow-admin",role:"admin",
    }));
  });
  const page=await context.newPage();
  const requests=[],errors=[];
  page.on("pageerror",e=>errors.push(e.message));
  page.on("request",req=>{
    if(req.url().startsWith(origin+"/api/")&&!["GET","HEAD","OPTIONS"].includes(req.method()))
      requests.push({method:req.method(),path:new URL(req.url()).pathname});
  });
  await page.route("**/*",route=>{
    const u=route.request().url();
    if(u.startsWith(origin+"/")||u.startsWith("data:")||u.startsWith("blob:"))
      return route.continue();
    throw Error("Unexpected non-loopback request "+u);
  });
  const api=async path=>{
    const r=await context.request.get(origin+"/api"+path,{headers:identity});
    assert.equal(r.status(),200,"GET "+path+" "+r.status());
    return r.json();
  };
  const workspace=()=>api("/cases/"+caseId+"/workspace");
  const until=async (description,predicate)=>{
    for(let count=0;count<90;count++){
      const ws=await workspace();
      if(predicate(ws)) return ws;
      await page.waitForTimeout(150);
    }
    throw Error("Canonical readback did not reach "+description);
  };
  const cycle=(ws)=>ws.remediation.cycles.find(x=>x.round_no===1);
  try {
    assert.equal((await workspace()).case_summary.state,"inspection_completed");
    const entry=await page.goto(origin+"/cases/"+encodeURIComponent(caseId),
      {waitUntil:"domcontentloaded"});
    assert.equal(entry?.status(),200);
    await page.waitForURL(u=>u.pathname==="/search"&&u.searchParams.get("history_id")===caseId,{timeout:30000});
    await page.getByRole("tab",{name:"Các đợt kiểm tra & thay đổi"}).click();
    await page.getByRole("button",{name:"Kiểm tra thực tế",exact:true}).click();

    // Create the real InspectionOutcome through the owned field editor.
    await page.getByRole("button",{name:"Sửa Kết quả kiểm tra",exact:true}).press("Enter");
    await page.getByRole("textbox",{name:"Kết quả kiểm tra"}).fill("CI synthetic inspection result");
    await page.getByRole("button",{name:"Lưu Đánh giá kết quả",exact:true}).click();
    await until("InspectionOutcome persisted",ws=>
      ws.inspection.outcome_result==="CI synthetic inspection result"&&ws.inspection.outcome_row_version!=null);

    // A CAPA cycle is created, submitted and assessed via operator controls.
    await page.getByRole("button",{name:"Báo cáo khắc phục",exact:true}).click();
    await page.getByRole("button",{name:"Thêm vòng khắc phục",exact:true}).click();
    await page.getByRole("textbox",{name:"Số tham chiếu đến"}).fill("BROWSER-CAPA-1");
    await page.getByLabel("Ngày yêu cầu",{exact:true}).fill("2026-11-11");
    await page.getByRole("button",{name:"Tạo vòng khắc phục",exact:true}).click();
    let ws=await until("CAPA created",x=>cycle(x)?.status==="requested");
    const cycleId=cycle(ws).capa_cycle_id;
    assert.ok(cycleId);
    await page.getByLabel("Ngày ghi nhận tiếp nhận",{exact:true}).fill("2026-11-11");
    await page.getByRole("button",{name:"Ghi nhận tiếp nhận",exact:true}).click();
    await until("CAPA submitted",x=>cycle(x)?.status==="submitted");
    await page.getByLabel("Ngày đánh giá khắc phục",{exact:true}).fill("2026-11-11");
    await page.getByRole("combobox",{name:"Kết quả đánh giá khắc phục"}).selectOption("accepted");
    await page.getByRole("button",{name:"Đánh giá",exact:true}).click();
    await until("CAPA accepted",x=>cycle(x)?.status==="accepted");

    await page.getByRole("button",{name:"Kiểm tra thực tế",exact:true}).click();
    const final=page.getByRole("group",{name:"Chốt đánh giá cuối cùng"});
    await final.getByRole("textbox",{name:"Đánh giá cuối cùng"}).fill("Đạt");
    await final.getByRole("button",{name:"Chốt đánh giá cuối cùng",exact:true}).click();
    await until("final evaluation",x=>x.inspection.final_evaluation==="Đạt");

    const lifecycle=page.locator("[data-case-lifecycle]");
    await lifecycle.getByRole("button",{name:"Chuyển: Chờ cấp chứng nhận",exact:true}).click();
    await until("awaiting certificate decision",x=>x.case_summary.state==="awaiting_certificate_decision");

    const approval=page.getByRole("region",{name:"Trình phê duyệt PCT / CT"});
    await approval.getByRole("textbox",{name:"Tham chiếu trình"}).fill("BROWSER-PCT-1");
    await approval.getByRole("button",{name:"Tạo trình PCT",exact:true}).click();
    ws=await until("PCT created",x=>x.inspection.approval_submissions.some(a=>a.stage==="PCT"));
    const pct=ws.inspection.approval_submissions.find(a=>a.stage==="PCT");
    assert.equal(pct.round_no,1);
    const pctGroup=approval.getByRole("group",{name:"Hoàn tất PCT lần 1"});
    await pctGroup.getByLabel("Ngày hoàn tất trình",{exact:true}).fill("2026-11-11");
    await pctGroup.getByRole("button",{name:"Hoàn tất PCT",exact:true}).click();
    await until("PCT completed",x=>x.inspection.approval_submissions.some(a=>
      a.approval_submission_id===pct.approval_submission_id&&a.completed_on==="2026-11-11"));

    await approval.getByRole("combobox",{name:"PCT hoàn tất cho CT"}).selectOption(pct.approval_submission_id);
    await approval.getByRole("textbox",{name:"Tham chiếu trình"}).fill("BROWSER-CT-1");
    await approval.getByRole("button",{name:"Tạo trình CT",exact:true}).click();
    ws=await until("CT created",x=>x.inspection.approval_submissions.some(a=>a.stage==="CT"));
    const ct=ws.inspection.approval_submissions.find(a=>a.stage==="CT");
    assert.equal(ct.pct_submission_id,pct.approval_submission_id);
    const ctGroup=approval.getByRole("group",{name:"Hoàn tất CT lần 1"});
    await ctGroup.getByLabel("Ngày hoàn tất trình",{exact:true}).fill("2026-11-11");
    await ctGroup.getByRole("button",{name:"Hoàn tất CT",exact:true}).click();
    ws=await until("CT completed",x=>x.inspection.approval_submissions.some(a=>
      a.approval_submission_id===ct.approval_submission_id&&a.completed_on==="2026-11-11"));
    assert.equal(ws.case_summary.site_id,siteId);
    assert.equal(ws.certificate_issue_readiness.available,true);

    // Issue a synthetic GxP Certificate through the Case-owned browser dialog.
    // Issuance alone must not mark it Current.
    await page.getByRole("button",{name:"Cấp chứng nhận GPs",exact:true}).click();
    await page.getByRole("button",{name:"Cấp chứng nhận GxP",exact:true}).click();
    const issueDialog=page.getByRole("dialog",{name:"Cấp giấy chứng nhận GxP"});
    await issueDialog.getByRole("textbox",{name:"Số GCN"}).fill("CI-OPERATOR-GMP");
    await issueDialog.getByLabel("Ngày cấp",{exact:true}).fill("2026-11-11");
    await issueDialog.getByLabel("Ngày hết hạn",{exact:true}).fill("2027-11-11");
    await issueDialog.getByRole("button",{name:"Cấp giấy chứng nhận",exact:true}).click();
    ws=await until("Certificate issued",x=>x.linked_gxp_certificates.some(cert=>
      cert.site_id===siteId&&cert.case_id===caseId));
    const certId=ws.linked_gxp_certificates.find(cert=>cert.site_id===siteId&&cert.case_id===caseId).certificate_id;
    let certificate=await api("/certificates/"+certId);
    assert.equal(certificate.certificate_number,"CI-OPERATOR-GMP");
    assert.equal(certificate.latest_flag,false);
    const notCurrent=await api("/reports/certificates?gxp_type=GMP&number=CI-OPERATOR-GMP");
    assert.ok(notCurrent.items.every(cert=>cert.certificate_id!==certId));

    await page.getByRole("tab",{name:"Giấy chứng nhận GPs",exact:true}).click();
    await page.getByRole("table",{name:"Danh mục GCN GxP"}).locator("tbody tr")
      .filter({hasText:"CI-OPERATOR-GMP"}).click();
    await page.getByRole("button",{name:"Đặt làm chứng nhận hiện hành",exact:true}).click();
    for(let attempt=0;attempt<90;attempt++){
      certificate=await api("/certificates/"+certId);
      if(certificate.latest_flag)break;
      await page.waitForTimeout(150);
    }
    assert.equal(certificate.latest_flag,true);
    const currentReport=await api("/reports/certificates?gxp_type=GMP&number=CI-OPERATOR-GMP");
    assert.ok(currentReport.items.some(cert=>cert.certificate_id===certId&&cert.site_id===siteId));

    // Re-enter Case lifecycle; no client-inferred transition is allowed.
    await page.getByRole("tab",{name:"Các đợt kiểm tra & thay đổi"}).click();
    await page.getByRole("button",{name:"Kiểm tra thực tế",exact:true}).click();
    // Reuse the Case lifecycle locator from the previous transition.
    await lifecycle.getByRole("button",{name:"Chuyển: Đã cấp chứng nhận",exact:true}).click();
    await until("Case certified",x=>x.case_summary.state==="certified");
    await lifecycle.getByRole("button",{name:"Chuyển: Đã đóng hồ sơ",exact:true}).click();
    await until("Case closed",x=>x.case_summary.state==="closed");

    const afterClose=await api("/reports/cases?gxp_type=GMP&q=Browser%20Operator%20CI");
    assert.ok(afterClose.items.every(x=>x.case_id!==caseId));
    const retained=await api("/reports/certificates?gxp_type=GMP&number=CI-OPERATOR-GMP");
    assert.ok(retained.items.some(cert=>cert.certificate_id===certId&&cert.site_id===siteId));
    const report=await api("/reports/cases?gxp_type=GMP&q=Browser%20Operator%20CI");
    assert.ok(report.items.every(x=>x.case_id!==caseId));
    // Browser emits only intended commands; no automatic duplicate submits.
    assert.equal(requests.length,14,"Unexpected number of UI mutation requests: "+JSON.stringify(requests));
    assert.deepEqual(errors,[]);
    process.stdout.write("OPERATOR_FULL_CASE_CERTIFICATE_BROWSER_PASS mutations="+requests.length+"\n");
  } catch(e) {
    await page.screenshot({path:join(artifacts,"operator-capa-approval-failed.png"),fullPage:true}).catch(()=>{});
    process.stderr.write("OPERATOR_CAPA_PCT_CT_BROWSER_FAILED "+String(e?.stack||e)+"\n");
    process.stderr.write("Mutation requests "+JSON.stringify(requests)+"\n");
    process.stderr.write("Browser errors "+JSON.stringify(errors)+"\n");
    throw e;
  }
} finally {
  await context?.close();
  await browser.close();
}
