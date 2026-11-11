import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../../App";
import { getChangeRequestWorkspace } from "../../lib/api";
import type { ChangeRequestWorkspace } from "../../types";
import { ChangeRequestReadWorkspace } from "./ChangeRequestReadWorkspace";

vi.mock("../../lib/api", () => ({ getChangeRequestWorkspace: vi.fn() }));

const access: ApiAccess = {
  auth: { username: "reader", role: "reader" },
  useStubAuth: true, bearerToken: null, canLoadSecureApi: true, accessGeneration: 1,
};
const record: ChangeRequestWorkspace = {
  id: "cr-uuid", site_id: "site-uuid", row_version: 3, legacy_change_request_id: 56,
  facility_name: "Cơ sở A", company_name: "Công ty B", scope_label: "Đổi địa chỉ",
  description: "Chuyển địa điểm", submitted_on: "2026-01-10",
  requester_name: "Đơn vị đề nghị", state: "under_review",
  handled_on: "2026-02-01", handled_by_name: "Người xử lý", result_label: "Đồng ý",
  effective_on: "2026-02-15", approval_reference: "123/QĐ",
  details: [
    { change_detail_id: "d1", legacy_change_detail_id: 1, classification_id: 7,
      classification_label: "Địa chỉ", approval_status: "review",
      old_value: "Địa chỉ cũ", new_value: "Địa chỉ mới", note: "Xem xét" },
    { change_detail_id: "d2", legacy_change_detail_id: null, classification_id: null,
      classification_label: null, approval_status: null, old_value: null, new_value: null, note: null },
  ],
  affected_artifacts: [
    { link_id: "link1", artifact_kind: "certificate", artifact_id: "gcn-uuid", source_affected_artifact_id: null },
  ],
  issued_artifacts: [
    { link_id: "link2", artifact_kind: "business_eligibility_certificate",
      artifact_id: "ddk-uuid", source_affected_artifact_id: "link1" },
  ],
  documents: { items: [{
    checklist_key: "cr:cr-uuid:decision", label: "Quyết định", family_code: "DECISION",
    parent_scope: "change_request", parent_id: "cr-uuid", status: "available",
    document_id: "doc-1", document_type_code: "DECISION", title: "Quyết định",
    original_filename: "quyet-dinh.pdf", issued_on: "2026-02-01",
    available_variant_types: ["pdf"], detail_available: true,
  }] },
  action_readiness: [],
};

function mount(uri: string, currentAccess = access) {
  return render(<MemoryRouter initialEntries={[uri]}><Routes>
    <Route path="/reports/change-requests/:changeRequestId"
      element={<ChangeRequestReadWorkspace access={currentAccess} />} />
  </Routes></MemoryRouter>);
}

beforeEach(() => {
  vi.mocked(getChangeRequestWorkspace).mockReset().mockResolvedValue(record);
});

describe("full canonical Change Request read workspace", () => {
  it("deep-links to the document section and restores tab selection on Back/Forward without new GETs", async () => {
    function History() {
      const location = useLocation(), navigate = useNavigate();
      return <><output data-testid="section-url">{location.search}</output>
        <button onClick={() => navigate(-1)}>Back</button><button onClick={() => navigate(1)}>Forward</button></>;
    }
    render(<MemoryRouter initialEntries={["/reports/change-requests/cr-uuid?section=documents"]}>
      <History /><Routes><Route path="/reports/change-requests/:changeRequestId"
        element={<ChangeRequestReadWorkspace access={access} />} /></Routes>
    </MemoryRouter>);
    await screen.findByText("quyet-dinh.pdf");
    expect(screen.getByRole("button", { name: "Tài liệu" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Xử lý và chứng nhận" }));
    expect(screen.getByTestId("section-url")).toHaveTextContent("section=processing");
    expect(screen.getByText("123/QĐ")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("button", { name: "Tài liệu" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("quyet-dinh.pdf")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Forward" }));
    expect(screen.getByRole("button", { name: "Xử lý và chứng nhận" })).toHaveAttribute("aria-pressed", "true");
    expect(getChangeRequestWorkspace).toHaveBeenCalledOnce();
  });

  it.each(["section=unknown", "section=documents&section=details", "site_id=foreign"])("rejects malformed detail section hint before canonical GET (%s)", async query => {
    mount("/reports/change-requests/cr-uuid?" + query);
    expect(screen.getByRole("alert")).toHaveTextContent("Tham số phần yêu cầu thay đổi không hợp lệ");
    expect(getChangeRequestWorkspace).not.toHaveBeenCalled();
  });

  it("keeps report return context when switching sections and opening the Change Request checklist", async () => {
    const origin = "/reports?report=change_requests&state=under_review&offset=100";
    function Destination() {
      const location = useLocation();
      return <output data-testid="checklist-return">{JSON.stringify(location.state)}</output>;
    }
    render(<MemoryRouter initialEntries={[{ pathname: "/reports/change-requests/cr-uuid", state: { reportReturn: origin } }]}>
      <Routes>
        <Route path="/reports/change-requests/:changeRequestId" element={<ChangeRequestReadWorkspace access={access} />} />
        <Route path="/documents/change-requests/:changeRequestId" element={<Destination />} />
      </Routes>
    </MemoryRouter>);
    await screen.findByText("site-uuid");
    fireEvent.click(screen.getByRole("button", { name: "Tài liệu" }));
    expect(screen.getByRole("link", { name: "Quay lại Báo cáo" })).toHaveAttribute("href", origin);
    fireEvent.click(screen.getByRole("link", { name: "Xem checklist và phiên bản" }));
    expect(screen.getByTestId("checklist-return")).toHaveTextContent(origin);
    expect(getChangeRequestWorkspace).toHaveBeenCalledOnce();
  });

  it("returns to the originating report filters and page", async () => {
    render(<MemoryRouter initialEntries={[{ pathname: "/reports/change-requests/cr-uuid", state: { reportReturn: "/reports?report=change_requests&state=received&offset=100" } }]}><Routes><Route path="/reports/change-requests/:changeRequestId" element={<ChangeRequestReadWorkspace access={access} />} /></Routes></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "Quay lại Báo cáo" })).toHaveAttribute("href", "/reports?report=change_requests&state=received&offset=100");
  });
  it("renders request, detail changes, decisions, affected/issued artifacts and documents", async () => {
    mount("/reports/change-requests/cr-uuid");
    expect(await screen.findByRole("heading", { name: "Hồ sơ yêu cầu thay đổi" })).toBeInTheDocument();
    expect(await screen.findByText("site-uuid")).toBeInTheDocument();
    expect(screen.getByText(/không tự suy diễn GxP/)).toBeInTheDocument();
    expect(screen.getByText("Chuyển địa điểm")).toBeInTheDocument();
    expect(getChangeRequestWorkspace).toHaveBeenCalledWith("cr-uuid", expect.anything(), true, null);
    fireEvent.click(screen.getByRole("button", { name: "Chi tiết thay đổi" }));
    expect(screen.getByText("Địa chỉ cũ")).toBeInTheDocument();
    expect(screen.getByText("Địa chỉ mới")).toBeInTheDocument();
    expect(screen.getByText("Các mục thay đổi (2)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Xử lý và chứng nhận" }));
    expect(screen.getByText("123/QĐ")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "gcn-uuid" })).toHaveAttribute("href", "/reports/certificates/gcn-uuid?site_id=site-uuid");
    expect(screen.getByRole("link", { name: "ddk-uuid" }))
      .toHaveAttribute("href", "/certificates/business-eligibility/ddk-uuid?site_id=site-uuid");
    expect(screen.getByRole("link", { name: "gcn-uuid" })).toHaveAttribute("href", "/reports/certificates/gcn-uuid?site_id=site-uuid");
    expect(screen.getAllByRole("link", { name: "Tài liệu" }).map(link => link.getAttribute("href")))
      .toEqual(["/documents/certificates/gcn-uuid", "/documents/business-eligibility-certificates/ddk-uuid"]);
    fireEvent.click(screen.getByRole("button", { name: "Tài liệu" }));
    expect(screen.getByText("quyet-dinh.pdf")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Xem mục này" })).toHaveAttribute("href",
      "/documents/change-requests/cr-uuid?document_key=cr%3Acr-uuid%3Adecision");
    expect(screen.getByRole("link", { name: "Xem checklist và phiên bản" }))
      .toHaveAttribute("href", "/documents/change-requests/cr-uuid");
  });

  it("passes only the verified Change Request and Site as an eligibility return hint", async () => {
    function Destination() {
      const location = useLocation();
      return <pre data-testid="navigation-state">{JSON.stringify(location.state)}</pre>;
    }
    render(<MemoryRouter initialEntries={["/reports/change-requests/cr-uuid"]}><Routes>
      <Route path="/reports/change-requests/:changeRequestId" element={<ChangeRequestReadWorkspace access={access} />} />
      <Route path="/certificates/business-eligibility/:eligibilityId" element={<Destination />} />
    </Routes></MemoryRouter>);
    await screen.findByText("site-uuid");
    fireEvent.click(screen.getByRole("button", { name: "Xử lý và chứng nhận" }));
    fireEvent.click(screen.getByRole("link", { name: "ddk-uuid" }));
    expect(screen.getByTestId("navigation-state"))
      .toHaveTextContent('"relatedChangeRequest":{"id":"cr-uuid","siteId":"site-uuid"}');
    expect(getChangeRequestWorkspace).toHaveBeenCalledOnce();
  });

  it("does not invent an eligibility metadata link for an unknown artifact kind", async () => {
    vi.mocked(getChangeRequestWorkspace).mockResolvedValue({
      ...record, affected_artifacts: [{
        link_id: "unknown", artifact_kind: "unmapped" as "certificate",
        artifact_id: "unknown-id", source_affected_artifact_id: null,
      }],
      issued_artifacts: [],
    });
    mount("/reports/change-requests/cr-uuid");
    await screen.findByText("site-uuid");
    fireEvent.click(screen.getByRole("button", { name: "Xử lý và chứng nhận" }));
    expect(screen.getByText("Loại chưa hỗ trợ")).toBeInTheDocument();
    expect(screen.getByText("Không hỗ trợ mở trực tiếp")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Tài liệu" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "unknown-id" })).not.toBeInTheDocument();
  });

  it("never fetches protected records without authentication", () => {
    mount("/reports/change-requests/cr-uuid", { ...access, canLoadSecureApi: false });
    expect(screen.getByText("Cần đăng nhập")).toBeInTheDocument();
    expect(getChangeRequestWorkspace).not.toHaveBeenCalled();
  });

  it("refuses a mismatched UUID or absent canonical Site", async () => {
    vi.mocked(getChangeRequestWorkspace).mockResolvedValue({ ...record, id: "other" });
    mount("/reports/change-requests/cr-uuid");
    expect(await screen.findByRole("alert")).toHaveTextContent("không khớp UUID");
    expect(screen.queryByText("Chuyển địa điểm")).not.toBeInTheDocument();
  });

  it("shows empty collections as empty, not synthesized records", async () => {
    vi.mocked(getChangeRequestWorkspace).mockResolvedValue({
      ...record, details: [], affected_artifacts: [], issued_artifacts: [], documents: { items: [] },
    });
    mount("/reports/change-requests/cr-uuid");
    await screen.findByText("site-uuid");
    fireEvent.click(screen.getByRole("button", { name: "Chi tiết thay đổi" }));
    expect(screen.getByText("Chưa có mục thay đổi chi tiết.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Xử lý và chứng nhận" }));
    expect(screen.getAllByText("Chưa có chứng nhận liên kết.")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Tài liệu" }));
    expect(screen.getByText("Chưa có mục tài liệu được liên kết.")).toBeInTheDocument();
  });

  it("does not display a previous request after navigation to a different UUID", async () => {
    const first = { ...record };
    const second = { ...record, id: "second-uuid", scope_label: "Thay người đại diện", details: [] };
    vi.mocked(getChangeRequestWorkspace).mockImplementation(async id => id === "cr-uuid" ? first : second);
    const { unmount } = mount("/reports/change-requests/cr-uuid");
    await screen.findByText("site-uuid");
    unmount();
    mount("/reports/change-requests/second-uuid");
    await waitFor(() => expect(screen.getByText("second-uuid")).toBeInTheDocument());
    expect(screen.queryByText("Đổi địa chỉ")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Thay người đại diện" })).toBeInTheDocument();
  });
});
