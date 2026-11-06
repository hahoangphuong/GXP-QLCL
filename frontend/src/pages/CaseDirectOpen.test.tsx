import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess, } from "../App";
import { getCaseWorkspace } from "../lib/api";
import { CaseDirectOpen } from "./CaseDirectOpen";

vi.mock("../lib/api", () => ({ getCaseWorkspace: vi.fn() }));
const access: ApiAccess = { auth: { username: "reader", role: "reader" },
  useStubAuth: true, bearerToken: null, canLoadSecureApi: true, accessGeneration: 1 };

function Destination() {
  const location = useLocation();
  return <><output data-testid="resolved-url">{location.pathname + location.search}</output><output data-testid="return-hint">{location.state?.caseReportReturn ?? ""}</output></>;
}
function mount(url: string, currentAccess = access) {
  return render(<MemoryRouter initialEntries={[url]}><Routes>
    <Route path="/cases/:caseId" element={<CaseDirectOpen access={currentAccess} />} />
    <Route path="/search" element={<Destination />} />
  </Routes></MemoryRouter>);
}
function workspace(id: string, site = "site-uuid", state = "planned") {
  return {
    case_summary: { id, site_id: site, gxp_type: "GMP", production_line_id: "line-uuid", production_line_code: "L1", production_line_identity_state: "canonical", state },
  } as Awaited<ReturnType<typeof getCaseWorkspace>>;
}

beforeEach(() => vi.mocked(getCaseWorkspace).mockReset());

describe("canonical Case UUID entry", () => {
  it("preserves the validated report return alongside its workflow queue", async () => {
    vi.mocked(getCaseWorkspace).mockResolvedValue(workspace("case-uuid"));
    render(<MemoryRouter initialEntries={[{ pathname: "/cases/case-uuid", search: "?return_queue=inspection", state: { caseReportReturn: "/workflow?queue=inspection&state=planned&offset=100" } }]}><Routes><Route path="/cases/:caseId" element={<CaseDirectOpen access={access} />} /><Route path="/search" element={<Destination />} /></Routes></MemoryRouter>);
    expect(await screen.findByTestId("return-hint")).toHaveTextContent("/workflow?queue=inspection&state=planned&offset=100");
    expect(screen.getByTestId("resolved-url")).toHaveTextContent("return_queue=inspection");
  });
  it("rejects an external return hint", async () => {
    vi.mocked(getCaseWorkspace).mockResolvedValue(workspace("case-uuid"));
    render(<MemoryRouter initialEntries={[{ pathname: "/cases/case-uuid", state: { caseReportReturn: "https://attacker.example/" } }]}><Routes><Route path="/cases/:caseId" element={<CaseDirectOpen access={access} />} /><Route path="/search" element={<Destination />} /></Routes></MemoryRouter>);
    expect(await screen.findByTestId("return-hint")).toBeEmptyDOMElement();
  });
  it("does not adopt a return hint for a different workflow queue", async () => {
    vi.mocked(getCaseWorkspace).mockResolvedValue(workspace("case-uuid"));
    render(<MemoryRouter initialEntries={[{ pathname: "/cases/case-uuid", search: "?return_queue=active", state: { caseReportReturn: "/workflow?queue=inspection" } }]}><Routes><Route path="/cases/:caseId" element={<CaseDirectOpen access={access} />} /><Route path="/search" element={<Destination />} /></Routes></MemoryRouter>);
    expect(await screen.findByTestId("return-hint")).toBeEmptyDOMElement();
    expect(screen.getByTestId("resolved-url")).toHaveTextContent("return_queue=active");
  });
  it("resolves a Case to exact site, GxP, line and history selection", async () => {
    vi.mocked(getCaseWorkspace).mockResolvedValue(workspace("case-uuid"));
    mount("/cases/case-uuid");
    const resolved = await screen.findByTestId("resolved-url");
    const uri = new URL(resolved.textContent!, "https://app.test");
    expect(uri.pathname).toBe("/search");
    expect(uri.searchParams.get("history_id")).toBe("case-uuid");
    expect(uri.searchParams.get("site_id")).toBe("site-uuid");
    expect(uri.searchParams.get("gxp_type")).toBe("GMP");
    expect(uri.searchParams.get("production_line_id")).toBe("line-uuid");
    expect(uri.searchParams.get("line_code")).toBe("L1");
  });

  it("refuses an incorrect returned Case UUID instead of selecting the wrong record", async () => {
    vi.mocked(getCaseWorkspace).mockResolvedValue(workspace("other-case"));
    mount("/cases/case-uuid");
    expect(await screen.findByRole("alert")).toHaveTextContent("không khớp định danh");
    expect(screen.queryByTestId("resolved-url")).not.toBeInTheDocument();
  });

  it("does not call protected API without access", () => {
    mount("/cases/case-uuid", { ...access, canLoadSecureApi: false });
    expect(screen.getByText("Cần đăng nhập")).toBeInTheDocument();
    expect(getCaseWorkspace).not.toHaveBeenCalled();
  });

  it("does not redirect when the canonical Case response lacks its Site identity", async () => {
    vi.mocked(getCaseWorkspace).mockResolvedValue(workspace("blocked-case", ""));
    mount("/cases/blocked-case");
    expect(await screen.findByRole("alert")).toHaveTextContent("thiếu ngữ cảnh");
    expect(screen.queryByTestId("resolved-url")).not.toBeInTheDocument();
  });
  it.each(["planned", "decision_issued", "inspection_in_progress"])("opens the inspection tab for canonical %s", async state => {
    vi.mocked(getCaseWorkspace).mockResolvedValue(workspace("case-uuid", "site-uuid", state));
    mount("/cases/case-uuid?return_queue=inspection");
    const uri = new URL((await screen.findByTestId("resolved-url")).textContent!, "https://app.test");
    expect(uri.searchParams.get("event_tab")).toBe("Kiểm tra");
    expect(uri.searchParams.get("return_queue")).toBe("inspection");
  });
  it("rejects contradictory canonical line identity before navigating", async () => {
    const value = workspace("case-uuid");
    value.case_summary.production_line_id = null;
    vi.mocked(getCaseWorkspace).mockResolvedValue(value);
    mount("/cases/case-uuid");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByTestId("resolved-url")).not.toBeInTheDocument();
  });
  it("does not infer a specialized tab for an unknown state", async () => {
    vi.mocked(getCaseWorkspace).mockResolvedValue(workspace("case-uuid", "site-uuid", "unknown"));
    mount("/cases/case-uuid");
    const uri = new URL((await screen.findByTestId("resolved-url")).textContent!, "https://app.test");
    expect(uri.searchParams.has("event_tab")).toBe(false);
  });
  it.each(["draft", "application_received", "under_assessment", "inspection_completed", "unknown"])("keeps %s in the general Case workspace", async state => {
    vi.mocked(getCaseWorkspace).mockResolvedValue(workspace("case-uuid", "site-uuid", state));
    mount("/cases/case-uuid?return_queue=active");
    const uri = new URL((await screen.findByTestId("resolved-url")).textContent!, "https://app.test");
    expect(uri.searchParams.has("event_tab")).toBe(false);
  });
  it.each([false, true])("does not navigate to certificate issuance when blocked or another action is available (%s)", async competing => {
    const value = workspace("case-uuid", "site-uuid", "awaiting_certificate_decision");
    value.certificate_issue_readiness = { action_key: "issue_certificate", available: competing, certificate_type: "GMP" } as typeof value.certificate_issue_readiness;
    value.inspection = { approval_actions: competing ? [{ available: true }] : [] } as typeof value.inspection;
    value.remediation = { actions: [] } as unknown as typeof value.remediation;
    value.transition_actions = [];
    vi.mocked(getCaseWorkspace).mockResolvedValue(value);
    mount("/cases/case-uuid?return_queue=certificate_decision");
    const uri = new URL((await screen.findByTestId("resolved-url")).textContent!, "https://app.test");
    expect(uri.searchParams.has("event_tab")).toBe(false);
  });
  it("suggests certificate workspace only when backend readiness is available without competing actions", async () => {
    const value = workspace("case-uuid", "site-uuid", "awaiting_certificate_decision");
    value.certificate_issue_readiness = { action_key: "issue_certificate", available: true, certificate_type: "GMP" } as typeof value.certificate_issue_readiness;
    value.inspection = { approval_actions: [] } as unknown as typeof value.inspection;
    value.remediation = { actions: [] } as unknown as typeof value.remediation;
    value.transition_actions = [];
    vi.mocked(getCaseWorkspace).mockResolvedValue(value);
    mount("/cases/case-uuid?return_queue=certificate_decision");
    const uri = new URL((await screen.findByTestId("resolved-url")).textContent!, "https://app.test");
    expect(uri.searchParams.get("event_tab")).toBe("Chứng nhận GxP");
  });
  it("preserves a valid historical unlinked line and ignores an untrusted queue", async () => {
    const value = workspace("case-uuid");
    value.case_summary.production_line_id = null;
    value.case_summary.production_line_identity_state = "legacy_unlinked";
    vi.mocked(getCaseWorkspace).mockResolvedValue(value);
    mount("/cases/case-uuid?return_queue=untrusted");
    const uri = new URL((await screen.findByTestId("resolved-url")).textContent!, "https://app.test");
    expect(uri.searchParams.get("line_code")).toBe("L1");
    expect(uri.searchParams.has("return_queue")).toBe(false);
    expect(uri.searchParams.has("event_tab")).toBe(false);
  });
  it("includes the canonical GxP context for facility-wide resolution", async () => {
    const value = workspace("case-uuid");
    value.case_summary.production_line_id = null;
    value.case_summary.production_line_code = null;
    value.case_summary.production_line_identity_state = "facility_wide";
    vi.mocked(getCaseWorkspace).mockResolvedValue(value);
    mount("/cases/case-uuid?return_queue=inspection");
    const uri = new URL((await screen.findByTestId("resolved-url")).textContent!, "https://app.test");
    expect(uri.searchParams.get("context_gxp")).toBe("GMP");
    expect(uri.searchParams.has("production_line_id")).toBe(false);
  });
  it("forwards a matching document hint only after canonical revalidation", async () => {
    const value = workspace("case-uuid");
    const item = { checklist_key: "case:case-uuid:PLAN", parent_scope: "case", parent_id: "case-uuid", family_code: "PLAN", status: "missing", document_id: null };
    value.documents = { items: [item as typeof value.documents.items[number]] };
    value.contextual_document_actions = [{ ...item, workflow_step: "Kiểm tra", actions: [{ action_key: "create", available: true }] } as typeof value.contextual_document_actions[number]];
    vi.mocked(getCaseWorkspace).mockResolvedValue(value);
    mount("/cases/case-uuid?return_queue=inspection&document_key=case%3Acase-uuid%3APLAN");
    const uri = new URL((await screen.findByTestId("resolved-url")).textContent!, "https://app.test");
    expect(uri.searchParams.get("document_key")).toBe(item.checklist_key);
    expect(uri.searchParams.get("return_queue")).toBe("inspection");
    expect(uri.searchParams.has("event_tab")).toBe(false);
  });
  it("falls back to general Case when the hinted document belongs elsewhere", async () => {
    const value = workspace("case-uuid");
    value.documents = { items: [] };
    value.contextual_document_actions = [];
    vi.mocked(getCaseWorkspace).mockResolvedValue(value);
    mount("/cases/case-uuid?document_key=foreign");
    const uri = new URL((await screen.findByTestId("resolved-url")).textContent!, "https://app.test");
    expect(uri.searchParams.has("document_key")).toBe(false);
    expect(uri.searchParams.has("event_tab")).toBe(false);
  });
  it("ignores the first A response after navigating A to B to A", async () => {
    type Workspace = Awaited<ReturnType<typeof getCaseWorkspace>>;
    let first!: (value: Workspace) => void;
    let second!: (value: Workspace) => void;
    let third!: (value: Workspace) => void;
    vi.mocked(getCaseWorkspace).mockImplementationOnce(() => new Promise(resolve => { first = resolve; }))
      .mockImplementationOnce(() => new Promise(resolve => { second = resolve; }))
      .mockImplementationOnce(() => new Promise(resolve => { third = resolve; }));
    function Controls() { const navigate = useNavigate(); return <><button onClick={() => navigate("/cases/B?return_queue=inspection")}>B</button><button onClick={() => navigate("/cases/A?return_queue=inspection")}>A</button></>; }
    render(<MemoryRouter initialEntries={["/cases/A?return_queue=inspection"]}><Controls /><Routes><Route path="/cases/:caseId" element={<CaseDirectOpen access={access} />} /><Route path="/search" element={<Destination />} /></Routes></MemoryRouter>);
    await waitFor(() => expect(first).toBeDefined());
    fireEvent.click(screen.getByText("B"));
    await waitFor(() => expect(second).toBeDefined());
    fireEvent.click(screen.getByText("A"));
    await waitFor(() => expect(third).toBeDefined());
    await act(async () => { first(workspace("A", "old-site")); second(workspace("B")); });
    expect(screen.queryByTestId("resolved-url")).not.toBeInTheDocument();
    await act(async () => third(workspace("A", "fresh-site")));
    expect(await screen.findByTestId("resolved-url")).toHaveTextContent("fresh-site");
  });
  it("does not use a pending workspace from a previous access generation", async () => {
    type Workspace = Awaited<ReturnType<typeof getCaseWorkspace>>;
    let old!: (value: Workspace) => void;
    let next!: (value: Workspace) => void;
    vi.mocked(getCaseWorkspace).mockImplementationOnce(() => new Promise(resolve => { old = resolve; }))
      .mockImplementationOnce(() => new Promise(resolve => { next = resolve; }));
    const view = mount("/cases/case-uuid?return_queue=inspection");
    await waitFor(() => expect(old).toBeDefined());
    view.rerender(<MemoryRouter initialEntries={["/cases/case-uuid?return_queue=inspection"]}><Routes>
      <Route path="/cases/:caseId" element={<CaseDirectOpen access={{ ...access, accessGeneration: 2 }} />} />
      <Route path="/search" element={<Destination />} />
    </Routes></MemoryRouter>);
    await waitFor(() => expect(next).toBeDefined());
    await act(async () => old(workspace("case-uuid", "old-site")));
    expect(screen.queryByTestId("resolved-url")).not.toBeInTheDocument();
    await act(async () => next(workspace("case-uuid", "new-site")));
    expect(await screen.findByTestId("resolved-url")).toHaveTextContent("new-site");
  });
});
