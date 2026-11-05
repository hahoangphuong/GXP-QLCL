import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import type { ApiAccess } from "../App";
import type { FacilitySearchResult } from "../types";
import { searchFacilities } from "../lib/api";
import { ReportsPage } from "./ReportsPage";

vi.mock("../lib/api", () => ({ searchFacilities: vi.fn() }));

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

  it("selects operational categories and sends backed filters for Case, change and expiry contexts", async () => {
    vi.mocked(searchFacilities).mockImplementation(async filters => ({
      items: [row(1)], offset: filters?.offset ?? 0, limit: filters?.limit ?? 100, total_count: 1,
    }));
    render(<MemoryRouter><ReportsPage access={access} statusError={null} /></MemoryRouter>);
    await screen.findByText("1 dòng kết quả");

    fireEvent.change(screen.getByLabelText("Loại báo cáo"), { target: { value: "inspection" } });
    fireEvent.submit(screen.getByRole("button", { name: "Áp dụng bộ lọc" }).closest("form")!);
    await waitFor(() => expect(vi.mocked(searchFacilities).mock.calls.some(([filters]) =>
      filters?.case_state?.join(",") === "planned,decision_issued,inspection_in_progress")).toBe(true));
    expect(screen.getByText(/Không suy ra lịch kiểm tra/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Giai đoạn kiểm tra"), { target: { value: "decision_issued" } });
    fireEvent.submit(screen.getByRole("button", { name: "Áp dụng bộ lọc" }).closest("form")!);
    await waitFor(() => expect(vi.mocked(searchFacilities).mock.calls.some(([filters]) =>
      filters?.case_state?.join(",") === "decision_issued")).toBe(true));

    fireEvent.change(screen.getByLabelText("Loại báo cáo"), { target: { value: "open_changes" } });
    fireEvent.submit(screen.getByRole("button", { name: "Áp dụng bộ lọc" }).closest("form")!);
    await waitFor(() => expect(vi.mocked(searchFacilities).mock.calls.some(([filters]) =>
      filters?.change_request_state?.join(",") === "received,under_review")).toBe(true));

    fireEvent.change(screen.getByLabelText("Loại báo cáo"), { target: { value: "expiring_certificates" } });
    fireEvent.change(screen.getByLabelText("Hết hạn trong"), { target: { value: "30" } });
    fireEvent.submit(screen.getByRole("button", { name: "Áp dụng bộ lọc" }).closest("form")!);
    await waitFor(() => expect(vi.mocked(searchFacilities).mock.calls.some(([filters]) =>
      filters?.certificate_expiring_within_days === 30 && filters.certificate_state === "active")).toBe(true));
    expect(screen.getByText(/API không định danh GCN khớp/)).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "GCN hiện hành (ngữ cảnh)" })).not.toBeInTheDocument();
  });

  it("does not query or expose report rows without authentication", () => {
    render(<MemoryRouter><ReportsPage access={{ ...access, canLoadSecureApi: false }} statusError={null} /></MemoryRouter>);
    expect(screen.getByText("Cần đăng nhập")).toBeInTheDocument();
    expect(vi.mocked(searchFacilities)).not.toHaveBeenCalled();
  });
});
