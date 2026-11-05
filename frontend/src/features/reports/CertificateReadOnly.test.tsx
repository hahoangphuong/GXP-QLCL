import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../../App";
import { getGxpCertificateDetail } from "../../lib/api";
import type { GxpCertificateDetail } from "../../types";
import { ReportRecordDetail } from "./ReportRecordDetail";

vi.mock("../../lib/api", () => ({ getGxpCertificateDetail: vi.fn(), getChangeRequestWorkspace: vi.fn() }));
const access: ApiAccess = { auth: { username: "reader", role: "reader" }, useStubAuth: true, bearerToken: null, canLoadSecureApi: true, accessGeneration: 1 };
function certificate(id: string, type = "GSP"): GxpCertificateDetail {
  return { certificate_id: id, row_version: 1, site_id: "site-a", case_id: null, certificate_type: type,
    line_code: null, production_line_id: null, production_line_code: null, production_line_identity_state: "facility_wide",
    issuance_basis: "legacy_import", latest_flag: true, certificate_number: `GCN-${id}`, issue_date: null,
    expiry_date: null, applicable_standard: "GSP", issuing_authority: "Cục quản lý", status: "active",
    facility_name: `Cơ sở ${id}`, address: "Địa chỉ", company_name: "Công ty", company_legal_address: null,
    scope_summary: null, scopes: [{ id: "scope-1", scope_key: null, scope_text: "Bảo quản lạnh", language_code: "vi", sort_order: 1 }],
    limitation_text: null, source_description: null, action_readiness: [] };
}
function Controls() { const nav = useNavigate(); return <><button onClick={() => nav("/reports/certificates/B?site_id=site-b")}>B</button><button onClick={() => nav("/reports/certificates/A?site_id=site-a")}>A</button><p>URL test</p></>; }
function mount(override = access, path = "/reports/certificates/A?site_id=site-a") {
  return render(<MemoryRouter initialEntries={[path]}><Controls /><Routes><Route path="/reports/certificates/:certificateId" element={<ReportRecordDetail access={override} kind="certificates" />} /><Route path="/search" element={<p>SEARCH-RAIL</p>} /></Routes></MemoryRouter>);
}
beforeEach(() => { vi.mocked(getGxpCertificateDetail).mockReset(); });
describe("read-only certificate identity", () => {
  it.each(["GSP", "GDP", "OTHER"])("opens %s without a mutation rail and links exact metadata", async type => {
    vi.mocked(getGxpCertificateDetail).mockResolvedValue(certificate("A", type));
    mount();
    expect((await screen.findAllByText(type, { exact: true })).length).toBeGreaterThan(0);
    expect(screen.getByText("Bảo quản lạnh")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /metadata tài liệu/i })).toHaveAttribute("href", "/documents/certificates/A");
    expect(screen.queryByText("SEARCH-RAIL")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /chỉnh sửa|cấp|lưu/i })).not.toBeInTheDocument();
  });
  it.each(["", "other"])("rejects missing or mismatching canonical Site %s", async site => {
    vi.mocked(getGxpCertificateDetail).mockResolvedValue({ ...certificate("A"), site_id: site });
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent(/Site/);
    expect(screen.queryByText("Cơ sở A")).not.toBeInTheDocument();
  });
  it("rejects a response for another Certificate UUID", async () => {
    vi.mocked(getGxpCertificateDetail).mockResolvedValue(certificate("other"));
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("Certificate UUID không khớp");
    expect(screen.queryByText("Cơ sở other")).not.toBeInTheDocument();
  });
  it("shows an empty scope without synthesizing one", async () => {
    vi.mocked(getGxpCertificateDetail).mockResolvedValue({ ...certificate("A"), scopes: null as unknown as GxpCertificateDetail["scopes"] });
    mount();
    expect(await screen.findByText("Chưa có phạm vi chứng nhận.")).toBeInTheDocument();
    expect(screen.queryByText("Bảo quản lạnh")).not.toBeInTheDocument();
  });
  it.each([401, 403, 404, 409])("displays HTTP %s without changing GxP or retrying", async status => {
    vi.mocked(getGxpCertificateDetail).mockRejectedValue(new Error(`HTTP ${status}`));
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent(`HTTP ${status}`);
    expect(getGxpCertificateDetail).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("SEARCH-RAIL")).not.toBeInTheDocument();
  });
  it("does not expose the old owner's late response after credentials change", async () => {
    let resolveOld!: (x: GxpCertificateDetail) => void;
    vi.mocked(getGxpCertificateDetail).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }))
      .mockResolvedValueOnce({ ...certificate("A"), facility_name: "Owner B" });
    const tree = (value: ApiAccess) => <MemoryRouter initialEntries={["/reports/certificates/A?site_id=site-a"]}><Routes><Route path="/reports/certificates/:certificateId" element={<ReportRecordDetail access={value} kind="certificates" />} /></Routes></MemoryRouter>;
    const view = render(tree(access));
    view.rerender(tree({ ...access, accessGeneration: 2, bearerToken: "synthetic-B" }));
    expect(await screen.findByText("Owner B")).toBeInTheDocument();
    await act(async () => resolveOld({ ...certificate("A"), facility_name: "Old owner" }));
    expect(screen.queryByText("Old owner")).not.toBeInTheDocument();
    expect(screen.getByText("Owner B")).toBeInTheDocument();
  });
  it("keeps the newest A owner when A → B → A responses arrive late", async () => {
    const pending: ((x: GxpCertificateDetail) => void)[] = [];
    vi.mocked(getGxpCertificateDetail).mockImplementation(() => new Promise(resolve => pending.push(resolve)));
    mount();
    fireEvent.click(screen.getByRole("button", { name: "B" }));
    fireEvent.click(screen.getByRole("button", { name: "A" }));
    expect(pending).toHaveLength(3);
    await act(async () => pending[2](certificate("A")));
    expect(await screen.findByText("Cơ sở A")).toBeInTheDocument();
    await act(async () => { pending[1]({ ...certificate("B"), site_id: "site-b" }); pending[0]({ ...certificate("A"), facility_name: "STALE" }); });
    expect(screen.getByText("Cơ sở A")).toBeInTheDocument();
    expect(screen.queryByText("STALE")).not.toBeInTheDocument();
    expect(screen.queryByText("Cơ sở B")).not.toBeInTheDocument();
  });
  it("does not show A after navigation to a failing B", async () => {
    vi.mocked(getGxpCertificateDetail).mockResolvedValueOnce(certificate("A")).mockRejectedValueOnce(new Error("B unavailable"));
    mount();
    await screen.findByText("Cơ sở A");
    fireEvent.click(screen.getByRole("button", { name: "B" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("B unavailable");
    expect(screen.queryByText("Cơ sở A")).not.toBeInTheDocument();
  });
});
