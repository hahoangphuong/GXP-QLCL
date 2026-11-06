import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../App";
import { getBusinessEligibilityDocumentMetadata, getGxpCertificateDocumentMetadata } from "../lib/api";
import type { DocumentOwnerMetadataInventory } from "../types";
import { CertificateDocumentRegister } from "./CertificateDocumentRegister";

vi.mock("../lib/api", () => ({
  getBusinessEligibilityDocumentMetadata: vi.fn(),
  getGxpCertificateDocumentMetadata: vi.fn(),
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
});

describe("certificate document metadata register", () => {
  it("reads GxP certificate inventory without exposing document detail, file or issuance actions", async () => {
    mount();
    expect(await screen.findByText("Tệp đã đăng ký")).toBeInTheDocument();
    expect(screen.getByText(/chưa xác minh tệp binary hoặc bản gốc đã ký/)).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(getGxpCertificateDocumentMetadata).toHaveBeenCalledWith("cert-1", expect.anything(), true, null);
    expect(screen.queryByRole("button", { name: /Tải|Xem chi tiết|Ban hành|Tạo/ })).not.toBeInTheDocument();
    expect(screen.queryByText("signed.docx")).not.toBeInTheDocument();
  });

  it("reads eligibility certificate metadata from its separately scoped API", async () => {
    mount("/documents/business-eligibility-certificates/elig-1");
    await screen.findByText("Tệp đã đăng ký");
    expect(getBusinessEligibilityDocumentMetadata).toHaveBeenCalledWith("elig-1", expect.anything(), true, null);
    expect(getGxpCertificateDocumentMetadata).not.toHaveBeenCalled();
  });

  it("returns to the exact Site-scoped eligibility list using only a valid UUID hint", async () => {
    const site = "11111111-1111-4111-8111-111111111111";
    mount(`/documents/business-eligibility-certificates/elig-1?return_site_id=${site}`);
    await screen.findByText("Tệp đã đăng ký");
    expect(screen.getByRole("link", { name: "Quay lại danh mục" }))
      .toHaveAttribute("href", `/documents?kind=business_eligibility&site_id=${site}`);
  });

  it("rejects malformed Site return hints and preserves GxP certificate kind", async () => {
    const first = mount("/documents/business-eligibility-certificates/elig-1?return_site_id=../../bad");
    await screen.findByText("Tệp đã đăng ký");
    expect(screen.getByRole("link", { name: "Quay lại danh mục" }))
      .toHaveAttribute("href", "/documents?kind=business_eligibility");
    first.unmount();
    mount("/documents/certificates/cert-1");
    await screen.findByText("Tệp đã đăng ký");
    expect(screen.getByRole("link", { name: "Quay lại danh mục" }))
      .toHaveAttribute("href", "/documents?kind=certificates");
  });

  it("rejects wrong certificate UUID and owner kind without showing metadata rows", async () => {
    vi.mocked(getGxpCertificateDocumentMetadata).mockResolvedValue({ ...metadata(), owner_id: "other-cert" });
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("không khớp");
    expect(screen.queryByText("Tệp đã đăng ký")).not.toBeInTheDocument();
  });

  it("rejects unverified metadata claiming a signed original was verified", async () => {
    vi.mocked(getGxpCertificateDocumentMetadata).mockResolvedValue({
      ...metadata(), original_signed_document_verified: true as false,
    });
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("không khớp");
  });

  it("rejects inconsistent empty metadata status and duplicate document identity", async () => {
    vi.mocked(getGxpCertificateDocumentMetadata).mockResolvedValue({
      ...metadata(), metadata_status: "no_registered_document_metadata",
    });
    const first = mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("không khớp chứng nhận");
    first.unmount();
    vi.mocked(getGxpCertificateDocumentMetadata).mockResolvedValue({
      ...metadata(), documents: [metadata().documents[0], metadata().documents[0]],
    });
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("không khớp chứng nhận");
  });

  it.each(["certificate", "business_eligibility_certificate"] as const)(
    "rejects corrupt %s count/status metadata consistently without granting binary access",
    async kind => {
      const isGxp = kind === "certificate";
      const api = isGxp ? vi.mocked(getGxpCertificateDocumentMetadata) : vi.mocked(getBusinessEligibilityDocumentMetadata);
      const path = isGxp ? "/documents/certificates/cert-1" : "/documents/business-eligibility-certificates/elig-1";
      const fixture = metadata(kind);
      const invalid: DocumentOwnerMetadataInventory[] = [
        { ...fixture, metadata_status: "registered_metadata_only_unverified", documents: [] },
        { ...fixture, documents: [{ ...fixture.documents[0], registered_variant_count: -1 }] },
        { ...fixture, documents: [{ ...fixture.documents[0], registered_version_count: 1.5 }] },
        { ...fixture, documents: [{ ...fixture.documents[0], registered_current_version_count: 3 }] },
        { ...fixture, documents: [{ ...fixture.documents[0], registered_variant_count: Number.MAX_SAFE_INTEGER + 1 }] },
        { ...fixture, documents: [{ ...fixture.documents[0], family_code: "  " }] },
        { ...fixture, documents: [{ ...fixture.documents[0], document_type_code: "" }] },
        { ...fixture, documents: [{ ...fixture.documents[0], document_id: " " }] },
        { ...fixture, documents: [{ ...fixture.documents[0], title: 42 as unknown as string }] },
      ];
      for (const item of invalid) {
        api.mockResolvedValueOnce(item);
        const view = mount(path);
        expect(await screen.findByRole("alert")).toHaveTextContent("trạng thái đăng ký/phiên bản không hợp lệ");
        expect(screen.queryByText("Tệp đã đăng ký")).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /Tải|Ban hành|Sửa|Lưu/ })).not.toBeInTheDocument();
        view.unmount();
      }
    },
  );

  it("never renders malformed document counts after A→B navigation or credential replacement", async () => {
    const first = metadata();
    const bad = { ...metadata(), documents: [{ ...metadata().documents[0], registered_current_version_count: 8 }] };
    vi.mocked(getGxpCertificateDocumentMetadata).mockImplementation(async id => id === "cert-1"
      ? first : { ...bad, owner_id: id });
    render(<MemoryRouter initialEntries={["/documents/certificates/cert-1"]}>
      <Link to="/documents/certificates/cert-2">Mở B</Link>
      <Routes><Route path="/documents/certificates/:certificateId" element={
        <CertificateDocumentRegister access={access} kind="certificate" />} /></Routes>
    </MemoryRouter>);
    expect(await screen.findByText("Tệp đã đăng ký")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "Mở B" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("không hợp lệ");
    expect(screen.queryByText("Tệp đã đăng ký")).not.toBeInTheDocument();
  });

  it("shows an empty registered inventory without inventing files or evidence", async () => {
    vi.mocked(getGxpCertificateDocumentMetadata).mockResolvedValue({
      ...metadata(), metadata_status: "no_registered_document_metadata", documents: [],
    });
    mount();
    expect(await screen.findByText(/Chưa có metadata tài liệu đăng ký/)).toBeInTheDocument();
  });

  it("does not call secure APIs when authentication is unavailable", () => {
    mount("/documents/certificates/cert-1", { ...access, canLoadSecureApi: false });
    expect(screen.getByText("Cần đăng nhập")).toBeInTheDocument();
    expect(getGxpCertificateDocumentMetadata).not.toHaveBeenCalled();
  });

  it("immediately hides old registered metadata during same UUID credential reauthentication", async () => {
    let resolveNew!: (value: DocumentOwnerMetadataInventory) => void;
    vi.mocked(getGxpCertificateDocumentMetadata)
      .mockResolvedValueOnce(metadata())
      .mockImplementationOnce(() => new Promise(resolve => { resolveNew = resolve; }));
    const renderPage = (credential: ApiAccess) => <MemoryRouter initialEntries={["/documents/certificates/cert-1"]}>
      <Routes><Route path="/documents/certificates/:certificateId"
        element={<CertificateDocumentRegister access={credential} kind="certificate" />} /></Routes>
    </MemoryRouter>;
    const view = render(renderPage(access));
    expect(await screen.findByText("Tệp đã đăng ký")).toBeInTheDocument();
    view.rerender(renderPage({
      ...access, bearerToken: "new-token", accessGeneration: 2,
      auth: { username: "new-reader", role: "reader" },
    }));
    expect(screen.queryByText("Tệp đã đăng ký")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Đang tải metadata");
    await waitFor(() => expect(getGxpCertificateDocumentMetadata).toHaveBeenCalledTimes(2));
    resolveNew({ ...metadata(), documents: [{
      ...metadata().documents[0], title: "Tài liệu phiên mới",
    }] });
    expect(await screen.findByText("Tài liệu phiên mới")).toBeInTheDocument();
    expect(screen.queryByText("Tệp đã đăng ký")).not.toBeInTheDocument();
  });

  it("clears verified document rows when the same owner loses secure API access", async () => {
    const renderPage = (credential: ApiAccess) => <MemoryRouter initialEntries={["/documents/certificates/cert-1"]}>
      <Routes><Route path="/documents/certificates/:certificateId"
        element={<CertificateDocumentRegister access={credential} kind="certificate" />} /></Routes>
    </MemoryRouter>;
    const view = render(renderPage(access));
    expect(await screen.findByText("Tệp đã đăng ký")).toBeInTheDocument();
    view.rerender(renderPage({ ...access, canLoadSecureApi: false, accessGeneration: 2 }));
    expect(screen.getByText("Cần đăng nhập")).toBeInTheDocument();
    expect(screen.queryByText("Tệp đã đăng ký")).not.toBeInTheDocument();
    expect(getGxpCertificateDocumentMetadata).toHaveBeenCalledTimes(1);
  });

  it("discards stale metadata after navigating to another certificate", async () => {
    let resolveOld!: (value: DocumentOwnerMetadataInventory) => void;
    vi.mocked(getGxpCertificateDocumentMetadata).mockImplementation(id =>
      id === "cert-1" ? new Promise(resolve => { resolveOld = resolve; }) :
        Promise.resolve({ ...metadata(), owner_id: "cert-2", metadata_status: "no_registered_document_metadata", documents: [] }));
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
  });
});
