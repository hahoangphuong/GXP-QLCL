import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../App";
import { getCaseWorkspace, getChangeRequestWorkspace, getDocumentDetail, openCaseDocumentCurrentContent, openCapaCycleDocumentCurrentContent } from "../lib/api";
import type { ContextualDocumentAction, DocumentChecklistItem } from "../types";
import { DocumentsPage, DocumentRegister } from "./DocumentsPage";

vi.mock("../lib/api", () => ({
  getCaseWorkspace: vi.fn(),
  getChangeRequestWorkspace: vi.fn(),
  getDocumentDetail: vi.fn(),
  openCaseDocumentCurrentContent: vi.fn(),
  openCapaCycleDocumentCurrentContent: vi.fn(),
}));
vi.mock("../features/reports/CaseReport", () => ({
  CaseReport: ({ showDocumentsLink }: { showDocumentsLink?: boolean }) =>
    <output data-testid="case-report">{String(showDocumentsLink)}</output>,
}));
vi.mock("../features/reports/CanonicalRecordReport", () => ({
  CanonicalRecordReport: ({ kind, showDocumentsLink }: { kind: string; showDocumentsLink?: boolean }) =>
    <output data-testid="change-report">{kind}:{String(showDocumentsLink)}</output>,
}));

const access: ApiAccess = {
  auth: { username: "reader", role: "reader" },
  bearerToken: null, useStubAuth: true, canLoadSecureApi: true, accessGeneration: 1,
};
const caseDocument: DocumentChecklistItem = {
  checklist_key: "case:case-1:INSPECTION_REPORT",
  label: "Biên bản kiểm tra",
  family_code: "INSPECTION_REPORT",
  parent_scope: "case",
  parent_id: "case-1",
  status: "available",
  document_id: "doc-1",
  document_type_code: "INSPECTION_REPORT",
  title: "Biên bản kiểm tra đợt 1",
  original_filename: "bien-ban.docx",
  issued_on: "2026-01-15",
  available_variant_types: ["editable_docx"], detail_available: true,
};
const missingDocument: DocumentChecklistItem = {
  ...caseDocument,
  checklist_key: "case:case-1:INSPECTION_QD_KT",
  label: "Quyết định kiểm tra",
  family_code: "INSPECTION_QD_KT",
  status: "missing",
  document_id: null, original_filename: null, issued_on: null,
  detail_available: false, available_variant_types: [],
};

function casePayload(id = "case-1") {
  return {
    case_summary: { id, facility_name: "Cơ sở A", site_id: "site-1", gxp_type: "GMP" },
    documents: { items: [caseDocument, missingDocument] },
    contextual_document_actions: [{
      checklist_key: missingDocument.checklist_key, parent_scope: "case", parent_id: "case-1",
      actions: [{ action_key: "create", available: false, disabled_reason: "QĐKT chưa đủ bằng chứng" }],
    }] as unknown as ContextualDocumentAction[],
  } as Awaited<ReturnType<typeof getCaseWorkspace>>;
}
function changePayload(id = "change-1") {
  return {
    id, site_id: "site-1", facility_name: "Cơ sở B",
    documents: { items: [{
      ...caseDocument,
      checklist_key: "change_request:change-1:REQUEST",
      parent_scope: "change_request",
      parent_id: "change-1",
      document_id: "change-doc",
    }] },
  } as Awaited<ReturnType<typeof getChangeRequestWorkspace>>;
}
function detailPayload(parent: "case" | "change" = "case") {
  return {
    document_id: parent === "case" ? "doc-1" : "change-doc",
    case_id: parent === "case" ? "case-1" : null,
    change_request_id: parent === "change" ? "change-1" : null,
    capa_cycle_id: null, certificate_id: null, business_eligibility_certificate_id: null,
    legacy_entity_type: null,
    family_code: "INSPECTION_REPORT",
    document_type_code: "INSPECTION_REPORT",
    title: "Biên bản",
    variants: [{
      id: "variant-1", variant_type: "editable_docx", language_code: "vi",
      is_active: true, versions: [{
        id: "version-1", version_no: 2, original_filename: "bien-ban-v2.docx",
        is_current: true, issued_on: null,
      }],
    }],
    generation_runs: [],
  } as Awaited<ReturnType<typeof getDocumentDetail>>;
}
function mount(path: string, apiAccess = access) {
  return render(<MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/documents/cases/:caseId" element={<DocumentRegister kind="cases" access={apiAccess} />} />
      <Route path="/documents/change-requests/:changeRequestId" element={<DocumentRegister kind="change-requests" access={apiAccess} />} />
    </Routes>
  </MemoryRouter>);
}

beforeEach(() => {
  vi.mocked(getCaseWorkspace).mockReset().mockResolvedValue(casePayload());
  vi.mocked(getChangeRequestWorkspace).mockReset().mockResolvedValue(changePayload());
  vi.mocked(getDocumentDetail).mockReset().mockResolvedValue(detailPayload());
  vi.mocked(openCaseDocumentCurrentContent).mockReset().mockResolvedValue({
    blob: new Blob(["source"], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }),
    contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    filename: "bien-ban.docx",
  });
  vi.mocked(openCapaCycleDocumentCurrentContent).mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("document binary action and readiness", () => {
  it("downloads the current Case-owned file using the authorized binary endpoint", async () => {
    const objectUrl = vi.fn(() => "blob:case-current");
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: objectUrl });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    mount("/documents/cases/case-1");
    await screen.findByText("2 mục trong checklist · 1 đã có · 1 chưa có");
    expect(screen.getByText(/Chưa sẵn sàng: QĐKT chưa đủ bằng chứng/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Đến workspace để tạo" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    await screen.findByText(/Phiên bản 2:/);
    fireEvent.click(screen.getByRole("button", { name: "Tải tệp hiện hành" }));
    await waitFor(() => expect(openCaseDocumentCurrentContent)
      .toHaveBeenCalledWith("case-1", "doc-1", expect.anything(), true, null));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(objectUrl).toHaveBeenCalledTimes(1);
    expect(openCapaCycleDocumentCurrentContent).not.toHaveBeenCalled();
  });

  it("does not offer download when metadata has no active current version", async () => {
    vi.mocked(getDocumentDetail).mockResolvedValue({
      ...detailPayload(),
      variants: [{ ...detailPayload().variants[0], is_active: false }],
    });
    mount("/documents/cases/case-1");
    await screen.findByText("2 mục trong checklist · 1 đã có · 1 chưa có");
    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    const download = await screen.findByRole("button", { name: "Tải tệp hiện hành" });
    expect(download).toBeDisabled();
    expect(screen.getByText(/Chưa xác nhận phiên bản hiện hành/)).toBeInTheDocument();
    expect(openCaseDocumentCurrentContent).not.toHaveBeenCalled();
  });

  it("uses the CAPA cycle-scoped endpoint for CAPA document content", async () => {
    const capaDocument = {
      ...caseDocument,
      checklist_key: "capa:cycle-1:REPORT",
      parent_scope: "capa_cycle" as const,
      parent_id: "cycle-1",
      document_id: "capa-doc",
    };
    vi.mocked(getCaseWorkspace).mockResolvedValue({
      ...casePayload(),
      documents: { items: [capaDocument] },
    });
    vi.mocked(getDocumentDetail).mockResolvedValue({
      ...detailPayload(), document_id: "capa-doc", case_id: null, capa_cycle_id: "cycle-1",
    });
    vi.mocked(openCapaCycleDocumentCurrentContent).mockResolvedValue({
      blob: new Blob(["capa"]), contentType: "application/octet-stream", filename: "capa.docx",
    });
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:capa-current") });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    mount("/documents/cases/case-1");
    await screen.findByText("1 mục trong checklist · 1 đã có · 0 chưa có");
    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    await screen.findByText(/Phiên bản 2:/);
    fireEvent.click(screen.getByRole("button", { name: "Tải tệp hiện hành" }));
    await waitFor(() => expect(openCapaCycleDocumentCurrentContent)
      .toHaveBeenCalledWith("case-1", "cycle-1", "capa-doc", expect.anything(), true, null));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(openCaseDocumentCurrentContent).not.toHaveBeenCalled();
  });

  it("keeps Change Request documents metadata-only without an invented binary route", async () => {
    vi.mocked(getDocumentDetail).mockResolvedValue(detailPayload("change"));
    mount("/documents/change-requests/change-1");
    await screen.findByText("Cơ sở B");
    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    await screen.findByText(/Phiên bản 2:/);
    expect(screen.queryByRole("button", { name: "Tải tệp hiện hành" })).not.toBeInTheDocument();
    expect(screen.getByText(/Chưa có API tải binary Change Request/)).toBeInTheDocument();
  });
});

describe("direct document register navigation", () => {
  const caseUuid = "11111111-1111-4111-8111-111111111111";
  const changeUuid = "22222222-2222-4222-8222-222222222222";

  it("opens an explicitly selected Case UUID without relying on active Case reports", () => {
    render(<MemoryRouter initialEntries={["/documents"]}><Routes>
      <Route path="/documents" element={<DocumentsPage access={access} statusError={null} />} />
      <Route path="/documents/cases/:caseId" element={<p>Case register reached</p>} />
    </Routes></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Mở danh mục tài liệu theo UUID"), { target: { value: `  ${caseUuid}  ` } });
    fireEvent.click(screen.getByRole("button", { name: "Mở hồ sơ" }));
    expect(screen.getByText("Case register reached")).toBeInTheDocument();
    expect(getCaseWorkspace).not.toHaveBeenCalled();
  });

  it("navigates to the Change Request register only when that scope is explicitly selected", () => {
    render(<MemoryRouter initialEntries={["/documents"]}><Routes>
      <Route path="/documents" element={<DocumentsPage access={access} statusError={null} />} />
      <Route path="/documents/change-requests/:changeRequestId" element={<p>Change Request register reached</p>} />
    </Routes></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "Yêu cầu thay đổi" }));
    fireEvent.change(screen.getByLabelText("Mở danh mục tài liệu theo UUID"), { target: { value: changeUuid } });
    fireEvent.click(screen.getByRole("button", { name: "Mở hồ sơ" }));
    expect(screen.getByText("Change Request register reached")).toBeInTheDocument();
  });

  it("opens GxP and eligibility certificate metadata via explicit UUID and kind", () => {
    const certUuid = "33333333-3333-4333-8333-333333333333";
    const eligUuid = "44444444-4444-4444-8444-444444444444";
    const ui = render(<MemoryRouter initialEntries={["/documents"]}><Routes>
      <Route path="/documents" element={<DocumentsPage access={access} statusError={null} />} />
      <Route path="/documents/certificates/:certificateId" element={<p>GCN metadata reached</p>} />
      <Route path="/documents/business-eligibility-certificates/:eligibilityId" element={<p>Eligibility metadata reached</p>} />
    </Routes></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "GCN GxP" }));
    fireEvent.change(screen.getByLabelText("Mở danh mục tài liệu theo UUID"), { target: { value: certUuid } });
    fireEvent.click(screen.getByRole("button", { name: "Mở hồ sơ" }));
    expect(screen.getByText("GCN metadata reached")).toBeInTheDocument();
    ui.unmount();
    render(<MemoryRouter initialEntries={["/documents"]}><Routes>
      <Route path="/documents" element={<DocumentsPage access={access} statusError={null} />} />
      <Route path="/documents/business-eligibility-certificates/:eligibilityId" element={<p>Eligibility metadata reached</p>} />
    </Routes></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "Giấy đủ điều kiện kinh doanh dược" }));
    fireEvent.change(screen.getByLabelText("Mở danh mục tài liệu theo UUID"), { target: { value: eligUuid } });
    fireEvent.click(screen.getByRole("button", { name: "Mở hồ sơ" }));
    expect(screen.getByText("Eligibility metadata reached")).toBeInTheDocument();
  });

  it("clears direct UUID when switching the selected owner type", () => {
    render(<MemoryRouter><DocumentsPage access={access} statusError={null} /></MemoryRouter>);
    const input = screen.getByLabelText("Mở danh mục tài liệu theo UUID");
    fireEvent.change(input, { target: { value: "55555555-5555-4555-8555-555555555555" } });
    expect(input).toHaveValue("55555555-5555-4555-8555-555555555555");
    fireEvent.click(screen.getByRole("button", { name: "GCN GxP" }));
    expect(input).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "Mở hồ sơ" }));
    expect(screen.getByRole("alert")).toHaveTextContent("UUID hợp lệ");
    fireEvent.click(screen.getByRole("button", { name: "Giấy đủ điều kiện kinh doanh dược" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("rejects invalid UUIDs without routing or reading protected data", () => {
    render(<MemoryRouter><DocumentsPage access={access} statusError={null} /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Mở danh mục tài liệu theo UUID"), { target: { value: "../other" } });
    fireEvent.click(screen.getByRole("button", { name: "Mở hồ sơ" }));
    expect(screen.getByRole("alert")).toHaveTextContent("UUID hợp lệ");
    expect(getCaseWorkspace).not.toHaveBeenCalled();
    expect(getChangeRequestWorkspace).not.toHaveBeenCalled();
  });

  it("does not offer direct navigation without authenticated API access", () => {
    render(<MemoryRouter><DocumentsPage access={{ ...access, canLoadSecureApi: false }} statusError={null} /></MemoryRouter>);
    expect(screen.queryByRole("button", { name: "Mở hồ sơ" })).not.toBeInTheDocument();
  });
});

describe("contextual document register", () => {
  it("offers authenticated Case and Change Request lists with exact document context links", () => {
    render(<MemoryRouter><DocumentsPage access={access} statusError={null} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Danh mục tài liệu theo hồ sơ" })).toBeInTheDocument();
    expect(screen.getByTestId("case-report")).toHaveTextContent("true");
    fireEvent.click(screen.getByRole("button", { name: "Yêu cầu thay đổi" }));
    expect(screen.getByTestId("change-report")).toHaveTextContent("change_requests:true");
    expect(getCaseWorkspace).not.toHaveBeenCalled();
  });

  it("does not read secure data without a session", () => {
    render(<MemoryRouter><DocumentsPage access={{ ...access, canLoadSecureApi: false }} statusError={null} /></MemoryRouter>);
    expect(screen.getByText("Cần đăng nhập")).toBeInTheDocument();
    expect(getCaseWorkspace).not.toHaveBeenCalled();
    mount("/documents/cases/case-1", { ...access, canLoadSecureApi: false });
    expect(getDocumentDetail).not.toHaveBeenCalled();
  });

  it("lists available and missing Case documents; filters and reads selected metadata", async () => {
    mount("/documents/cases/case-1");
    expect(await screen.findByText("2 mục trong checklist · 1 đã có · 1 chưa có")).toBeInTheDocument();
    expect(screen.getByText("Quyết định kiểm tra")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mở Case trong workspace" })).toHaveAttribute("href", "/cases/case-1");
    expect(getDocumentDetail).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Trạng thái tài liệu"), { target: { value: "missing" } });
    expect(screen.getByText("Quyết định kiểm tra")).toBeInTheDocument();
    expect(screen.queryByText("Biên bản kiểm tra")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Trạng thái tài liệu"), { target: { value: "all" } });

    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    expect(await screen.findByText(/Phiên bản 2:/)).toBeInTheDocument();
    expect(screen.getByText(/bien-ban-v2.docx/)).toBeInTheDocument();
    expect(getDocumentDetail).toHaveBeenCalledWith("doc-1", expect.anything(), true, null);
    expect(screen.queryByRole("button", { name: "Tạo Quyết định kiểm tra" })).not.toBeInTheDocument();
  });

  it("fails closed on an incorrect Case UUID returned from the API", async () => {
    vi.mocked(getCaseWorkspace).mockResolvedValue(casePayload("other-case"));
    mount("/documents/cases/case-1");
    const error = await screen.findByText("Case UUID không khớp phản hồi.");
    expect(error).toBeInTheDocument();
    expect(getDocumentDetail).not.toHaveBeenCalled();
  });

  it("refuses a Case checklist if its canonical Site is missing", async () => {
    vi.mocked(getCaseWorkspace).mockResolvedValue({
      ...casePayload(), case_summary: { ...casePayload().case_summary, site_id: "" },
    });
    mount("/documents/cases/case-1");
    expect(await screen.findByText(/thiếu Site canonical/)).toBeInTheDocument();
    expect(screen.queryByText("Biên bản kiểm tra")).not.toBeInTheDocument();
    expect(getDocumentDetail).not.toHaveBeenCalled();
  });

  it("refuses a Change Request checklist if its canonical Site is missing", async () => {
    vi.mocked(getChangeRequestWorkspace).mockResolvedValue({
      ...changePayload(), site_id: "",
    });
    mount("/documents/change-requests/change-1");
    expect(await screen.findByText(/thiếu Site canonical/)).toBeInTheDocument();
    expect(screen.queryByText("Biên bản kiểm tra")).not.toBeInTheDocument();
    expect(getDocumentDetail).not.toHaveBeenCalled();
  });

  it("refuses metadata from another Case even if the document UUID is selected", async () => {
    vi.mocked(getDocumentDetail).mockResolvedValue({ ...detailPayload(), case_id: "other-case" });
    mount("/documents/cases/case-1");
    await screen.findByText("2 mục trong checklist · 1 đã có · 1 chưa có");
    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("không thuộc ngữ cảnh");
    expect(screen.queryByText(/bien-ban-v2.docx/)).not.toBeInTheDocument();
  });

  it("rejects Case document detail carrying an additional certificate owner before download", async () => {
    vi.mocked(getDocumentDetail).mockResolvedValue({ ...detailPayload(), certificate_id: "other-cert" });
    mount("/documents/cases/case-1");
    await screen.findByText("2 mục trong checklist · 1 đã có · 1 chưa có");
    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("không thuộc ngữ cảnh");
    expect(screen.queryByRole("button", { name: "Tải tệp hiện hành" })).not.toBeInTheDocument();
    expect(openCaseDocumentCurrentContent).not.toHaveBeenCalled();
  });

  it("rejects Change Request document detail carrying an additional Case owner", async () => {
    vi.mocked(getDocumentDetail).mockResolvedValue({
      ...detailPayload("change"), case_id: "another-case",
    });
    mount("/documents/change-requests/change-1");
    await screen.findByText("Cơ sở B");
    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("không thuộc ngữ cảnh");
    expect(screen.queryByText(/bien-ban-v2.docx/)).not.toBeInTheDocument();
  });

  it("rejects CAPA detail with a second Case parent before requesting a binary", async () => {
    const capaDocument = { ...caseDocument, checklist_key: "capa:cycle-1:REPORT",
      parent_scope: "capa_cycle" as const, parent_id: "cycle-1", document_id: "capa-doc" };
    vi.mocked(getCaseWorkspace).mockResolvedValue({
      ...casePayload(), documents: { items: [capaDocument] },
    });
    vi.mocked(getDocumentDetail).mockResolvedValue({
      ...detailPayload(), document_id: "capa-doc", capa_cycle_id: "cycle-1", case_id: "case-1",
    });
    mount("/documents/cases/case-1");
    await screen.findByText("1 mục trong checklist · 1 đã có · 0 chưa có");
    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("không thuộc ngữ cảnh");
    expect(openCapaCycleDocumentCurrentContent).not.toHaveBeenCalled();
  });

  it("rejects a foreign parent in a Case checklist without exposing any rows", async () => {
    vi.mocked(getCaseWorkspace).mockResolvedValue({
      ...casePayload(), documents: { items: [{ ...caseDocument, parent_id: "case-foreign" }] },
    });
    mount("/documents/cases/case-1");
    expect(await screen.findByText(/Checklist tài liệu có ngữ cảnh owner không khớp/)).toBeInTheDocument();
    expect(screen.queryByText("Biên bản kiểm tra")).not.toBeInTheDocument();
    expect(getDocumentDetail).not.toHaveBeenCalled();
  });

  it("rejects foreign Change Request checklist rows", async () => {
    vi.mocked(getChangeRequestWorkspace).mockResolvedValue({
      ...changePayload(), documents: { items: [{ ...caseDocument,
        parent_scope: "change_request", parent_id: "another-change" }] },
    });
    mount("/documents/change-requests/change-1");
    expect(await screen.findByText(/Checklist tài liệu có ngữ cảnh owner không khớp/)).toBeInTheDocument();
    expect(getDocumentDetail).not.toHaveBeenCalled();
  });

  it("rejects duplicate checklist keys without rendering ambiguous document actions", async () => {
    vi.mocked(getCaseWorkspace).mockResolvedValue({
      ...casePayload(), documents: { items: [caseDocument, { ...caseDocument }] },
    });
    mount("/documents/cases/case-1");
    expect(await screen.findByText(/định danh trùng lặp/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xem chi tiết" })).not.toBeInTheDocument();
  });

  it("opens exactly the requested Change Request's checklist and validates its document owner", async () => {
    vi.mocked(getDocumentDetail).mockResolvedValue(detailPayload("change"));
    mount("/documents/change-requests/change-1");
    expect(await screen.findByText("Cơ sở B")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Xem yêu cầu thay đổi" }))
      .toHaveAttribute("href", "/reports/change-requests/change-1");
    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    await waitFor(() => expect(getDocumentDetail).toHaveBeenCalledWith("change-doc", expect.anything(), true, null));
    expect(await screen.findByText(/Phiên bản 2:/)).toBeInTheDocument();
    expect(getCaseWorkspace).not.toHaveBeenCalled();
  });
});
