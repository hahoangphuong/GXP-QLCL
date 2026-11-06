import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import type { ApiAccess } from "../../App";
import { getCertificateReport, getChangeRequestReport } from "../../lib/api";
import { ReportsPage } from "../../pages/ReportsPage";

vi.mock("../../lib/api", () => ({ getCertificateReport: vi.fn(), getChangeRequestReport: vi.fn(), searchFacilities: vi.fn(), getCaseReport: vi.fn() }));
const access: ApiAccess = { auth: { username: "reader", role: "reader" }, bearerToken: null, useStubAuth: true, canLoadSecureApi: true, accessGeneration: 1 };
function History() { const location = useLocation(); const navigate = useNavigate(); return <><output data-testid="url">{location.search}</output><button onClick={() => navigate(-1)}>Back</button><button onClick={() => navigate(1)}>Forward</button></>; }
beforeEach(() => {
  vi.mocked(getCertificateReport).mockReset().mockImplementation(async f => ({ items: [], total_count: f?.offset ?? 0, limit: 100, offset: f?.offset ?? 0 }));
  vi.mocked(getChangeRequestReport).mockReset().mockResolvedValue({ items: [], total_count: 0, limit: 100, offset: 0 });
});
it("restores certificate filters and page from a shared report URL", async () => {
  render(<MemoryRouter initialEntries={["/reports?report=certificates&gxp_type=GSP&expiry_days=30&number=123&q=hello&offset=100"]}><History /><ReportsPage access={access} statusError={null} /></MemoryRouter>);
  await waitFor(() => expect(getCertificateReport).toHaveBeenCalledWith(expect.objectContaining({ gxp_type: "GSP", expiry_days: "30", number: "123", q: "hello", offset: 100 }), expect.anything(), true, null));
  expect(screen.getByLabelText("Loại GxP")).toHaveValue("GSP");
});
it("pushes applied change filters and restores them on Back and Forward", async () => {
  render(<MemoryRouter initialEntries={["/reports?report=change_requests"]}><History /><ReportsPage access={access} statusError={null} /></MemoryRouter>);
  await waitFor(() => expect(getChangeRequestReport).toHaveBeenCalled());
  fireEvent.change(screen.getByLabelText("Trạng thái thay đổi"), { target: { value: "received" } });
  fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
  await waitFor(() => expect(screen.getByTestId("url")).toHaveTextContent("state=received"));
  fireEvent.click(screen.getByRole("button", { name: "Back" }));
  await waitFor(() => expect(screen.getByLabelText("Trạng thái thay đổi")).toHaveValue(""));
  fireEvent.click(screen.getByRole("button", { name: "Forward" }));
  await waitFor(() => expect(screen.getByLabelText("Trạng thái thay đổi")).toHaveValue("received"));
});

it.each(["GMP", "GSP", "GDP"])("restores the %s certificate filter", async gxp => {
  render(<MemoryRouter initialEntries={[`/reports?report=certificates&gxp_type=${gxp}&expiry_days=`]}><ReportsPage access={access} statusError={null} /></MemoryRouter>);
  await waitFor(() => expect(getCertificateReport).toHaveBeenCalledWith(expect.objectContaining({ gxp_type: gxp, expiry_days: "" }), expect.anything(), true, null));
});
it.each(["30", "60", "90", ""])("restores expiry window %s", async expiry => {
  render(<MemoryRouter initialEntries={[`/reports?report=certificates&expiry_days=${expiry}`]}><ReportsPage access={access} statusError={null} /></MemoryRouter>);
  await waitFor(() => expect(getCertificateReport).toHaveBeenCalledWith(expect.objectContaining({ expiry_days: expiry }), expect.anything(), true, null));
});
it.each(["offset=-1", "offset=1", "offset=1.5", "offset=999999999999999999999", "gxp_type=WRONG", "expiry_days=45", `q=${"a".repeat(201)}`, "offset=0&offset=100"])("rejects invalid certificate URL %s before API access", async query => {
  render(<MemoryRouter initialEntries={[`/reports?report=certificates&${query}`]}><ReportsPage access={access} statusError={null} /></MemoryRouter>);
  expect(await screen.findByRole("alert")).toHaveTextContent("không hợp lệ");
  expect(getCertificateReport).not.toHaveBeenCalled();
});
it("rejects an invalid change state without a request", async () => {
  render(<MemoryRouter initialEntries={["/reports?report=change_requests&state=approved"]}><ReportsPage access={access} statusError={null} /></MemoryRouter>);
  expect(await screen.findByRole("alert")).toHaveTextContent("không hợp lệ");
  expect(getChangeRequestReport).not.toHaveBeenCalled();
});
it("ignores unknown URL parameters and switches kinds without carrying filters", async () => {
  render(<MemoryRouter initialEntries={["/reports?report=certificates&gxp_type=GDP&unknown=ignored"]}><History /><ReportsPage access={access} statusError={null} /></MemoryRouter>);
  await waitFor(() => expect(getCertificateReport).toHaveBeenCalledWith(expect.objectContaining({ gxp_type: "GDP" }), expect.anything(), true, null));
  fireEvent.change(screen.getByLabelText("Loại báo cáo"), { target: { value: "change_requests" } });
  await waitFor(() => expect(getChangeRequestReport).toHaveBeenCalledWith(expect.objectContaining({ state: "", q: "", offset: 0 }), expect.anything(), true, null));
  expect(screen.getByTestId("url")).toHaveTextContent("?report=change_requests");
  expect(screen.getByTestId("url")).not.toHaveTextContent("gxp_type");
});
it("pushes pagination, restores it on Back/Forward and resets it on filter submit", async () => {
  const row = { certificate_id: "id", certificate_version_id: "version", result_key: "key", site_id: "site", case_id: null, production_line_id: null, line_code: null, facility_name: "Cơ sở", company_name: "Công ty", gxp_type: "GMP", certificate_number: "Số", issue_date: null, expiry_date: null, lifecycle_state: null, status: "active" };
  const rows = Array.from({ length: 101 }, (_, n) => ({ ...row, certificate_id: `id-${n}`, result_key: `key-${n}` }));
  vi.mocked(getCertificateReport).mockImplementation(async f => { const offset = f?.offset ?? 0; return { items: rows.slice(offset, offset + 100), total_count: 101, offset, limit: 100 }; });
  render(<MemoryRouter initialEntries={["/reports?report=certificates"]}><History /><ReportsPage access={access} statusError={null} /></MemoryRouter>);
  await screen.findByText("Trang 1 / 2");
  fireEvent.click(screen.getByRole("button", { name: "Trang sau" }));
  expect(await screen.findByText("Trang 2 / 2")).toBeInTheDocument();
  expect(screen.getByTestId("url")).toHaveTextContent("offset=100");
  fireEvent.click(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByText("Trang 1 / 2")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Forward" }));
  expect(await screen.findByText("Trang 2 / 2")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Tìm kiếm"), { target: { value: "test" } });
  fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
  await waitFor(() => expect(screen.getByTestId("url")).not.toHaveTextContent("offset=100"));
});
it("exports applied URL filters, not an unsubmitted draft", async () => {
  vi.mocked(getCertificateReport).mockImplementation(async f => ({ items: [], total_count: 0, offset: 0, limit: f?.export ? 10000 : 100 }));
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:fixture") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<MemoryRouter initialEntries={["/reports?report=certificates&q=applied"]}><ReportsPage access={access} statusError={null} /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole("button", { name: /Xuất CSV/ })).toBeEnabled());
  fireEvent.change(screen.getByLabelText("Tìm kiếm"), { target: { value: "draft" } });
  fireEvent.click(screen.getByRole("button", { name: /Xuất CSV/ }));
  await waitFor(() => expect(getCertificateReport).toHaveBeenCalledWith(expect.objectContaining({ q: "applied", export: true }), expect.anything(), true, null));
  click.mockRestore();
});
it("does not download a pending export after the report URL changes", async () => {
  let resolveExport!: (value: Awaited<ReturnType<typeof getCertificateReport>>) => void;
  vi.mocked(getCertificateReport).mockImplementation(f => f?.export ? new Promise(resolve => { resolveExport = resolve; }) : Promise.resolve({ items: [], total_count: 0, offset: 0, limit: 100 }));
  const create = vi.fn(() => "blob:stale");
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
  function Controls() { const navigate = useNavigate(); return <button onClick={() => navigate("/reports?report=certificates&q=new")}>Change URL</button>; }
  render(<MemoryRouter initialEntries={["/reports?report=certificates&q=old"]}><Controls /><ReportsPage access={access} statusError={null} /></MemoryRouter>);
  await waitFor(() => expect(screen.getByRole("button", { name: /Xuất CSV/ })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: /Xuất CSV/ }));
  await waitFor(() => expect(resolveExport).toBeDefined());
  fireEvent.click(screen.getByRole("button", { name: "Change URL" }));
  await act(async () => resolveExport({ items: [], total_count: 0, offset: 0, limit: 10000 }));
  expect(create).not.toHaveBeenCalled();
});
it.each(["403", "404", "409"])("ignores a stale %s response across URL A → B → A", async code => {
  const pending: Array<{ resolve: (value: Awaited<ReturnType<typeof getCertificateReport>>) => void; reject: (error: Error) => void }> = [];
  vi.mocked(getCertificateReport).mockImplementation(() => new Promise((resolve, reject) => pending.push({ resolve, reject })));
  function Controls() { const navigate = useNavigate(); return <><button onClick={() => navigate("/reports?report=certificates&q=B")}>B</button><button onClick={() => navigate("/reports?report=certificates&q=A")}>A</button></>; }
  render(<MemoryRouter initialEntries={["/reports?report=certificates&q=A"]}><Controls /><ReportsPage access={access} statusError={null} /></MemoryRouter>);
  await waitFor(() => expect(pending).toHaveLength(1));
  fireEvent.click(screen.getByRole("button", { name: "B" }));
  await waitFor(() => expect(pending).toHaveLength(2));
  fireEvent.click(screen.getByRole("button", { name: "A" }));
  await waitFor(() => expect(pending).toHaveLength(3));
  await act(async () => { pending[2].resolve({ items: [], total_count: 0, offset: 0, limit: 100 }); });
  expect(await screen.findByText("Không có kết quả phù hợp.")).toBeInTheDocument();
  await act(async () => { pending[0].reject(new Error(`stale ${code}`)); pending[1].reject(new Error(`stale ${code}`)); });
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
