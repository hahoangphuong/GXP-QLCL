import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../App";
import { getDashboardSummary } from "../lib/api";
import type { DashboardSummary } from "../types";
import { DashboardPage } from "./DashboardPage";

vi.mock("../lib/api", () => ({ getDashboardSummary: vi.fn() }));

const access: ApiAccess = { auth: { username: "reader", role: "reader" },
  useStubAuth: true, bearerToken: null, canLoadSecureApi: true, accessGeneration: 1 };
const summary: DashboardSummary = {
  total_facilities: 2, total_cases: 1, active_cases: 1, waiting_inspection: 1,
  waiting_certificate_decision: 0, active_certificates: 0,
  expiring_certificates_90_days: 0, incomplete_changes: 0,
  queue: [{ case_id: "case%/uuid", site_id: "stale-site", result_key: "stale:result",
    facility_name: "Cơ sở A", company_name: "Công ty A", gxp_type: "GMP",
    state: "planned", reference_code: "KT-2026", opened_year: 2026 }],
};
beforeEach(() => vi.mocked(getDashboardSummary).mockReset().mockResolvedValue(summary));

describe("dashboard canonical Case queue", () => {
  it("routes Case and documents by UUID instead of stale Site/line projections", async () => {
    render(<MemoryRouter><DashboardPage access={access} statusError={null} /></MemoryRouter>);
    const link = await screen.findByRole("link", { name: "KT-2026" });
    expect(link).toHaveAttribute("href", "/cases/case%25%2Fuuid");
    expect(link.getAttribute("href")).not.toContain("stale-site");
    expect(screen.getByRole("link", { name: "Xem tài liệu" })).toHaveAttribute("href", "/documents/cases/case%25%2Fuuid");
    expect(screen.getByRole("link", { name: "Mở Bàn công việc" })).toHaveAttribute("href", "/workflow");
  });
  it("does not fetch secure queue or show document links without access", () => {
    render(<MemoryRouter><DashboardPage access={{ ...access, canLoadSecureApi: false }} statusError={null} /></MemoryRouter>);
    expect(screen.getByText("Cần đăng nhập")).toBeInTheDocument();
    expect(getDashboardSummary).not.toHaveBeenCalled();
    expect(screen.queryByRole("link", { name: "Xem tài liệu" })).not.toBeInTheDocument();
  });
  it("does not render document actions for an empty queue", async () => {
    vi.mocked(getDashboardSummary).mockResolvedValue({ ...summary, queue: [] });
    render(<MemoryRouter><DashboardPage access={access} statusError={null} /></MemoryRouter>);
    expect(await screen.findByText(/Hiện chưa có hồ sơ đang mở/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Xem tài liệu" })).not.toBeInTheDocument();
  });
});
