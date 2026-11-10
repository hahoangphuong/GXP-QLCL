import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../../App";
import { getChangeRequestWorkspace, getGxpCertificateDetail, getGxpCertificateVersionHistory } from "../../lib/api";
import { ReportRecordDetail } from "./ReportRecordDetail";

vi.mock("../../lib/api", () => ({ getGxpCertificateDetail: vi.fn(), getChangeRequestWorkspace: vi.fn(), getGxpCertificateVersionHistory: vi.fn() }));

const access: ApiAccess = { auth: { username: "reader", role: "reader" },
  useStubAuth: true, bearerToken: null, canLoadSecureApi: true, accessGeneration: 1 };

function mount(route: string) {
  return render(<MemoryRouter initialEntries={[route]}><Routes>
    <Route path="/reports/certificates/:certificateId" element={<ReportRecordDetail access={access} kind="certificates" />} />
    <Route path="/reports/change-requests/:changeRequestId" element={<ReportRecordDetail access={access} kind="change_requests" />} />
    <Route path="/search" element={<LocationCapture />} />
  </Routes></MemoryRouter>);
}

function LocationCapture() { return <p>{useLocation().search}</p>; }

const storedGspHistory: Awaited<ReturnType<typeof getGxpCertificateVersionHistory>> = {
  certificate_id: "cert-uuid", site_id: "site-uuid", case_id: null, certificate_type: "GSP",
  issuance_basis: "legacy_import", aggregate_latest_flag: false, latest_version_id: "version-gsp-2",
  versions: [2, 1].map(n => ({
    certificate_version_id: `version-gsp-${n}`, version_no: n, row_version: 3,
    is_latest_version: n === 2, lifecycle_state: null, certificate_number: `GSP-${n}`,
    issue_date: null, expiry_date: null, applicable_standard: null, issuing_authority: null,
    scope_summary: `Phạm vi lần ${n}`, scopes: [{
      id: `scope-gsp-${n}`, scope_key: null, scope_text: `Bảo quản GSP lần ${n}`, language_code: "vi", sort_order: 0,
    }],
  })),
};

beforeEach(() => {
  vi.mocked(getGxpCertificateDetail).mockReset();
  vi.mocked(getChangeRequestWorkspace).mockReset();
  vi.mocked(getGxpCertificateVersionHistory).mockReset();
  vi.mocked(getGxpCertificateVersionHistory).mockResolvedValue(storedGspHistory);
});

describe("authorized canonical detail navigation", () => {
  it("returns to the exact report context supplied by an internal navigation", async () => {
    vi.mocked(getChangeRequestWorkspace).mockResolvedValue({ id: "change-uuid", site_id: "site-uuid", facility_name: "Cơ sở", company_name: "Công ty", scope_label: "Đổi tên", state: "received" } as Awaited<ReturnType<typeof getChangeRequestWorkspace>>);
    render(<MemoryRouter initialEntries={[{ pathname: "/reports/change-requests/change-uuid", state: { reportReturn: "/reports?report=change_requests&state=received&offset=100" } }]}><Routes><Route path="/reports/change-requests/:changeRequestId" element={<ReportRecordDetail access={access} kind="change_requests" />} /></Routes></MemoryRouter>);
    expect(await screen.findByText("change-uuid")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Quay lại Báo cáo" })).toHaveAttribute("href", "/reports?report=change_requests&state=received&offset=100");
  });
  it.each(["GMP", "GLP", "GMPbb"])("redirects a matching %s Certificate to its existing workspace with UUID", async (type) => {
    vi.mocked(getGxpCertificateDetail).mockResolvedValue({ certificate_id: "cert-uuid", site_id: "site-uuid",
      certificate_type: type, production_line_id: "line-uuid", line_code: "A" } as Awaited<ReturnType<typeof getGxpCertificateDetail>>);
    mount("/reports/certificates/cert-uuid");
    expect(await screen.findByText(/certificate_id=cert-uuid/)).toHaveTextContent("production_line_id=line-uuid");
    expect(screen.getByText(/certificate_id=cert-uuid/)).toHaveTextContent(`gxp_type=${type}`);
  });

  it("shows GSP read-only without redirecting to another rail", async () => {
    vi.mocked(getGxpCertificateDetail).mockResolvedValue({ certificate_id: "cert-uuid", site_id: "site-uuid",
      certificate_type: "GSP", production_line_id: null, line_code: null } as Awaited<ReturnType<typeof getGxpCertificateDetail>>);
    mount("/reports/certificates/cert-uuid");
    expect(await screen.findByRole("heading", { name: "Chi tiết GCN GSP" })).toBeInTheDocument();
    expect(screen.queryByText(/certificate_id=cert-uuid/)).not.toBeInTheDocument();
  });
  it("loads both canonical GSP version snapshots under the verified report Certificate", async () => {
    vi.mocked(getGxpCertificateDetail).mockResolvedValue({
      certificate_id: "cert-uuid", site_id: "site-uuid", case_id: null, certificate_type: "GSP",
      production_line_id: null, line_code: null, scopes: [], row_version: 3,
    } as unknown as Awaited<ReturnType<typeof getGxpCertificateDetail>>);
    mount("/reports/certificates/cert-uuid?site_id=site-uuid");
    expect(await screen.findByRole("heading", { name: "Chi tiết GCN GSP" })).toBeInTheDocument();
    expect(await screen.findByText("Các phiên bản GPs đã lưu")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Các phiên bản GPs đã lưu"));
    expect(await screen.findByText("Bảo quản GSP lần 2")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Phiên bản đã lưu" }), { target: { value: "version-gsp-1" } });
    expect(screen.getByText("Bảo quản GSP lần 1")).toBeInTheDocument();
    expect(screen.queryByText("Bảo quản GSP lần 2")).not.toBeInTheDocument();
    expect(getGxpCertificateVersionHistory).toHaveBeenCalledWith("cert-uuid", expect.anything(), true, null, expect.any(AbortSignal));
    expect(screen.queryByRole("button", { name: /Lưu thay đổi|Cấp giấy|Đặt làm chứng nhận hiện hành/ })).not.toBeInTheDocument();
  });

  it("rejects GSP history with a wrong Site or Certificate type even after correct detail GET", async () => {
    vi.mocked(getGxpCertificateDetail).mockResolvedValue({
      certificate_id: "cert-uuid", site_id: "site-uuid", case_id: null,
      certificate_type: "GSP", scopes: [], row_version: 3,
    } as unknown as Awaited<ReturnType<typeof getGxpCertificateDetail>>);
    vi.mocked(getGxpCertificateVersionHistory).mockResolvedValue({
      ...storedGspHistory, site_id: "foreign-site", certificate_type: "GDP",
    });
    mount("/reports/certificates/cert-uuid?site_id=site-uuid");
    expect(await screen.findByRole("alert")).toHaveTextContent("Lịch sử phiên bản không khớp");
    expect(screen.queryByText("Bảo quản GSP lần 2")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Phiên bản đã lưu" })).not.toBeInTheDocument();
  });

  it("does not request history when Certificate detail identity fails", async () => {
    vi.mocked(getGxpCertificateDetail).mockResolvedValue({
      certificate_id: "wrong-cert", site_id: "site-uuid", certificate_type: "GSP",
    } as Awaited<ReturnType<typeof getGxpCertificateDetail>>);
    mount("/reports/certificates/cert-uuid?site_id=site-uuid");
    expect(await screen.findByRole("alert")).toHaveTextContent("Certificate UUID không khớp phản hồi");
    expect(getGxpCertificateVersionHistory).not.toHaveBeenCalled();
  });

  it("returns from a read-only linked GSP certificate to the exact Change Request when Site matches", async () => {
    vi.mocked(getGxpCertificateDetail).mockResolvedValue({
      certificate_id: "cert-uuid", site_id: "site-uuid", certificate_type: "GSP",
      production_line_id: null, line_code: null, scopes: [],
    } as unknown as Awaited<ReturnType<typeof getGxpCertificateDetail>>);
    render(<MemoryRouter initialEntries={[{
      pathname: "/reports/certificates/cert-uuid",
      search: "?site_id=site-uuid",
      state: { relatedChangeRequest: { id: "change-uuid", siteId: "site-uuid" } },
    }]}><Routes><Route path="/reports/certificates/:certificateId" element={<ReportRecordDetail access={access} kind="certificates" />} /></Routes></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "Quay lại yêu cầu thay đổi" }))
      .toHaveAttribute("href", "/reports/change-requests/change-uuid");
  });

  it("does not trust a related Change Request navigation hint from the wrong Site", async () => {
    vi.mocked(getGxpCertificateDetail).mockResolvedValue({
      certificate_id: "cert-uuid", site_id: "site-uuid", certificate_type: "GSP",
      production_line_id: null, line_code: null, scopes: [],
    } as unknown as Awaited<ReturnType<typeof getGxpCertificateDetail>>);
    render(<MemoryRouter initialEntries={[{
      pathname: "/reports/certificates/cert-uuid",
      search: "?site_id=site-uuid",
      state: { relatedChangeRequest: { id: "other-change", siteId: "other-site" } },
    }]}><Routes><Route path="/reports/certificates/:certificateId" element={<ReportRecordDetail access={access} kind="certificates" />} /></Routes></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Chi tiết GCN GSP" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Quay lại yêu cầu thay đổi" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Quay lại Báo cáo" })).toHaveAttribute("href", "/reports?report=certificates");
  });

  it("rejects a related certificate whose canonical Site differs from the source Change Request", async () => {
    vi.mocked(getGxpCertificateDetail).mockResolvedValue({
      certificate_id: "cert-uuid", site_id: "other-site", certificate_type: "GSP",
    } as Awaited<ReturnType<typeof getGxpCertificateDetail>>);
    render(<MemoryRouter initialEntries={[{
      pathname: "/reports/certificates/cert-uuid",
      search: "?site_id=site-uuid",
      state: { relatedChangeRequest: { id: "change-uuid", siteId: "site-uuid" } },
    }]}><Routes><Route path="/reports/certificates/:certificateId" element={<ReportRecordDetail access={access} kind="certificates" />} /></Routes></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Site UUID không hợp lệ hoặc không khớp chứng nhận");
    expect(screen.queryByRole("link", { name: "Quay lại yêu cầu thay đổi" })).not.toBeInTheDocument();
  });

  it("fetches exact Certificate UUID and rejects mismatched canonical identity", async () => {
    vi.mocked(getGxpCertificateDetail).mockResolvedValue({
      certificate_id: "different-id", certificate_number: "GCN-ERROR",
    } as Awaited<ReturnType<typeof getGxpCertificateDetail>>);
    mount("/reports/certificates/cert-uuid");
    expect(await screen.findByRole("alert")).toHaveTextContent("Certificate UUID không khớp phản hồi");
    expect(getGxpCertificateDetail).toHaveBeenCalledWith("cert-uuid", expect.anything(), true, null);
    expect(screen.queryByText("GCN-ERROR")).not.toBeInTheDocument();
  });

  it("fetches exact Change Request UUID with Site-owned data, never picking another request", async () => {
    vi.mocked(getChangeRequestWorkspace).mockResolvedValue({
      id: "change-uuid", site_id: "site-uuid", facility_name: "Cơ sở A",
      company_name: "Công ty", scope_label: "Đổi tên", state: "received",
      submitted_on: null, requester_name: null, description: null,
    } as Awaited<ReturnType<typeof getChangeRequestWorkspace>>);
    mount("/reports/change-requests/change-uuid");
    expect(await screen.findByText("change-uuid")).toBeInTheDocument();
    expect(screen.getByText("Cơ sở A")).toBeInTheDocument();
    expect(getChangeRequestWorkspace).toHaveBeenCalledWith("change-uuid", expect.anything(), true, null);
    expect(screen.getByRole("link", { name: "Quay lại Báo cáo" })).toHaveAttribute("href", "/reports");
  });
});
