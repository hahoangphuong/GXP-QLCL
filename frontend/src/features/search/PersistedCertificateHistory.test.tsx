import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { BusinessEligibilityVersionHistory, GxpCertificateVersionHistory } from "../../types";
import { PersistedCertificateHistory } from "./PersistedCertificateHistory";

const data: GxpCertificateVersionHistory = {
  certificate_id: "aggregate-a", site_id: "site", case_id: null, certificate_type: "GMP", issuance_basis: "legacy_import",
  aggregate_latest_flag: false, latest_version_id: "version-new", versions: [2, 1].map(n => ({
    certificate_version_id: n === 2 ? "version-new" : "version-old", version_no: n, row_version: 8,
    is_latest_version: n === 2, lifecycle_state: null, certificate_number: "same-number", issue_date: null,
    expiry_date: "2001-01-01", applicable_standard: null, issuing_authority: null, scope_summary: `summary-${n}`,
    scopes: [{ id: `scope-${n}`, scope_key: null, scope_text: `scope ${n}\nsecond line`, language_code: "vi", sort_order: 0 }],
  })),
};

describe("persisted certificate snapshots", () => {
  it("announces loading and errors while the native disclosure remains collapsed", () => {
    const { rerender } = render(<PersistedCertificateHistory kind="gxp" state={{ status: "loading" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Đang tải phiên bản đã lưu");
    expect(screen.getByText("Các phiên bản GPs đã lưu").closest("details")).not.toHaveAttribute("open");
    rerender(<PersistedCertificateHistory kind="gxp" state={{ status: "error", httpStatus: 403 }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Không có quyền xem phiên bản");
  });
  it("keeps focus on the labelled selector and announces the newly displayed snapshot", () => {
    render(<PersistedCertificateHistory kind="gxp" state={{ status: "ready", data }} />);
    fireEvent.click(screen.getByText("Các phiên bản GPs đã lưu"));
    const selector = screen.getByRole("combobox", { name: "Phiên bản đã lưu" });
    selector.focus();
    fireEvent.change(selector, { target: { value: "version-old" } });
    expect(selector).toHaveFocus();
    expect(screen.getByRole("status")).toHaveTextContent("Đang hiển thị phiên bản 1");
    expect(screen.getByRole("region", { name: "Snapshot phiên bản — chỉ đọc" })).toContainElement(selector);
  });
  it("does not steal aggregate focus when a replacement history snapshot arrives", () => {
    const renderOwner = (history: GxpCertificateVersionHistory) => <><button type="button">Giấy chứng nhận đang chọn</button>
      <PersistedCertificateHistory kind="gxp" state={{ status: "ready", data: history }} /></>;
    const { rerender } = render(renderOwner(data));
    const aggregateControl = screen.getByRole("button", { name: "Giấy chứng nhận đang chọn" });
    aggregateControl.focus();
    rerender(renderOwner({ ...data, certificate_id: "aggregate-b", latest_version_id: "version-b",
      versions: [{ ...data.versions[0], certificate_version_id: "version-b", certificate_number: "aggregate B" }] }));
    expect(aggregateControl).toHaveFocus();
    expect(screen.queryByText("version-old")).not.toBeInTheDocument();
  });
  it("keeps historical scopes separate from the latest snapshot and never infers lifecycle", () => {
    render(<PersistedCertificateHistory kind="gxp" state={{ status: "ready", data }} />);
    fireEvent.click(screen.getByText("Các phiên bản GPs đã lưu"));
    expect(screen.getByText("2 phiên bản đã lưu")).toBeInTheDocument();
    expect(screen.getByText("scope 2 second line")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Phiên bản đã lưu"), { target: { value: "version-old" } });
    expect(screen.getByText("scope 1 second line")).toBeInTheDocument();
    expect(screen.queryByText("scope 2 second line")).not.toBeInTheDocument();
    expect(screen.getByText("Chưa có trạng thái được xác nhận trong bản ghi")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
  it.each([0, 1])("reports %i stored versions without fabricating history", count => {
    render(<PersistedCertificateHistory kind="gxp" state={{ status: "ready", data: { ...data, versions: data.versions.slice(0, count) } }} />);
    fireEvent.click(screen.getByText("Các phiên bản GPs đã lưu"));
    expect(screen.getByText(`${count} phiên bản đã lưu`)).toBeInTheDocument();
    if (!count) expect(screen.getByRole("status")).toHaveTextContent("Giấy chứng nhận chưa có phiên bản được lưu.");
  });
  it.each([401, 403, 404, 409, 500, null])("shows an owned read error %s without current-detail fallback or retry", httpStatus => {
    render(<PersistedCertificateHistory kind="gxp" state={{ status: "error", httpStatus }} />);
    fireEvent.click(screen.getByText("Các phiên bản GPs đã lưu"));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

it("keeps DDK prose and FK links in their exact version, separate from source tokens", () => {
  const history: BusinessEligibilityVersionHistory = {
    business_eligibility_certificate_id: "ddk-a", legacy_dkkd_id: 42, site_id: "site", company_id: "company",
    aggregate_latest_flag: true, latest_version_id: "ddk-v2", latest_selection_method: "max_persisted_version_no",
    gxp_source_tokens_included: false, canonical_link_status: "stored_fk_only_not_validated",
    versions: [2, 1].map(n => ({
      business_eligibility_version_id: `ddk-v${n}`, version_no: n, row_version: 9, certificate_number: "same-number",
      issued_on: null, expires_on: null, professional_responsible_person_name: `person-${n}`,
      quality_assurance_person_name: null, professional_qualification_text: null, professional_license_number: null,
      professional_license_issued_on: null, professional_license_issuer: null, responsible_license_issued_on: null,
      responsible_license_issuer: null, decision_reference: null, issuance_sequence_text: null,
      issuance_history_text: "issued 4 times; adjusted 3 times", business_activity_text: null,
      current_status_text: null, handled_by_name: null, application_dossier_reference: null, notes: null,
      stored_link_records: n === 2 ? [{ link_id: "link-new", certificate_id: "cert-new", link_role: "basis" }] : [],
    })),
  };
  render(<PersistedCertificateHistory kind="ddk" state={{ status: "ready", data: history }} />);
  fireEvent.click(screen.getByText("Các phiên bản ĐĐK đã lưu"));
  expect(screen.getByRole("combobox").children).toHaveLength(2);
  expect(screen.getByText("cert-new")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Phiên bản đã lưu"), { target: { value: "ddk-v1" } });
  expect(screen.queryByText("cert-new")).not.toBeInTheDocument();
  expect(screen.getByText("person-1")).toBeInTheDocument();
  expect(screen.getByText("Không có bản ghi liên kết canonical được lưu cho phiên bản.")).toBeInTheDocument();
  expect(screen.getByText("issued 4 times; adjusted 3 times")).toBeInTheDocument();
  expect(screen.getByRole("combobox").children).toHaveLength(2);
});
