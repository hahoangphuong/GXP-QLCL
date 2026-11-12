/** Ambiguous transport outcome: one committed response lost, one unsent request.
 * Real Chromium UI -> Vite proxy -> FastAPI -> disposable PostgreSQL.
 * This asserts only IN-SESSION fail-closed behavior, not durable recovery.
 */
import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {readFileSync,mkdirSync} from "node:fs";
import {join} from "node:path";

if(process.env.GXP_CROSS_HEAD_DISPOSABLE_GATE!=="1")
  throw Error("Disposable browser gate required");
const origin="http://127.0.0.1:4173";
const fixture=JSON.parse(readFileSync(process.env.GXP_CROSS_HEAD_FIXTURE_JSON,"utf8"));
const artifacts=process.env.GXP_CROSS_HEAD_SCREENSHOTS;
const driver=process.env.GXP_CROSS_HEAD_PW_DIR;
if(!fixture.case||!fixture.other_case||!artifacts||!driver)
  throw Error("Missing isolated negative-gate fixture or browser paths");
mkdirSync(artifacts,{recursive:true});
const require=createRequire(join(driver,"bootstrap.cjs"));
const {chromium}=require("playwright");
const browser=await chromium.launch({headless:true});
const identity={"x-auth-user":"ci-ambiguous-operator","x-auth-role":"inspector"};

async function probe(caseId,mode){
  const context=await browser.newContext({viewport:{width:1366,height:768},acceptDownloads:false});
  let page;
  const requests=[],errors=[];
  let intercepted=0,forwardedStatus=null;
  try {
    await context.addInitScript(()=>{
      localStorage.setItem("gxp-operator-shell-auth",JSON.stringify({
        username:"ci-ambiguous-operator",role:"inspector",
      }));
    });
    page=await context.newPage();
    page.on("pageerror",error=>errors.push(error.message));
    page.on("request",request=>{
      if(request.url().startsWith(origin+"/api/") &&
        !["GET","HEAD","OPTIONS"].includes(request.method()))
        requests.push({method:request.method(),path:new URL(request.url()).pathname});
    });
    await page.route("**/*",route=>{
      const url=route.request().url();
      if(url.startsWith(origin+"/")||url.startsWith("data:")||url.startsWith("blob:"))
        return route.continue();
      throw Error("Non-loopback browser request: "+url);
    });
    const api=async()=>{
      const r=await context.request.get(origin+"/api/cases/"+caseId+"/workspace",{headers:identity});
      assert.equal(r.status(),200,"Canonical Case workspace readback");
      return r.json();
    };
    const before=await api();
    assert.equal(before.case_summary.id,caseId);
    assert.equal(before.case_summary.state,"draft");

    const navigation=await page.goto(origin+"/cases/"+encodeURIComponent(caseId),
      {waitUntil:"domcontentloaded"});
    assert.equal(navigation?.status(),200);
    await page.waitForURL(u=>u.pathname==="/search"&&u.searchParams.get("history_id")===caseId,
      {timeout:30000});
    await page.getByRole("tab",{name:"Các đợt kiểm tra & thay đổi"}).click();
    await page.getByRole("button",{name:"Kiểm tra thực tế",exact:true}).click();
    const lifecycle=page.locator("[data-case-lifecycle]");
    const action=lifecycle.getByRole("button",{name:"Chuyển: Đã tiếp nhận hồ sơ",exact:true});
    await action.waitFor({state:"visible",timeout:30000});
    assert.equal(await action.isEnabled(),true);

    // Register only after page bootstrap: a single real browser command is
    // intercepted. In committed_lost_response the proxy forwards and gets
    // a successful server response, then intentionally aborts the response to
    // Chromium. In unsent_request the server never receives this command.
    await page.route("**/api/cases/"+caseId+"/transition",async route=>{
      intercepted+=1;
      if(mode==="committed_lost_response"){
        const response=await route.fetch();
        forwardedStatus=response.status();
        assert.equal(forwardedStatus,200,"Only a committed transition may lose its response");
      }
      await route.abort("failed");
    });
    await lifecycle.getByRole("textbox",{name:"Lý do chuyển trạng thái"})
      .fill("CI transport unknown "+mode);
    await action.click();
    await lifecycle.locator('[role="alert"]').waitFor({state:"visible",timeout:30000});
    const alertText=await lifecycle.locator('[role="alert"]').innerText();
    assert.match(alertText,/Chưa xác định kết quả lưu|chưa xác minh/i,
      "Unknown mutation outcome must not be treated as a verified rejection");
    assert.equal(intercepted,1,"The browser must not replay an ambiguous POST");
    const after=await api();
    assert.equal(after.case_summary.state,
      mode==="committed_lost_response"?"application_received":"draft");
    if(mode==="committed_lost_response"){
      assert.equal(forwardedStatus,200);
      assert.ok(after.case_summary.row_version>before.case_summary.row_version);
    }else{
      assert.equal(forwardedStatus,null);
      assert.equal(after.case_summary.row_version,before.case_summary.row_version);
    }

    // Tab round-trip must preserve the in-session command fence. A canonical
    // GET is not an authorized receipt or safe-retry token by itself.
    await page.getByRole("tab",{name:"Giấy chứng nhận GPs",exact:true}).click();
    await page.getByRole("tab",{name:"Các đợt kiểm tra & thay đổi"}).click();
    await page.getByRole("button",{name:"Kiểm tra thực tế",exact:true}).click();
    const same=lifecycle.getByRole("button",{name:"Chuyển: Đã tiếp nhận hồ sơ",exact:true});
    await same.waitFor({state:"visible",timeout:30000});
    assert.equal(await same.isDisabled(),true,
      "Unknown outcome must fence the original operation after tab round-trip");
    assert.equal(await lifecycle.getByRole("textbox",{name:"Lý do chuyển trạng thái"}).isEditable(),false,
      "Submitted request evidence must remain read-only");
    assert.match(await lifecycle.innerText(),/Kết quả chuyển trạng thái chưa xác minh/);
    await page.waitForTimeout(250);
    assert.equal(intercepted,1,"An ambiguous command may not retry automatically");
    assert.deepEqual(requests,[{method:"POST",path:"/api/cases/"+caseId+"/transition"}]);
    assert.deepEqual(errors,[]);
    process.stdout.write("OPERATOR_AMBIGUOUS_CASE_NO_REPLAY_PASS mode="+mode+
      " committed="+(mode==="committed_lost_response")+" requests="+requests.length+"\\n");
  }catch(error){
    await page?.screenshot({path:join(artifacts,"ambiguous-"+mode+"-failed.png"),fullPage:true}).catch(()=>{});
    process.stderr.write("OPERATOR_AMBIGUOUS_CASE_FAILED "+mode+" "+String(error?.stack||error)+"\\n");
    process.stderr.write("Commands "+JSON.stringify(requests)+" Browser errors "+JSON.stringify(errors)+"\\n");
    throw error;
  }finally{
    await context.close();
  }
}

try{
  await probe(fixture.other_case,"committed_lost_response");
  await probe(fixture.case,"unsent_request");
}finally{
  await browser.close();
}
