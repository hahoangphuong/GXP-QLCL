import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import type { ApiAccess } from "../../App";
import { getCaseReport } from "../../lib/api";
import { CaseReport } from "./CaseReport";
import { caseReportReturn } from "./caseReportUrl";

vi.mock("../../lib/api", () => ({ getCaseReport: vi.fn() }));
const access: ApiAccess = { auth: { username: "reader", role: "reader" }, bearerToken: null, useStubAuth: true, canLoadSecureApi: true, accessGeneration: 1 };
function History() { const location = useLocation(); const nav = useNavigate(); return <><output data-testid="url">{location.search}</output><button onClick={() => nav(-1)}>Back</button><button onClick={() => nav(1)}>Forward</button></>; }
beforeEach(() => { vi.mocked(getCaseReport).mockReset().mockImplementation(async f => ({ items: [], total_count: f.offset ?? 0, offset: f.offset ?? 0, limit: 100 })); });
it("restores Case filters and page from a shared URL", async () => {
  render(<MemoryRouter initialEntries={["/reports?report=cases&gxp_type=GMP&state=planned&opened_year=2026&q=test&offset=100"]}><CaseReport access={access} inspectionQueue={false} urlState /></MemoryRouter>);
  await waitFor(() => expect(getCaseReport).toHaveBeenCalledWith(expect.objectContaining({ gxp_type: "GMP", state: "planned", opened_year: "2026", q: "test", offset: 100 }), access.auth, true, null));
});
it("rejects an invalid inspection state before fetching", async () => {
  render(<MemoryRouter initialEntries={["/reports?report=inspection&state=under_assessment"]}><CaseReport access={access} inspectionQueue urlState /></MemoryRouter>);
  expect(await screen.findByRole("alert")).toHaveTextContent("không hợp lệ");
  expect(getCaseReport).not.toHaveBeenCalled();
});
it("restores applied filters on Back and Forward", async () => {
  render(<MemoryRouter initialEntries={["/reports?report=cases"]}><History /><CaseReport access={access} inspectionQueue={false} urlState /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Loại GxP"), { target: { value: "GLP" } });
  fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
  await waitFor(() => expect(screen.getByTestId("url")).toHaveTextContent("gxp_type=GLP"));
  fireEvent.click(screen.getByRole("button", { name: "Back" }));
  await waitFor(() => expect(screen.getByLabelText("Loại GxP")).toHaveValue(""));
  fireEvent.click(screen.getByRole("button", { name: "Forward" }));
  await waitFor(() => expect(screen.getByLabelText("Loại GxP")).toHaveValue("GLP"));
});
it("round-trips pagination and resets offset when a new filter is applied", async () => {
  const row = { case_id: "case", site_id: "site", result_key: "key", production_line_id: null, facility_name: "Cơ sở", company_name: "Công ty", gxp_type: "GMP", state: "planned", reference_code: "KT", opened_year: 2026 };
  const rows = Array.from({ length: 101 }, (_, n) => ({ ...row, case_id: `case-${n}` }));
  vi.mocked(getCaseReport).mockImplementation(async f => { const offset = f.offset ?? 0; return { items: rows.slice(offset, offset + 100), total_count: 101, offset, limit: 100 }; });
  render(<MemoryRouter initialEntries={["/reports?report=cases"]}><History /><CaseReport access={access} inspectionQueue={false} urlState /></MemoryRouter>);
  await screen.findByText("Trang 1 / 2"); fireEvent.change(screen.getByLabelText("Cơ sở, công ty hoặc mã hồ sơ"), { target: { value: "unapplied" } }); fireEvent.click(screen.getByRole("button", { name: "Trang sau" }));
  expect(await screen.findByText("Trang 2 / 2")).toBeInTheDocument(); expect(screen.getByTestId("url")).toHaveTextContent("offset=100");
  expect(screen.getByLabelText("Cơ sở, công ty hoặc mã hồ sơ")).toHaveValue("unapplied");
  fireEvent.click(screen.getByRole("button", { name: "Back" })); expect(await screen.findByText("Trang 1 / 2")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Forward" })); expect(await screen.findByText("Trang 2 / 2")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Cơ sở, công ty hoặc mã hồ sơ"), { target: { value: "new" } }); fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
  await waitFor(() => expect(screen.getByTestId("url")).not.toHaveTextContent("offset=100"));
});
it.each(["offset=-1", "offset=1", "offset=1.5", "offset=9007199254740992", "gxp_type=GSP", "state=bad", "opened_year=1899", "opened_year=20xx", "state=planned&state=draft", "case_state=", "case_state=awaiting_certificate_decision&state=planned", `q=${"x".repeat(201)}`])("rejects invalid URL %s without fetching", async query => {
  render(<MemoryRouter initialEntries={[`/reports?report=cases&${query}`]}><CaseReport access={access} inspectionQueue={false} urlState /></MemoryRouter>);
  expect(await screen.findByRole("alert")).toHaveTextContent("không hợp lệ");
  expect(getCaseReport).not.toHaveBeenCalled();
});
it("rejects a returned row outside the inspection queue", async () => {
  vi.mocked(getCaseReport).mockResolvedValue({ items: [{ case_id: "case-a", site_id: "site-a", result_key: "key", production_line_id: null, facility_name: "Cơ sở", company_name: "Công ty", gxp_type: "GMP", state: "draft", reference_code: "KT-A", opened_year: 2026 }], total_count: 1, offset: 0, limit: 100 });
  render(<MemoryRouter initialEntries={["/reports?report=inspection"]}><CaseReport access={access} inspectionQueue urlState /></MemoryRouter>);
  expect(await screen.findByRole("alert")).toHaveTextContent("không nhất quán");
  expect(screen.queryByRole("link", { name: "KT-A" })).not.toBeInTheDocument();
});
it.each(["403", "404", "409"])("shows the current %s read error without retrying", async code => {
  vi.mocked(getCaseReport).mockRejectedValue(new Error(`HTTP ${code}`));
  render(<MemoryRouter initialEntries={["/reports?report=cases"]}><CaseReport access={access} inspectionQueue={false} urlState /></MemoryRouter>);
  expect(await screen.findByRole("alert")).toHaveTextContent(`HTTP ${code}`);
  expect(getCaseReport).toHaveBeenCalledTimes(1);
});
it("preserves the canonical Case link and the report return hint", async () => {
  vi.mocked(getCaseReport).mockResolvedValue({ items: [{ case_id: "case-a", site_id: "site-a", result_key: "key", production_line_id: null, facility_name: "Cơ sở", company_name: "Công ty", gxp_type: "GMP", state: "planned", reference_code: "KT-A", opened_year: 2026 }], total_count: 1, offset: 0, limit: 100 });
  function Destination() { const loc = useLocation(); return <p data-testid="return">{loc.state?.caseReportReturn}</p>; }
  render(<MemoryRouter initialEntries={["/reports?report=cases&state=planned&q=abc"]}><Routes><Route path="/reports" element={<CaseReport access={access} inspectionQueue={false} urlState />} /><Route path="/cases/:caseId" element={<Destination />} /></Routes></MemoryRouter>);
  fireEvent.click(await screen.findByRole("link", { name: "KT-A" }));
  expect(screen.getByTestId("return")).toHaveTextContent("/reports?report=cases&state=planned&q=abc");
});
it("keeps the certificate decision queue's legacy state when bookmarked", async () => {
  render(<MemoryRouter initialEntries={["/reports?report=cases&case_state=awaiting_certificate_decision"]}><CaseReport access={access} initialState="awaiting_certificate_decision" inspectionQueue={false} urlState /></MemoryRouter>);
  await waitFor(() => expect(getCaseReport).toHaveBeenCalledWith(expect.objectContaining({ state: "awaiting_certificate_decision" }), access.auth, true, null));
});
it.each(["active", "inspection", "certificate_decision"] as const)("preserves the %s workflow queue in the return hint", async queue => {
  const state = queue === "certificate_decision" ? "awaiting_certificate_decision" : "planned";
  vi.mocked(getCaseReport).mockResolvedValue({ items: [{ case_id: "case-a", site_id: "site-a", result_key: "key", production_line_id: null, facility_name: "Cơ sở", company_name: "Công ty", gxp_type: "GMP", state, reference_code: "KT-A", opened_year: 2026 }], total_count: 1, offset: 0, limit: 100 });
  function Destination() { const loc = useLocation(); return <p data-testid="return">{loc.pathname + loc.search}|{loc.state?.caseReportReturn}</p>; }
  render(<MemoryRouter initialEntries={[`/workflow?queue=${queue}&state=${state}`]}><Routes><Route path="/workflow" element={<CaseReport access={access} inspectionQueue={queue === "inspection"} initialState={queue === "certificate_decision" ? state : ""} returnQueue={queue} urlState />} /><Route path="/cases/:caseId" element={<Destination />} /></Routes></MemoryRouter>);
  fireEvent.click(await screen.findByRole("link", { name: "KT-A" }));
  expect(screen.getByTestId("return")).toHaveTextContent(`return_queue=${queue}`);
  expect(screen.getByTestId("return")).toHaveTextContent(`/workflow?queue=${queue}&state=${state}`);
});
it.each(["https://evil.test/reports?report=cases", "//evil.test", "/reports?report=cases&offset=1", "/workflow?queue=inspection&state=draft", "/reports?report=cases&token=secret"])("rejects unsafe return hint %s", hint => {
  expect(caseReportReturn({ caseReportReturn: hint })).toBeNull();
});
it("uses applied rather than draft filters for CSV", async () => {
  vi.mocked(getCaseReport).mockImplementation(async f => ({ items: [], total_count: 0, offset: 0, limit: f.export ? 10000 : 100 }));
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:fixture") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<MemoryRouter initialEntries={["/reports?report=cases&q=applied"]}><CaseReport access={access} inspectionQueue={false} urlState /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole("button", { name: "Xuất CSV (Excel)" })).toBeEnabled());
  fireEvent.change(screen.getByLabelText("Cơ sở, công ty hoặc mã hồ sơ"), { target: { value: "draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Xuất CSV (Excel)" }));
  await waitFor(() => expect(getCaseReport).toHaveBeenCalledWith(expect.objectContaining({ q: "applied", export: true }), access.auth, true, null));
  click.mockRestore();
});
it("does not download an old export after URL owner changes", async () => {
  let resolveExport!: (page: Awaited<ReturnType<typeof getCaseReport>>) => void;
  vi.mocked(getCaseReport).mockImplementation(f => f.export ? new Promise(resolve => { resolveExport = resolve; }) : Promise.resolve({ items: [], total_count: 0, offset: 0, limit: 100 }));
  const create = vi.fn(() => "blob:stale"); Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
  function Controls() { const navigate = useNavigate(); return <button onClick={() => navigate("/reports?report=cases&q=B")}>B</button>; }
  render(<MemoryRouter initialEntries={["/reports?report=cases&q=A"]}><Controls /><CaseReport access={access} inspectionQueue={false} urlState /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole("button", { name: "Xuất CSV (Excel)" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Xuất CSV (Excel)" }));
  await waitFor(() => expect(resolveExport).toBeDefined());
  fireEvent.click(screen.getByRole("button", { name: "B" }));
  await act(async () => resolveExport({ items: [], total_count: 0, offset: 0, limit: 10000 }));
  expect(create).not.toHaveBeenCalled();
});
it.each(["403", "404", "409", "success"])("discards replaced %s responses after A → B → A", async outcome => {
  const pending: Array<{ resolve: (page: Awaited<ReturnType<typeof getCaseReport>>) => void; reject: (error: Error) => void }> = [];
  vi.mocked(getCaseReport).mockImplementation(() => new Promise((resolve, reject) => pending.push({ resolve, reject })));
  function Controls() { const nav = useNavigate(); return <><button onClick={() => nav("/reports?report=cases&q=B")}>B</button><button onClick={() => nav("/reports?report=cases&q=A")}>A</button></>; }
  render(<MemoryRouter initialEntries={["/reports?report=cases&q=A"]}><Controls /><CaseReport access={access} inspectionQueue={false} urlState /></MemoryRouter>);
  await waitFor(() => expect(pending).toHaveLength(1));
  fireEvent.click(screen.getByRole("button", { name: "B" })); await waitFor(() => expect(pending).toHaveLength(2));
  fireEvent.click(screen.getByRole("button", { name: "A" })); await waitFor(() => expect(pending).toHaveLength(3));
  await act(async () => pending[2].resolve({ items: [], total_count: 0, offset: 0, limit: 100 }));
  expect(await screen.findByText("Không có hồ sơ phù hợp.")).toBeInTheDocument();
  await act(async () => { if (outcome === "success") pending[0].resolve({ items: [{ case_id: "old-case", site_id: "old-site", result_key: "old-key", production_line_id: null, facility_name: "OLD OWNER", company_name: "Old", gxp_type: "GMP", state: "planned", reference_code: "OLD", opened_year: 2026 }], total_count: 1, offset: 0, limit: 100 }); else pending[0].reject(new Error(`stale ${outcome}`)); pending[1].reject(new Error("stale B")); });
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.queryByText("OLD OWNER")).not.toBeInTheDocument();
});
