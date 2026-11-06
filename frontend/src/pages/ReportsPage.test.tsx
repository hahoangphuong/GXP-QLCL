import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import type { ApiAccess } from "../App";
import type { FacilitySearchPage, FacilitySearchResult } from "../types";
import { searchFacilities } from "../lib/api";
import { ReportsPage } from "./ReportsPage";

vi.mock("../lib/api", () => ({ searchFacilities: vi.fn() }));
vi.mock("../features/reports/CaseReport", () => ({
  CaseReport: ({ showDocumentsLink, inspectionQueue, initialState }: { showDocumentsLink?: boolean; inspectionQueue: boolean; initialState?: string }) =>
    <output data-testid="cases-report">{inspectionQueue ? "inspection" : "cases"}:{String(showDocumentsLink)}:{initialState ?? ""}</output>,
}));
vi.mock("../features/reports/CanonicalRecordReport", () => ({
  CanonicalRecordReport: ({ kind, showDocumentsLink }: { kind: string; showDocumentsLink?: boolean }) =>
    <output data-testid="canonical-report">{kind}:{String(showDocumentsLink)}</output>,
}));

const access: ApiAccess = {
  auth: { username: "report-test", role: "reader" },
  useStubAuth: true,
  bearerToken: null,
  canLoadSecureApi: true,
  accessGeneration: 1,
};

function row(n: number): FacilitySearchResult {
  return {
    result_key: "result-" + n, site_id: "site-" + n, legacy_site_id: n,
    facility_code: "F" + n, context_code: null, result_grain: "facility",
    gxp_type: "GMP", line_code: null, facility_name: "Cơ sở " + n,
    company_name: "Công ty " + n, gxp_types: ["GMP"],
    certificate_scope_summary: null, province_name: "Hà Nội",
    last_inspection_on: null, current_state: "planned",
    current_certificate_number: "GCN " + n, current_certificate_expiry: null,
  };
}

beforeEach(() => vi.mocked(searchFacilities).mockReset());

function NavigationHistory() {
  const location = useLocation();
  const navigate = useNavigate();
  return <>
    <output data-testid="report-url">{location.pathname + location.search}</output>
    <button type="button" onClick={() => navigate(-1)}>Lùi lịch sử</button>
    <button type="button" onClick={() => navigate(1)}>Tiến lịch sử</button>
    <button type="button" onClick={() =>
      navigate("/reports?report=cases&case_state=awaiting_certificate_decision")}>Mở trực tiếp Case chờ cấp</button>
  </>;
}

describe("ReportsPage operator workflow", () => {
  it("shows real authorized results, pages and navigates to matching facility context", async () => {
    const all = Array.from({ length: 101 }, (_, n) => row(n));
    vi.mocked(searchFacilities).mockImplementation(async filters => {
      const offset = filters?.offset ?? 0;
      const limit = filters?.limit ?? 100;
      return { items: all.slice(offset, offset + limit), offset, limit, total_count: all.length };
    });
    render(<MemoryRouter><ReportsPage access={access} statusError={null} /></MemoryRouter>);

    expect(await screen.findByText("101 dòng kết quả")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cơ sở 0" })).toHaveAttribute("href", expect.stringContaining("result_key=result-0"));
    fireEvent.click(screen.getByRole("button", { name: "Trang sau" }));
    expect(await screen.findByRole("link", { name: "Cơ sở 100" })).toBeInTheDocument();
    expect(screen.getByText("Trang 2 / 2")).toBeInTheDocument();
    expect(vi.mocked(searchFacilities).mock.calls.some(([filters]) => filters?.offset === 100)).toBe(true);

    fireEvent.change(screen.getByLabelText("Loại GxP"), { target: { value: "GLP" } });
    fireEvent.submit(screen.getByRole("button", { name: "Áp dụng bộ lọc" }).closest("form")!);
    await waitFor(() => expect(vi.mocked(searchFacilities).mock.calls.some(([filters]) =>
      filters?.gxp_type === "GLP" && filters.offset === 0)).toBe(true));
  });

  it.each([
    ["wrong offset", { offset: 10 }],
    ["duplicate result_key", { items: [row(0), { ...row(0) }], total_count: 2 }],
    ["missing Site UUID", { items: [{ ...row(0), site_id: "" }] }],
    ["missing result_key", { items: [{ ...row(0), result_key: "" }] }],
    ["inconsistent count", { total_count: 0 }],
    ["underfilled first page", { total_count: 2 }],
    ["wrong limit", { limit: 200 }],
  ])("refuses %s before displaying clickable facility result", async (_name, change) => {
    vi.mocked(searchFacilities).mockResolvedValue({
      items: [row(0)], total_count: 1, offset: 0, limit: 100, ...change,
    });
    render(<MemoryRouter><ReportsPage access={access} statusError={null} /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent(/phân trang|định danh|Site/);
    expect(screen.queryByRole("link", { name: "Cơ sở 0" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Xuất CSV (Excel)" })).toBeDisabled();
  });

  it("does not display a stale first page after the next page reports the wrong offset", async () => {
    const first = Array.from({ length: 100 }, (_, n) => row(n));
    vi.mocked(searchFacilities).mockImplementation(async filters => ({
      items: filters?.offset === 100 ? [row(100)] : first,
      total_count: 101, offset: 0, limit: 100,
    }));
    render(<MemoryRouter><ReportsPage access={access} statusError={null} /></MemoryRouter>);
    expect(await screen.findByText("101 dòng kết quả")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Trang sau" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("phân trang");
    expect(screen.queryByRole("link", { name: "Cơ sở 0" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Cơ sở 100" })).not.toBeInTheDocument();
  });

  it("provides canonical document links for Case and Change Request reports only", () => {
    vi.mocked(searchFacilities).mockResolvedValue({ items: [], total_count: 0, offset: 0, limit: 100 });
    render(<MemoryRouter><ReportsPage access={access} statusError={null} /></MemoryRouter>);
    const select = screen.getByLabelText("Loại báo cáo");
    fireEvent.change(select, { target: { value: "cases" } });
    expect(screen.getByTestId("cases-report")).toHaveTextContent("cases:true");
    fireEvent.change(select, { target: { value: "inspection" } });
    expect(screen.getByTestId("cases-report")).toHaveTextContent("inspection:true");
    fireEvent.change(select, { target: { value: "change_requests" } });
    expect(screen.getByTestId("canonical-report")).toHaveTextContent("change_requests:true");
    fireEvent.change(select, { target: { value: "certificates" } });
    expect(screen.getByTestId("canonical-report")).toHaveTextContent("certificates:false");
  });

  it("restores bookmarked report selections, including non-facility reports", () => {
    const first = render(<MemoryRouter initialEntries={["/reports?report=change_requests"]}>
      <ReportsPage access={access} statusError={null} />
    </MemoryRouter>);
    expect(screen.getByLabelText("Loại báo cáo")).toHaveValue("change_requests");
    expect(screen.getByTestId("canonical-report")).toHaveTextContent("change_requests:true");
    expect(searchFacilities).not.toHaveBeenCalled();
    first.unmount();
    render(<MemoryRouter initialEntries={["/reports?report=inspection"]}>
      <ReportsPage access={access} statusError={null} />
    </MemoryRouter>);
    expect(screen.getByTestId("cases-report")).toHaveTextContent("inspection:true");
  });

  it("synchronizes report selection with URL history without losing unrelated query params", () => {
    vi.mocked(searchFacilities).mockResolvedValue({ items: [], offset: 0, limit: 100, total_count: 0 });
    render(<MemoryRouter initialEntries={["/reports?source=workflow&report=cases"]}>
      <ReportsPage access={access} statusError={null} /><NavigationHistory />
    </MemoryRouter>);
    expect(screen.getByTestId("cases-report")).toHaveTextContent("cases:true");
    fireEvent.change(screen.getByLabelText("Loại báo cáo"), { target: { value: "certificates" } });
    expect(screen.getByTestId("canonical-report")).toHaveTextContent("certificates:false");
    expect(screen.getByTestId("report-url")).toHaveTextContent("source=workflow");
    expect(screen.getByTestId("report-url")).toHaveTextContent("report=certificates");
    fireEvent.click(screen.getByRole("button", { name: "Lùi lịch sử" }));
    expect(screen.getByTestId("cases-report")).toHaveTextContent("cases:true");
    fireEvent.click(screen.getByRole("button", { name: "Tiến lịch sử" }));
    expect(screen.getByTestId("canonical-report")).toHaveTextContent("certificates:false");
  });

  it("uses the certificate-decision Case filter only from its explicit supported URL", () => {
    const first = render(<MemoryRouter initialEntries={["/reports?report=cases&case_state=awaiting_certificate_decision"]}>
      <ReportsPage access={access} statusError={null} />
    </MemoryRouter>);
    expect(screen.getByTestId("cases-report")).toHaveTextContent("cases:true:awaiting_certificate_decision");
    first.unmount();
    const second = render(<MemoryRouter initialEntries={["/reports?report=cases&case_state=unknown"]}>
      <ReportsPage access={access} statusError={null} />
    </MemoryRouter>);
    expect(screen.getByTestId("cases-report")).toHaveTextContent("cases:true:");
    expect(screen.getByTestId("cases-report")).not.toHaveTextContent("unknown");
    second.unmount();
  });

  it("resolves a same-page Case URL change to the new initial filter and restores browser history", () => {
    render(<MemoryRouter initialEntries={["/reports?report=cases"]}>
      <ReportsPage access={access} statusError={null} /><NavigationHistory />
    </MemoryRouter>);
    expect(screen.getByTestId("cases-report")).toHaveTextContent("cases:true:");
    fireEvent.click(screen.getByRole("button", { name: "Mở trực tiếp Case chờ cấp" }));
    expect(screen.getByTestId("cases-report")).toHaveTextContent("cases:true:awaiting_certificate_decision");
    fireEvent.click(screen.getByRole("button", { name: "Lùi lịch sử" }));
    expect(screen.getByTestId("cases-report")).not.toHaveTextContent("awaiting_certificate_decision");
  });

  it("clears a stale Case-specific filter when manually switching report categories", () => {
    vi.mocked(searchFacilities).mockResolvedValue({ items: [], offset: 0, limit: 100, total_count: 0 });
    render(<MemoryRouter initialEntries={["/reports?report=cases&case_state=awaiting_certificate_decision"]}>
      <ReportsPage access={access} statusError={null} /><NavigationHistory />
    </MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Loại báo cáo"), { target: { value: "certificates" } });
    expect(screen.getByTestId("report-url")).not.toHaveTextContent("case_state=");
    fireEvent.change(screen.getByLabelText("Loại báo cáo"), { target: { value: "cases" } });
    expect(screen.getByTestId("cases-report")).toHaveTextContent("cases:true:");
    expect(screen.getByTestId("cases-report")).not.toHaveTextContent("awaiting_certificate_decision");
  });

  it("rejects an unknown or duplicated report type before fetching", async () => {
    vi.mocked(searchFacilities).mockResolvedValue({ items: [], offset: 0, limit: 100, total_count: 0 });
    render(<MemoryRouter initialEntries={["/reports?report=GSP&report=cases"]}>
      <ReportsPage access={access} statusError={null} />
    </MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("không hợp lệ");
    expect(searchFacilities).not.toHaveBeenCalled();
    expect(screen.queryByTestId("cases-report")).not.toBeInTheDocument();
  });

  it("does not query or expose report rows without authentication", () => {
    render(<MemoryRouter><ReportsPage access={{ ...access, canLoadSecureApi: false }} statusError={null} /></MemoryRouter>);
    expect(screen.getByText("Cần đăng nhập")).toBeInTheDocument();
    expect(vi.mocked(searchFacilities)).not.toHaveBeenCalled();
  });

  it("restores facility report filters and pagination from a bookmark", async () => {
    vi.mocked(searchFacilities).mockImplementation(async filters => ({
      items: [row(100)], offset: filters?.offset ?? 0, limit: 100, total_count: 101,
    }));
    render(<MemoryRouter initialEntries={["/reports?report=facilities&gxp_type=GLP&q=H%C3%A0&province=HN&offset=100"]}>
      <ReportsPage access={access} statusError={null} /><NavigationHistory />
    </MemoryRouter>);
    expect(await screen.findByText("101 dòng kết quả")).toBeInTheDocument();
    expect(screen.getByLabelText("Loại GxP")).toHaveValue("GLP");
    expect(screen.getByLabelText("Từ khóa")).toHaveValue("Hà");
    expect(screen.getByLabelText("Tỉnh/thành")).toHaveValue("HN");
    expect(screen.getByText("Trang 2 / 2")).toBeInTheDocument();
    expect(vi.mocked(searchFacilities).mock.calls.every(([filters]) =>
      filters?.gxp_type === "GLP" && filters?.q === "Hà" && filters?.province === "HN" && filters?.offset === 100)).toBe(true);
  });

  it("does not fetch invalid facility report bookmarks", () => {
    render(<MemoryRouter initialEntries={["/reports?report=facilities&offset=101"]}>
      <ReportsPage access={access} statusError={null} />
    </MemoryRouter>);
    expect(screen.getByRole("alert")).toHaveTextContent("URL báo cáo cơ sở không hợp lệ");
    expect(vi.mocked(searchFacilities)).not.toHaveBeenCalled();
  });

  it("keeps unsubmitted facility drafts separate from applied URL filters and restores history", async () => {
    vi.mocked(searchFacilities).mockResolvedValue({ items: [], offset: 0, limit: 100, total_count: 0 });
    render(<MemoryRouter initialEntries={["/reports?report=facilities"]}>
      <ReportsPage access={access} statusError={null} /><NavigationHistory />
    </MemoryRouter>);
    await screen.findByText("0 dòng kết quả");
    fireEvent.change(screen.getByLabelText("Loại GxP"), { target: { value: "GLP" } });
    expect(screen.getByTestId("report-url")).not.toHaveTextContent("gxp_type=GLP");
    fireEvent.submit(screen.getByRole("button", { name: "Áp dụng bộ lọc" }).closest("form")!);
    await waitFor(() => expect(screen.getByTestId("report-url")).toHaveTextContent("gxp_type=GLP"));
    fireEvent.change(screen.getByLabelText("Loại GxP"), { target: { value: "GMPbb" } });
    expect(screen.getByTestId("report-url")).not.toHaveTextContent("GMPbb");
    fireEvent.click(screen.getByRole("button", { name: "Lùi lịch sử" }));
    expect(screen.getByLabelText("Loại GxP")).toHaveValue("GMP");
    fireEvent.click(screen.getByRole("button", { name: "Tiến lịch sử" }));
    expect(screen.getByLabelText("Loại GxP")).toHaveValue("GLP");
  });

  it("does not generate a facility CSV from a late export after changing report", async () => {
    let releaseExport: ((page: { items: FacilitySearchResult[]; offset: number; limit: number; total_count: number }) => void) | undefined;
    vi.mocked(searchFacilities)
      .mockResolvedValueOnce({ items: [row(0)], offset: 0, limit: 100, total_count: 1 })
      .mockImplementationOnce(() => new Promise<FacilitySearchPage>(resolve => { releaseExport = resolve; }));
    const oldCreate = URL.createObjectURL;
    const create = vi.fn(() => "blob:report-test");
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
    try {
      render(<MemoryRouter initialEntries={["/reports?report=facilities"]}>
        <ReportsPage access={access} statusError={null} /><NavigationHistory />
      </MemoryRouter>);
      await screen.findByText("1 dòng kết quả");
      fireEvent.click(screen.getByRole("button", { name: "Xuất CSV (Excel)" }));
      await waitFor(() => expect(releaseExport).toBeDefined());
      fireEvent.change(screen.getByLabelText("Loại báo cáo"), { target: { value: "cases" } });
      releaseExport!({ items: [row(0)], offset: 0, limit: 100, total_count: 1 });
      await waitFor(() => expect(screen.getByTestId("cases-report")).toBeInTheDocument());
      expect(create).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(URL, "createObjectURL", { configurable: true, value: oldCreate });
    }
  });
});
