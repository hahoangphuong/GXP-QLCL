import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../App";
import { getBusinessEligibilityDocumentMetadata, getDocumentDetail, getGxpCertificateDocumentMetadata } from "../lib/api";
import type { DocumentDetail, DocumentOwnerMetadataInventory } from "../types";
import { CertificateDocumentRegister } from "./CertificateDocumentRegister";

vi.mock("../lib/api", () => ({
  getBusinessEligibilityDocumentMetadata: vi.fn(),
  getGxpCertificateDocumentMetadata: vi.fn(),
  getDocumentDetail: vi.fn(),
}));

const access: ApiAccess = {
  auth: { username: "reader", role: "reader" },
  bearerToken: null, useStubAuth: true, canLoadSecureApi: true, accessGeneration: 1,
};

function metadata(kind: "certificate" | "business_eligibility_certificate" = "certificate"): DocumentOwnerMetadataInventory {
  return {
    owner_kind: kind, owner_id: kind === "certificate" ? "cert-1" : "elig-1",
    metadata_status: "registered_metadata_only_unverified",
    binary_verified: false, original_signed_document_verified: false,
    documents: [{ document_id: "doc-1", family_code: "CERTIFICATE",
      document_type_code: "CERTIFICATE", title: "Tệp đã đăng ký",
      registered_variant_count: 1, registered_version_count: 2, registered_current_version_count: 1 }],
  };
}

function document(kind: "certificate" | "business_eligibility_certificate" = "certificate"): DocumentDetail {
  return {
    document_id: "doc-1", family_code: "CERTIFICATE", document_type_code: "CERTIFICATE",
    title: "Tệp đã đăng ký", legacy_entity_type: null, case_id: null, capa_cycle_id: null,
    certificate_id: kind === "certificate" ? "cert-1" : null,
    business_eligibility_certificate_id: kind === "business_eligibility_certificate" ? "elig-1" : null,
    change_request_id: null, generation_runs: [],
    variants: [{ id: "variant-1", variant_type: "editable_docx", language_code: "vi",
      is_active: true, versions: [{ id: "version-1", version_no: 2, original_filename: "signed.docx",
        is_current: true, issued_on: null }] }],
  };
}

function mount(path = "/documents/certificates/cert-1", apiAccess = access) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/documents/certificates/:certificateId"
      element={<CertificateDocumentRegister access={apiAccess} kind="certificate" />} />
    <Route path="/documents/business-eligibility-certificates/:eligibilityId"
      element={<CertificateDocumentRegister access={apiAccess} kind="business_eligibility_certificate" />} />
  </Routes></MemoryRouter>);
}

beforeEach(() => {
  vi.mocked(getGxpCertificateDocumentMetadata).mockReset().mockResolvedValue(metadata());
  vi.mocked(getBusinessEligibilityDocumentMetadata).mockReset().mockResolvedValue(metadata("business_eligibility_certificate"));
  vi.mocked(getDocumentDetail).mockReset().mockResolvedValue(document());
});

describe("certificate document metadata register", () => {
  it("reads a GxP certificate inventory and clearly marks signed binary as unverified", async () => {
    mount();
    expect(await screen.findByText("Tệp đã đăng ký")).toBeInTheDocument();
    expect(screen.getByText(/Chưa xác minh tệp binary hoặc bản gốc đã ký/)).toBeInTheDocument();
    expect(getGxpCertificateDocumentMetadata).toHaveBeenCalledWith("cert-1", expect.anything(), true, null);
    expect(getDocumentDetail).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    await screen.findByText(/Phiên bản 2/);
    expect(getDocumentDetail).toHaveBeenCalledWith("doc-1", expect.anything(), true, null);
    expect(screen.queryByRole("button", { name: /Tải|Ban hành|Tạo/ })).not.toBeInTheDocument();
  });

  it("reads the eligibility certificate metadata from its own scoped API", async () => {
    vi.mocked(getDocumentDetail).mockResolvedValue(document("business_eligibility_certificate"));
    mount("/documents/business-eligibility-certificates/elig-1");
    await screen.findByText("Tệp đã đăng ký");
    expect(getBusinessEligibilityDocumentMetadata).toHaveBeenCalledWith("elig-1", expect.anything(), true, null);
    expect(getGxpCertificateDocumentMetadata).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    await screen.findByText(/Phiên bản 2/);
  });

  it("refuses wrong owner UUID or owner kind before exposing document rows", async () => {
    vi.mocked(getGxpCertificateDocumentMetadata).mockResolvedValue({ ...metadata(), owner_id: "another-cert" });
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("không khớp");
    expect(screen.queryByText("Tệp đã đăng ký")).not.toBeInTheDocument();
    expect(getDocumentDetail).not.toHaveBeenCalled();
  });

  it("refuses document details belonging to another certificate", async () => {
    vi.mocked(getDocumentDetail).mockResolvedValue({ ...document(), certificate_id: "other-cert" });
    mount();
    await screen.findByText("Tệp đã đăng ký");
    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("không thuộc chứng nhận");
    expect(screen.queryByText(/Phiên bản 2/)).not.toBeInTheDocument();
  });

  it("rejects multi-parent document detail even when the selected certificate ID matches", async () => {
    vi.mocked(getDocumentDetail).mockResolvedValue({ ...document(), change_request_id: "unexpected-owner" });
    mount();
    await screen.findByText("Tệp đã đăng ký");
    fireEvent.click(screen.getByRole("button", { name: "Xem chi tiết" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("không thuộc chứng nhận");
    expect(screen.queryByText(/Phiên bản 2/)).not.toBeInTheDocument();
  });

  it("shows an empty registered inventory without claiming missing binary evidence", async () => {
    vi.mocked(getGxpCertificateDocumentMetadata).mockResolvedValue({
      ...metadata(), metadata_status: "no_registered_document_metadata", documents: [],
    });
    mount();
    expect(await screen.findByText(/Chưa có metadata tài liệu đăng ký/)).toBeInTheDocument();
    expect(getDocumentDetail).not.toHaveBeenCalled();
  });

  it("does not call secure APIs when authentication is unavailable", () => {
    mount("/documents/certificates/cert-1", { ...access, canLoadSecureApi: false });
    expect(screen.getByText("Cần đăng nhập")).toBeInTheDocument();
    expect(getGxpCertificateDocumentMetadata).not.toHaveBeenCalled();
    expect(getDocumentDetail).not.toHaveBeenCalled();
  });

  it("discards stale metadata after navigating to another certificate", async () => {
    let resolveOld!: (value: DocumentOwnerMetadataInventory) => void;
    vi.mocked(getGxpCertificateDocumentMetadata).mockImplementation(id =>
      id === "cert-1" ? new Promise(resolve => { resolveOld = resolve; }) :
        Promise.resolve({ ...metadata(), owner_id: "cert-2", documents: [] }));
    render(<MemoryRouter initialEntries={["/documents/certificates/cert-1"]}>
      <Link to="/documents/certificates/cert-2">Mở chứng nhận khác</Link>
      <Routes><Route path="/documents/certificates/:certificateId" element={
        <CertificateDocumentRegister access={access} kind="certificate" />} /></Routes>
    </MemoryRouter>);
    await waitFor(() => expect(getGxpCertificateDocumentMetadata).toHaveBeenCalledWith(
      "cert-1", expect.anything(), true, null));
    fireEvent.click(screen.getByRole("link", { name: "Mở chứng nhận khác" }));
    expect(await screen.findByText("UUID chứng nhận: cert-2")).toBeInTheDocument();
    resolveOld(metadata());
    expect(screen.queryByText("Tệp đã đăng ký")).not.toBeInTheDocument();
    expect(getDocumentDetail).not.toHaveBeenCalled();
  });
});
