import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../../App";
import { getChangeRequestWorkspace, getGxpCertificateDetail } from "../../lib/api";
import { ReportRecordDetail } from "./ReportRecordDetail";

vi.mock("../../lib/api", () => ({ getGxpCertificateDetail: vi.fn(), getChangeRequestWorkspace: vi.fn() }));

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

beforeEach(() => {
  vi.mocked(getGxpCertificateDetail).mockReset();
  vi.mocked(getChangeRequestWorkspace).mockReset();
});

describe("authorized canonical detail navigation", () => {
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
