import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../App";
import { getCaseWorkspace, getChangeRequestWorkspace, getDocumentDetail } from "../lib/api";
import type { DocumentChecklistItem } from "../types";
import { DocumentsPage, DocumentRegister } from "./DocumentsPage";

vi.mock("../lib/api", () => ({
  getCaseWorkspace: vi.fn(),
  getChangeRequestWorkspace: vi.fn(),
  getDocumentDetail: vi.fn(),
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
    capa_cycle_id: null,
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

  it("refuses metadata from another Case even if the document UUID is selected", async () => {
    vi.mocked(getDocumentDetail).mockResolvedValue({ ...detailPayload(), case_id: "other-case" });
    mount("/documents/cases/case-1");
    await screen.findByText("2 mục trong checklist · 1 đã có · 1 chưa có");
    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("không thuộc ngữ cảnh");
    expect(screen.queryByText(/bien-ban-v2.docx/)).not.toBeInTheDocument();
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
