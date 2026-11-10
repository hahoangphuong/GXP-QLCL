import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../../App";
import { getCertificateReport, getChangeRequestReport } from "../../lib/api";
import { CanonicalRecordReport } from "./CanonicalRecordReport";

vi.mock("../../lib/api", () => ({ getCertificateReport: vi.fn(), getChangeRequestReport: vi.fn() }));

const access: ApiAccess = {
  auth: { username: "reader", role: "reader" }, useStubAuth: true,
  bearerToken: null, canLoadSecureApi: true, accessGeneration: 1,
};
const cert = {
  certificate_id: "cert-uuid", result_key: "site-uuid:GMP:facility_wide:", certificate_version_id: "version-uuid", site_id: "site-uuid",
  case_id: null, production_line_id: null, line_code: null, facility_name: "Cơ sở GMP",
  company_name: "Công ty A", gxp_type: "GMP", certificate_number: "GCN-123",
  issue_date: "2026-01-01", expiry_date: "2026-12-31", lifecycle_state: "GRANTED", status: "active",
};
const change = {
  change_request_id: "change-uuid", site_id: "site-uuid", legacy_change_request_id: 123,
  facility_name: "Cơ sở GMP", company_name: "Công ty A", scope_label: "Đổi tên",
  description: "Thay đổi", submitted_on: "2026-01-01", requester_name: null, state: "received",
};

beforeEach(() => {
  vi.mocked(getCertificateReport).mockReset().mockResolvedValue({ items: [cert], total_count: 1, limit: 100, offset: 0 });
  vi.mocked(getChangeRequestReport).mockReset().mockResolvedValue({ items: [change], total_count: 1, limit: 100, offset: 0 });
});

describe("canonical record report workflow", () => {
  it("filters current Certificates by GxP and expiry window, linking to exact UUID", async () => {
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "GCN-123" })).toHaveAttribute("href", expect.stringContaining("certificate_id=cert-uuid"));
    expect(screen.getByRole("link", { name: "Xem metadata" })).toHaveAttribute("href", "/documents/certificates/cert-uuid");
    expect(screen.getByText("1 GCN")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Loại GxP"), { target: { value: "GMP" } });
    fireEvent.change(screen.getByLabelText("GCN hết hạn trong"), { target: { value: "30" } });
    fireEvent.change(screen.getByLabelText("Số GCN"), { target: { value: "GCN-123" } });
    fireEvent.submit(screen.getByRole("button", { name: "Áp dụng bộ lọc" }).closest("form")!);
    await waitFor(() => expect(vi.mocked(getCertificateReport).mock.calls.some(([filters]) =>
      filters?.gxp_type === "GMP" && filters.expiry_days === "30" && filters.number === "GCN-123")).toBe(true));
  });

  it("can start in all-current certificate mode for document browsing without changing report defaults", async () => {
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" initialCertificateExpiryDays="" /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "Xem metadata" })).toHaveAttribute("href", "/documents/certificates/cert-uuid");
    expect(screen.getByLabelText("GCN hết hạn trong")).toHaveValue("");
    expect(getCertificateReport).toHaveBeenCalledWith(expect.objectContaining({ expiry_days: "", offset: 0, export: false }),
      expect.anything(), true, null);
  });

  it.each(["GSP", "GDP"])("filters %s certificates and preserves read-only detail/metadata links", async gxp => {
    vi.mocked(getCertificateReport).mockResolvedValue({
      items: [{ ...cert, gxp_type: gxp, result_key: `site-uuid:${gxp}:facility_wide:` }],
      total_count: 1, limit: 100, offset: 0,
    });
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" initialCertificateExpiryDays="" /></MemoryRouter>);
    await screen.findByRole("link", { name: "GCN-123" });
    fireEvent.change(screen.getByLabelText("Loại GxP"), { target: { value: gxp } });
    fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
    await waitFor(() => expect(getCertificateReport).toHaveBeenCalledWith(
      expect.objectContaining({ gxp_type: gxp, expiry_days: "", export: false }),
      expect.anything(), true, null,
    ));
    expect(await screen.findByRole("link", { name: "GCN-123" }))
      .toHaveAttribute("href", "/reports/certificates/cert-uuid?site_id=site-uuid");
    expect(screen.getByRole("link", { name: "Xem metadata" }))
      .toHaveAttribute("href", "/documents/certificates/cert-uuid");
    expect(screen.getByRole("button", { name: "Xuất CSV (Excel)" })).toBeEnabled();
  });

  it("opens an issuing Case directly from the Certificate report using a link that CaseDirectOpen must independently verify", async () => {
    vi.mocked(getCertificateReport).mockResolvedValue({
      items: [{ ...cert, gxp_type: "GMP", case_id: "case-uuid" }],
      total_count: 1, limit: 100, offset: 0,
    });
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    const link = await screen.findByRole("link", { name: "Mở Case" });
    const url = new URL(link.getAttribute("href")!, "https://app.test");
    expect(url.pathname).toBe("/cases/case-uuid");
    expect(url.searchParams.get("source_certificate_id")).toBe("cert-uuid");
    expect(url.searchParams.get("source_site_id")).toBe("site-uuid");
    expect(getChangeRequestReport).not.toHaveBeenCalled();
  });

  it.each(["GSP", "GDP"])("does not offer an unsupported %s Case deep link even if the report contains a Case ID", async gxp => {
    vi.mocked(getCertificateReport).mockResolvedValue({
      items: [{ ...cert, gxp_type: gxp, result_key: `site-uuid:${gxp}:facility_wide:`, case_id: "legacy-case" }],
      total_count: 1, limit: 100, offset: 0,
    });
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    await screen.findByRole("link", { name: "GCN-123" });
    expect(screen.queryByRole("link", { name: "Mở Case" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "GCN-123" })).toHaveAttribute("href", "/reports/certificates/cert-uuid?site_id=site-uuid");
  });

  it("does not infer a Case for an unlinked legacy Certificate report projection", async () => {
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    await screen.findByRole("link", { name: "GCN-123" });
    expect(screen.queryByRole("link", { name: "Mở Case" })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Case phát hành" })).toBeInTheDocument();
  });

  it("shows each Change Request identity without inventing a GxP classification", async () => {
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="change_requests" /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "123" })).toHaveAttribute("href", "/reports/change-requests/change-uuid");
    expect(screen.queryByLabelText("Loại GxP")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Trạng thái thay đổi"), { target: { value: "under_review" } });
    fireEvent.submit(screen.getByRole("button", { name: "Áp dụng bộ lọc" }).closest("form")!);
    await waitFor(() => expect(vi.mocked(getChangeRequestReport).mock.calls.some(([filters]) =>
      filters?.state === "under_review")).toBe(true));
  });

  it("links GSP to the canonical read-only detail instead of mapping it to GMP", async () => {
    vi.mocked(getCertificateReport).mockResolvedValue({ items: [{ ...cert, gxp_type: "GSP" }], total_count: 1, limit: 100, offset: 0 });
    render(<MemoryRouter><CanonicalRecordReport access={access} kind="certificates" /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "GCN-123" })).toHaveAttribute("href", "/reports/certificates/cert-uuid?site_id=site-uuid");
    expect(screen.getByRole("link", { name: "Xem metadata" })).toHaveAttribute("href", "/documents/certificates/cert-uuid");
  });

  it("does not fetch protected pages without a valid session", () => {
    render(<MemoryRouter><CanonicalRecordReport access={{ ...access, canLoadSecureApi: false }} kind="certificates" /></MemoryRouter>);
    expect(screen.getByText("Cần đăng nhập để xem báo cáo.")).toBeInTheDocument();
    expect(getCertificateReport).not.toHaveBeenCalled();
  });
});
