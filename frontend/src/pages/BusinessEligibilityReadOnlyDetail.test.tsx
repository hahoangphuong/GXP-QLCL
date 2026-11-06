import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../App";
import { getBusinessEligibilityDetail, getBusinessEligibilityVersionHistory, getBusinessEligibilityGxpSourceEvidence } from "../lib/api";
import type { BusinessEligibilityDetail, BusinessEligibilityVersionHistory, BusinessEligibilityGxpSourceEvidence } from "../types";
import { BusinessEligibilityReadOnlyDetail } from "./BusinessEligibilityReadOnlyDetail";

vi.mock("../lib/api", () => ({ getBusinessEligibilityDetail: vi.fn(), getBusinessEligibilityVersionHistory: vi.fn(), getBusinessEligibilityGxpSourceEvidence: vi.fn() }));
const idA = "11111111-1111-4111-8111-111111111111";
const idB = "22222222-2222-4222-8222-222222222222";
const site = "33333333-3333-4333-8333-333333333333";
const otherSite = "44444444-4444-4444-8444-444444444444";
const company = "55555555-5555-4555-8555-555555555555";
const basis = "66666666-6666-4666-8666-666666666666";
const access: ApiAccess = { auth: { username: "reader", role: "reader" }, useStubAuth: true, bearerToken: null, canLoadSecureApi: true, accessGeneration: 1 };
function detail(id = idA): BusinessEligibilityDetail {
  return {
    business_eligibility_certificate_id: id, row_version: 4, site_id: site,
    company_id: company, latest_flag: true, certificate_number: "GCN-ĐĐK-01",
    issued_on: "2026-03-01", expires_on: null, notes: "Ghi chú đã lưu",
    decision_reference: "QD-01", issuance_sequence_text: "2", issuance_history_text: null,
    company_name: "Công ty Minh chứng", company_legal_address: "Trụ sở",
    facility_name: "Cơ sở Minh chứng", address: "Địa chỉ cơ sở",
    professional_responsible_person_name: "Người phụ trách", quality_assurance_person_name: "Người QA",
    professional_qualification_text: null, professional_license_number: null,
    professional_license_issued_on: null, professional_license_issuer: null,
    responsible_license_issued_on: null, responsible_license_issuer: null,
    business_activity_text: "Bán buôn", current_status_text: "Còn hiệu lực",
    handled_by_name: null, application_dossier_reference: null,
    replaces_certificate_number: null, replaced_by_certificate_number: null,
    linked_gxp_certificates: [{
      certificate_id: basis, certificate_type: "GMP", line_code: null,
      certificate_number: "GMP-01", issue_date: null, link_role: "source_certificate",
    }],
    action_readiness: [{ action_key: "edit_latest_version", label: "Sửa", available: true, reason_code: null,
      required_permissions: ["certificate.edit"], expected_version: 4 }],
  };
}
function versionHistory(id = idA): BusinessEligibilityVersionHistory {
  return {
    business_eligibility_certificate_id: id, legacy_dkkd_id: 42, site_id: site, company_id: company,
    aggregate_latest_flag: true, latest_version_id: "77777777-7777-4777-8777-777777777777",
    latest_selection_method: "max_persisted_version_no",
    gxp_source_tokens_included: false, canonical_link_status: "stored_fk_only_not_validated",
    versions: [{
      business_eligibility_version_id: "77777777-7777-4777-8777-777777777777",
      version_no: 2, row_version: 4, certificate_number: "GCN-ĐĐK-01",
      issued_on: "2026-03-01", expires_on: null, notes: null,
      decision_reference: "QD-01", issuance_sequence_text: "2", issuance_history_text: null,
      professional_responsible_person_name: "Người phụ trách",
      quality_assurance_person_name: "Người QA",
      professional_qualification_text: null, professional_license_number: null,
      professional_license_issued_on: null, professional_license_issuer: null,
      responsible_license_issued_on: null, responsible_license_issuer: null,
      business_activity_text: "Bán buôn", current_status_text: "Còn hiệu lực",
      handled_by_name: null, application_dossier_reference: null,
      stored_link_records: [{ link_id: "88888888-8888-4888-8888-888888888888", certificate_id: basis, link_role: "source_certificate" }],
    }],
  };
}
function originalExcelEvidence(id = idA): BusinessEligibilityGxpSourceEvidence {
  return {
    business_eligibility_certificate_id: id, legacy_dkkd_id: 42, source_status: "available",
    evidence_kind: "original_excel_cells_source_only", canonical_links_included: false,
    source_workbook_sha256: "a".repeat(64), source_sheet_name: "db.dkkd", source_row_number: 42,
    groups: (["GMP", "GLP", "GSP", "GDP"] as const).map((name, i) => ({
      source_group_id: `source-${name}`, source_group: name,
      id_cc_excel_column: 1 + i, certificate_scope_excel_column: 5 + i,
      applicable_standard_excel_column: 9 + i, business_activity_excel_column: 13 + i,
      id_cc_raw: name === "GMP" ? "376" : "", certificate_scope_raw: name === "GMP" ? "Nguồn Excel gốc" : "",
      applicable_standard_raw: "", business_activity_raw: "", source_values_sha256: "b".repeat(64),
      reference_tokens: name === "GMP" ? [{
        source_reference_id: "source-token", token_index: 1, raw_token: "376", parsed_legacy_certificate_id: 376,
      }] : [],
    })),
  };
}
function mount(path = `/certificates/business-eligibility/${idA}?site_id=${site}`, props = access) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/certificates/business-eligibility/:eligibilityId" element={<BusinessEligibilityReadOnlyDetail access={props} />} />
  </Routes></MemoryRouter>);
}
beforeEach(() => {
  vi.mocked(getBusinessEligibilityDetail).mockReset().mockResolvedValue(detail());
  vi.mocked(getBusinessEligibilityVersionHistory).mockReset().mockResolvedValue(versionHistory());
  vi.mocked(getBusinessEligibilityGxpSourceEvidence).mockReset().mockResolvedValue(originalExcelEvidence());
});

describe("read-only business eligibility detail", () => {
  it("opens the canonical record, legal fields and registered metadata without mutation rail", async () => {
    mount();
    expect(await screen.findByText("Cơ sở Minh chứng")).toBeInTheDocument();
    expect(screen.getAllByText("Bán buôn").length).toBeGreaterThan(0);
    expect(screen.getByText("GMP-01", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Quay lại danh sách Site" }))
      .toHaveAttribute("href", `/documents?kind=business_eligibility&site_id=${site}`);
    expect(screen.getByRole("link", { name: "Xem metadata tài liệu đã đăng ký" }))
      .toHaveAttribute("href", `/documents/business-eligibility-certificates/${idA}?return_site_id=${site}`);
    expect(getBusinessEligibilityDetail).toHaveBeenCalledWith(idA, access.auth, true, null);
    expect(screen.queryByRole("button", { name: /Cấp|Lưu|Sửa|Ban hành|Tải/ })).not.toBeInTheDocument();
  });

  it("displays persisted version snapshots and stored FK links without treating them as verified source", async () => {
    mount();
    expect(await screen.findByText("Cơ sở Minh chứng")).toBeInTheDocument();
    expect(await screen.findByText("Các phiên bản ĐĐK đã lưu")).toBeInTheDocument();
    await waitFor(() => expect(getBusinessEligibilityVersionHistory).toHaveBeenCalledWith(idA, access.auth, true, null, expect.anything()));
    fireEvent.click(screen.getByText("Các phiên bản ĐĐK đã lưu"));
    expect(await screen.findByText("Snapshot phiên bản — chỉ đọc")).toBeInTheDocument();
    expect(screen.getByText(/chưa xác nhận hiệu lực hoặc phê duyệt lịch sử/)).toBeInTheDocument();
    expect(screen.getAllByText("Phiên bản 2", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /Cấp|Sửa|Ban hành|Lưu/ })).not.toBeInTheDocument();
  });

  it("does not use cross-Site or malformed version history as canonical evidence", async () => {
    vi.mocked(getBusinessEligibilityVersionHistory).mockResolvedValueOnce({
      ...versionHistory(), site_id: otherSite,
    });
    const a = mount();
    expect(await screen.findByText("Cơ sở Minh chứng")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("GCN-ĐĐK-01", { exact: false })).toBeInTheDocument();
    a.unmount();
    vi.mocked(getBusinessEligibilityVersionHistory).mockResolvedValueOnce({
      ...versionHistory(), versions: [versionHistory().versions[0], versionHistory().versions[0]],
    });
    mount();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("1 phiên bản đã lưu")).not.toBeInTheDocument();
  });

  it("shows Excel source cells separately from persisted FK history and never promotes raw ID CC to canonical identity", async () => {
    mount();
    expect(await screen.findByText("Cơ sở Minh chứng")).toBeInTheDocument();
    await waitFor(() => expect(getBusinessEligibilityGxpSourceEvidence)
      .toHaveBeenCalledWith(idA, access.auth, true, null, expect.anything()));
    expect(await screen.findByText("Dữ liệu GxP từ hồ sơ ĐĐK gốc")).toBeInTheDocument();
    expect(screen.getByText("Dữ liệu đối chiếu Excel, chưa phải liên kết GxP được xác nhận.")).toBeInTheDocument();
    expect(screen.getByText("Nguồn Excel gốc")).toBeInTheDocument();
    expect(screen.getAllByText("376", { exact: true }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /Cấp|Sửa|Ban hành|Lưu/ })).not.toBeInTheDocument();
  });

  it.each(["legacy_identity_missing", "not_in_imported_source"] as const)("renders %s without inventing source values", async source_status => {
    vi.mocked(getBusinessEligibilityGxpSourceEvidence).mockResolvedValueOnce({
      ...originalExcelEvidence(), source_status, groups: [],
    });
    mount();
    expect(await screen.findByText("Cơ sở Minh chứng")).toBeInTheDocument();
    expect(await screen.findByText(source_status === "legacy_identity_missing"
      ? /chưa có định danh legacy/ : /không nằm trong nguồn Excel đã import/)).toBeInTheDocument();
    expect(screen.queryByText("Nguồn Excel gốc")).not.toBeInTheDocument();
  });

  it("fails closed on mismatched Certificate and missing or duplicate original Excel groups", async () => {
    const bad = [
      { ...originalExcelEvidence(), business_eligibility_certificate_id: idB },
      { ...originalExcelEvidence(), canonical_links_included: true },
      { ...originalExcelEvidence(), groups: originalExcelEvidence().groups.slice(0, 3) },
      { ...originalExcelEvidence(), groups: [
        originalExcelEvidence().groups[0], originalExcelEvidence().groups[0],
        originalExcelEvidence().groups[2], originalExcelEvidence().groups[3],
      ] },
    ] as BusinessEligibilityGxpSourceEvidence[];
    for (const invalid of bad) {
      vi.mocked(getBusinessEligibilityGxpSourceEvidence).mockResolvedValueOnce(invalid);
      const view = mount();
      expect(await screen.findByText("Cơ sở Minh chứng")).toBeInTheDocument();
      expect(await screen.findByRole("alert")).toHaveTextContent("Không thể tải dữ liệu nguồn");
      expect(screen.queryByText("Nguồn Excel gốc")).not.toBeInTheDocument();
      view.unmount();
    }
  });

  it("does not retrieve Excel evidence when canonical detail fails verification", async () => {
    vi.mocked(getBusinessEligibilityDetail).mockResolvedValueOnce({ ...detail(), site_id: otherSite });
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("không khớp");
    expect(getBusinessEligibilityGxpSourceEvidence).not.toHaveBeenCalled();
  });

  it.each([403, 404, 409])("does not retry Excel source HTTP %s or expose mock data", async status => {
    vi.mocked(getBusinessEligibilityGxpSourceEvidence).mockRejectedValueOnce(Object.assign(
      new Error("Protected source unavailable"), { status }));
    mount();
    expect(await screen.findByText("Cơ sở Minh chứng")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(getBusinessEligibilityGxpSourceEvidence).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Nguồn Excel gốc")).not.toBeInTheDocument();
  });

  it("does not request version history when detail is unverified or unauthorized", async () => {
    vi.mocked(getBusinessEligibilityDetail).mockResolvedValueOnce({ ...detail(), site_id: otherSite });
    const view = mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("không khớp");
    expect(getBusinessEligibilityVersionHistory).not.toHaveBeenCalled();
    view.unmount();
    mount(`/certificates/business-eligibility/${idA}`, { ...access, canLoadSecureApi: false });
    expect(getBusinessEligibilityVersionHistory).not.toHaveBeenCalled();
  });

  it("does not read protected data with invalid URL identity or no authorization", () => {
    mount("/certificates/business-eligibility/invalid");
    expect(screen.getByRole("alert")).toHaveTextContent("UUID");
    expect(getBusinessEligibilityDetail).not.toHaveBeenCalled();
    mount(`/certificates/business-eligibility/${idA}?site_id=wrong`);
    expect(screen.getAllByRole("alert")).toHaveLength(2);
    expect(getBusinessEligibilityDetail).not.toHaveBeenCalled();
    mount(`/certificates/business-eligibility/${idA}`, { ...access, canLoadSecureApi: false });
    expect(screen.getByText("Cần đăng nhập")).toBeInTheDocument();
    expect(getBusinessEligibilityDetail).not.toHaveBeenCalled();
  });

  it("fails closed on wrong certificate ID, Site, bad version and duplicate linked GxP identities", async () => {
    const invalids = [
      { ...detail(), business_eligibility_certificate_id: idB },
      { ...detail(), site_id: otherSite },
      { ...detail(), row_version: 0 },
      { ...detail(), linked_gxp_certificates: [detail().linked_gxp_certificates[0], detail().linked_gxp_certificates[0]] },
    ];
    for (const invalid of invalids) {
      vi.mocked(getBusinessEligibilityDetail).mockResolvedValueOnce(invalid);
      const view = mount();
      expect(await screen.findByRole("alert")).toHaveTextContent("không khớp");
      expect(screen.queryByText("Cơ sở Minh chứng")).not.toBeInTheDocument();
      view.unmount();
    }
  });

  it("does not resurrect an old certificate response after A to B to A", async () => {
    const pending: Array<(result: BusinessEligibilityDetail) => void> = [];
    vi.mocked(getBusinessEligibilityDetail).mockImplementation(() => new Promise(resolve => pending.push(resolve)));
    render(<MemoryRouter initialEntries={[`/certificates/business-eligibility/${idA}?site_id=${site}`]}>
      <Link to={`/certificates/business-eligibility/${idB}?site_id=${site}`}>Open B</Link>
      <Link to={`/certificates/business-eligibility/${idA}?site_id=${site}`}>Open A</Link>
      <Routes><Route path="/certificates/business-eligibility/:eligibilityId" element={<BusinessEligibilityReadOnlyDetail access={access} />} /></Routes>
    </MemoryRouter>);
    await waitFor(() => expect(pending).toHaveLength(1));
    fireEvent.click(screen.getByRole("link", { name: "Open B" }));
    await waitFor(() => expect(pending).toHaveLength(2));
    fireEvent.click(screen.getByRole("link", { name: "Open A" }));
    await waitFor(() => expect(pending).toHaveLength(3));
    await act(async () => pending[2]({ ...detail(idA), facility_name: "New A" }));
    expect(await screen.findByText("New A")).toBeInTheDocument();
    await act(async () => {
      pending[1](detail(idB));
      pending[0]({ ...detail(idA), facility_name: "Old A" });
    });
    expect(screen.queryByText("Old A")).not.toBeInTheDocument();
    expect(screen.getByText("New A")).toBeInTheDocument();
  });

  it("retains no old credential data after accessGeneration change", async () => {
    let oldResolve!: (value: BusinessEligibilityDetail) => void;
    vi.mocked(getBusinessEligibilityDetail).mockImplementationOnce(() => new Promise(resolve => { oldResolve = resolve; }))
      .mockResolvedValueOnce({ ...detail(), facility_name: "New credential" });
    const app = (props: ApiAccess) => <MemoryRouter initialEntries={[`/certificates/business-eligibility/${idA}?site_id=${site}`]}><Routes>
      <Route path="/certificates/business-eligibility/:eligibilityId" element={<BusinessEligibilityReadOnlyDetail access={props} />} />
    </Routes></MemoryRouter>;
    const view = render(app(access));
    view.rerender(app({ ...access, accessGeneration: 2 }));
    expect(await screen.findByText("New credential")).toBeInTheDocument();
    await act(async () => oldResolve({ ...detail(), facility_name: "Old credential" }));
    expect(screen.queryByText("Old credential")).not.toBeInTheDocument();
  });

  it.each([403, 404, 409])("shows HTTP %s without inventing a certificate or retry", async code => {
    vi.mocked(getBusinessEligibilityDetail).mockRejectedValueOnce(new Error(`HTTP ${code}`));
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent(`HTTP ${code}`);
    expect(getBusinessEligibilityDetail).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Cơ sở Minh chứng")).not.toBeInTheDocument();
  });
});
