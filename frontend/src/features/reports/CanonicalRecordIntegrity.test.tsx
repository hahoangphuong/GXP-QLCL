import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../../App";
import { getCertificateReport, getChangeRequestReport } from "../../lib/api";
import { CanonicalRecordReport } from "./CanonicalRecordReport";

vi.mock("../../lib/api", () => ({ getCertificateReport: vi.fn(), getChangeRequestReport: vi.fn() }));
const access: ApiAccess = { auth: { username: "reader", role: "reader" }, useStubAuth: true, bearerToken: null, canLoadSecureApi: true, accessGeneration: 1 };
const certificate = { certificate_id: "cert-a", certificate_version_id: "version-a", site_id: "site-a", result_key: "site-a:GMP:facility_wide:", case_id: null, production_line_id: null, line_code: null, facility_name: "Cơ sở", company_name: "Công ty", gxp_type: "GMP", certificate_number: "GCN-A", issue_date: null, expiry_date: null, lifecycle_state: "GRANTED", status: "active" };
const change = { change_request_id: "change-a", site_id: "site-a", legacy_change_request_id: 1, facility_name: "Cơ sở", company_name: "Công ty", scope_label: null, description: null, submitted_on: null, requester_name: null, state: "received" };
beforeEach(() => { vi.mocked(getCertificateReport).mockReset(); vi.mocked(getChangeRequestReport).mockReset(); });
describe("canonical report page integrity", () => {
  it.each([
    ["wrong offset", { items: [certificate], total_count: 1, limit: 100, offset: 1 }],
    ["missing site", { items: [{ ...certificate, site_id: "" }], total_count: 1, limit: 100, offset: 0 }],
    ["missing version", { items: [{ ...certificate, certificate_version_id: "" }], total_count: 1, limit: 100, offset: 0 }],
    ["duplicate", { items: [certificate, certificate], total_count: 2, limit: 100, offset: 0 }],
    ["underfilled", { items: [certificate], total_count: 101, limit: 100, offset: 0 }],
    ["invalid limit", { items: [certificate], total_count: 1, limit: 99, offset: 0 }],
    ["negative total", { items: [], total_count: -1, limit: 100, offset: 0 }],
    ["empty middle page", { items: [], total_count: 1, limit: 100, offset: 0 }],
    ["missing identity", { items: [{ ...certificate, certificate_id: "" }], total_count: 1, limit: 100, offset: 0 }],
    ["unknown status", { items: [{ ...certificate, status: "unknown" }], total_count: 1, limit: 100, offset: 0 }],
  ])("rejects %s without creating links or export", async (_name, page) => {
    vi.mocked(getCertificateReport).mockResolvedValue(page);
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "GCN-A" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Xem metadata" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Xuất CSV/ })).toBeDisabled();
  });
  it("rejects duplicate Change Request identity", async () => {
    vi.mocked(getChangeRequestReport).mockResolvedValue({ items: [change, change], total_count: 2, limit: 100, offset: 0 });
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="change_requests" showDocumentsLink /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "1" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Xem tài liệu" })).not.toBeInTheDocument();
  });
  it("allows distinct certificates sharing a Site", async () => {
    vi.mocked(getCertificateReport).mockResolvedValue({ items: [certificate, { ...certificate, certificate_id: "cert-b", certificate_version_id: "version-b", certificate_number: "GCN-B" }], total_count: 2, limit: 100, offset: 0 });
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "GCN-A" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "GCN-B" })).toBeInTheDocument();
  });
  it("rejects a wrong GxP filter and number filter without links", async () => {
    vi.mocked(getCertificateReport).mockResolvedValue({ items: [certificate], total_count: 1, limit: 100, offset: 0 });
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    await screen.findByRole("link", { name: "GCN-A" });
    fireEvent.change(screen.getByLabelText("Loại GxP"), { target: { value: "GLP" } });
    fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "GCN-A" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Loại GxP"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Số GCN"), { target: { value: "WRONG" } });
    fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Số chứng nhận");
    expect(screen.queryByRole("link", { name: "GCN-A" })).not.toBeInTheDocument();
  });
  it("rejects a wrong Change Request state", async () => {
    vi.mocked(getChangeRequestReport).mockResolvedValue({ items: [change], total_count: 1, limit: 100, offset: 0 });
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="change_requests" /></MemoryRouter>);
    await screen.findByRole("link", { name: "1" });
    fireEvent.change(screen.getByLabelText("Trạng thái thay đổi"), { target: { value: "under_review" } });
    fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "1" })).not.toBeInTheDocument();
  });
  it("does not resurrect A or its late response during A to B to A", async () => {
    type Page = Awaited<ReturnType<typeof getCertificateReport>>;
    let finishB!: (page: Page) => void;
    let finishA!: (page: Page) => void;
    const page = { items: [certificate], total_count: 1, limit: 100, offset: 0 };
    vi.mocked(getCertificateReport).mockResolvedValueOnce(page)
      .mockImplementationOnce(() => new Promise(resolve => { finishB = resolve; }))
      .mockImplementationOnce(() => new Promise(resolve => { finishA = resolve; }));
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    await screen.findByRole("link", { name: "GCN-A" });
    fireEvent.change(screen.getByLabelText("Tìm kiếm"), { target: { value: "B" } });
    fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
    await waitFor(() => expect(finishB).toBeDefined());
    expect(screen.queryByRole("link", { name: "GCN-A" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Tìm kiếm"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
    await waitFor(() => expect(finishA).toBeDefined());
    expect(screen.queryByRole("link", { name: "GCN-A" })).not.toBeInTheDocument();
    await act(async () => finishB({ ...page, items: [{ ...certificate, certificate_number: "STALE-B" }] }));
    expect(screen.queryByRole("link", { name: "STALE-B" })).not.toBeInTheDocument();
    await act(async () => finishA(page));
    expect(await screen.findByRole("link", { name: "GCN-A" })).toBeInTheDocument();
  });
  it("rejects incomplete export without download and permits a later complete export", async () => {
    const create = vi.fn(() => "blob:report");
    const revoke = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    vi.mocked(getCertificateReport)
      .mockResolvedValueOnce({ items: [certificate], total_count: 1, limit: 100, offset: 0 })
      .mockResolvedValueOnce({ items: [certificate], total_count: 2, limit: 10000, offset: 0 })
      .mockResolvedValueOnce({ items: [certificate], total_count: 1, limit: 10000, offset: 0 });
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    await screen.findByRole("link", { name: "GCN-A" });
    fireEvent.click(screen.getByRole("button", { name: /Xuất CSV/ }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
    expect(click).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Xuất CSV/ }));
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(click).toHaveBeenCalledTimes(1);
    expect(revoke).toHaveBeenCalledWith("blob:report");
    click.mockRestore();
  });
  it("does not download an export resolved after access changes", async () => {
    type Page = Awaited<ReturnType<typeof getCertificateReport>>;
    let finish!: (page: Page) => void;
    const create = vi.fn(() => "blob:stale");
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
    vi.mocked(getCertificateReport).mockResolvedValueOnce({ items: [certificate], total_count: 1, limit: 100, offset: 0 })
      .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const view = render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    await screen.findByRole("link", { name: "GCN-A" });
    fireEvent.click(screen.getByRole("button", { name: /Xuất CSV/ }));
    await waitFor(() => expect(finish).toBeDefined());
    view.rerender(<MemoryRouter><CanonicalRecordReport access={{ ...access, canLoadSecureApi: false, accessGeneration: 2 }} kind="certificates" /></MemoryRouter>);
    await act(async () => finish({ items: [certificate], total_count: 1, limit: 10000, offset: 0 }));
    expect(create).not.toHaveBeenCalled();
    expect(screen.getByText("Cần đăng nhập để xem báo cáo.")).toBeInTheDocument();
  });
  it.each([
    ["duplicate", [certificate, certificate]],
    ["missing Site", [{ ...certificate, site_id: "" }]],
    ["missing version", [{ ...certificate, certificate_version_id: "" }]],
  ])("blocks %s during export", async (_name, items) => {
    const create = vi.fn(() => "blob:invalid");
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
    vi.mocked(getCertificateReport)
      .mockResolvedValueOnce({ items: [certificate], total_count: 1, limit: 100, offset: 0 })
      .mockResolvedValueOnce({ items, total_count: items.length, limit: 10000, offset: 0 });
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    await screen.findByText("GCN-A");
    fireEvent.click(screen.getByRole("button", { name: /Xuất CSV/ }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });
  it("exports a BOM and neutralizes spreadsheet formula values", async () => {
    let output: Blob | undefined;
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn((blob: Blob) => { output = blob; return "blob:safe"; }) });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const formula = { ...certificate, facility_name: "=SUM(A1:A2)" };
    vi.mocked(getCertificateReport)
      .mockResolvedValueOnce({ items: [formula], total_count: 1, limit: 100, offset: 0 })
      .mockResolvedValueOnce({ items: [formula], total_count: 1, limit: 10000, offset: 0 });
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    await screen.findByText("=SUM(A1:A2)");
    fireEvent.click(screen.getByRole("button", { name: /Xuất CSV/ }));
    await waitFor(() => expect(output).toBeDefined());
    const text = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsText(output!); });
    expect(text).toContain("\"'=SUM(A1:A2)\"");
    const bytes = await new Promise<ArrayBuffer>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result as ArrayBuffer); reader.onerror = reject; reader.readAsArrayBuffer(output!); });
    expect(Array.from(new Uint8Array(bytes).slice(0, 3))).toEqual([0xef, 0xbb, 0xbf]);
    click.mockRestore();
  });
  it("pages through distinct rows without rejecting a shared Site", async () => {
    const first = Array.from({ length: 100 }, (_, index) => ({ ...certificate, certificate_id: `cert-${index}`, certificate_version_id: `version-${index}`, certificate_number: `GCN-${index}` }));
    vi.mocked(getCertificateReport).mockImplementation(async filters => filters.offset === 100
      ? { items: [{ ...certificate, certificate_id: "last", certificate_number: "GCN-LAST" }], total_count: 101, limit: 100, offset: 100 }
      : { items: first, total_count: 101, limit: 100, offset: 0 });
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    await screen.findByText("GCN-0");
    fireEvent.click(screen.getByText("Trang sau"));
    expect(await screen.findByText("GCN-LAST")).toBeInTheDocument();
    expect(screen.queryByText("GCN-0")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Trang trước"));
    expect(await screen.findByText("GCN-0")).toBeInTheDocument();
  });
  it("does not reject a backend text match or SQL wildcard based on visible fields", async () => {
    vi.mocked(getCertificateReport).mockResolvedValue({ items: [certificate], total_count: 1, limit: 100, offset: 0 });
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    await screen.findByRole("link", { name: "GCN-A" });
    fireEvent.change(screen.getByLabelText("Tìm kiếm"), { target: { value: "other backend text" } });
    fireEvent.change(screen.getByLabelText("Số GCN"), { target: { value: "GCN_%" } });
    fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
    expect(await screen.findByRole("link", { name: "GCN-A" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("ignores late authorization errors after the report kind changes", async () => {
    let reject!: (error: Error) => void;
    vi.mocked(getCertificateReport).mockImplementation(() => new Promise((_resolve, fail) => { reject = fail; }));
    vi.mocked(getChangeRequestReport).mockResolvedValue({ items: [change], total_count: 1, limit: 100, offset: 0 });
    const view = render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    await waitFor(() => expect(reject).toBeDefined());
    view.rerender(<MemoryRouter><CanonicalRecordReport access={access} kind="change_requests" /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "1" })).toBeInTheDocument();
    await act(async () => reject(new Error("403 stale")));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "1" })).toBeInTheDocument();
  });
});
