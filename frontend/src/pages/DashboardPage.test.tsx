import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
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
  it("drills actionable metric tiles into shareable canonical workflow queues", async () => {
    render(<MemoryRouter><DashboardPage access={access} statusError={null} /></MemoryRouter>);
    await screen.findByRole("heading", { name: "Bảng điều phối nghiệp vụ" });
    const expected = [
      ["Cơ sở có hồ sơ đang xử lý", "/workflow?queue=active"],
      ["Cơ sở chờ kiểm tra", "/workflow?queue=inspection"],
      ["Cơ sở chờ cấp chứng nhận", "/workflow?queue=certificate_decision"],
      ["Cơ sở có GCN sắp hết hạn 90 ngày", "/workflow?queue=expiring"],
      ["Cơ sở có thay đổi chưa hoàn tất", "/workflow?queue=change_requests"],
    ];
    for (const [label, href] of expected) {
      expect(screen.getByRole("link", { name: new RegExp(label) })).toHaveAttribute("href", href);
    }
    expect(screen.getByRole("link", { name: /Tổng số cơ sở/ })).toHaveAttribute("href", "/search");
    expect(screen.getByRole("link", { name: /Cơ sở có GCN còn hiệu lực/ })).toHaveAttribute("href", "/search?certificate_state=active");
    expect(screen.getByText(/thẻ thống kê đếm cơ sở/i)).toBeInTheDocument();
  });

  it.each([
    ["negative site count", { total_facilities: -1 }],
    ["fractional Case count", { total_cases: 1.5 }],
    ["more active Sites than total Sites", { active_cases: 3 }],
    ["queue length larger than total Cases", { total_cases: 0 }],
    ["duplicate Case UUID", { total_cases: 2, queue: [summary.queue[0], { ...summary.queue[0] }] }],
    ["missing Site UUID", { queue: [{ ...summary.queue[0], site_id: "" }] }],
    ["missing Case identity", { queue: [{ ...summary.queue[0], case_id: "" }] }],
    ["missing Case state", { queue: [{ ...summary.queue[0], state: "" }] }],
  ])("rejects %s before showing any Dashboard metrics or Case/document links", async (_name, changes) => {
    vi.mocked(getDashboardSummary).mockResolvedValue({ ...summary, ...changes });
    render(<MemoryRouter><DashboardPage access={access} statusError={null} /></MemoryRouter>);
    expect(await screen.findByText(/API trả về (thống kê|hàng đợi) Dashboard|Hàng đợi Dashboard thiếu/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "KT-2026" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Xem tài liệu" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Tổng số cơ sở/ })).not.toBeInTheDocument();
  });

  it("accepts distinct Cases at the same Site without falsely classifying them as duplicates", async () => {
    vi.mocked(getDashboardSummary).mockResolvedValue({
      ...summary, total_cases: 2,
      queue: [summary.queue[0], { ...summary.queue[0], case_id: "case-two", reference_code: "KT-2" }],
    });
    render(<MemoryRouter><DashboardPage access={access} statusError={null} /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "KT-2026" })).toHaveAttribute("href", "/cases/case%25%2Fuuid");
    expect(screen.getByRole("link", { name: "KT-2" })).toHaveAttribute("href", "/cases/case-two");
    expect(screen.getAllByRole("link", { name: "Xem tài liệu" })).toHaveLength(2);
  });

  it("does not publish an older summary after credential generation changes", async () => {
    let resolveOld: (value: DashboardSummary) => void = () => {};
    vi.mocked(getDashboardSummary)
      .mockImplementationOnce(() => new Promise<DashboardSummary>(resolve => { resolveOld = resolve; }))
      .mockResolvedValueOnce({ ...summary, queue: [{ ...summary.queue[0], case_id: "new-case", reference_code: "NEW" }] });
    const { rerender } = render(<MemoryRouter><DashboardPage access={access} statusError={null} /></MemoryRouter>);
    rerender(<MemoryRouter><DashboardPage access={{ ...access, accessGeneration: 2 }} statusError={null} /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "NEW" })).toHaveAttribute("href", "/cases/new-case");
    resolveOld(summary);
    await waitFor(() => expect(screen.queryByRole("link", { name: "KT-2026" })).not.toBeInTheDocument());
    expect(screen.getByRole("link", { name: "NEW" })).toBeInTheDocument();
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
