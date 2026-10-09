import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BusinessEligibilityWorkspace } from "./BusinessEligibilityWorkspace";
import type { BusinessEligibilityDetail, BusinessEligibilityListItem, GxpCertificateListItem } from "../../types";

const items: BusinessEligibilityListItem[] = [{
  business_eligibility_certificate_id: "dkkd-1",
  site_id: "site-1",
  company_id: "company-1",
  latest_flag: false,
  certificate_number: "DDKD-001",
  issued_on: "2026-10-01",
  issuance_sequence_text: "1",
  current_status_text: null,
}];

const basis: GxpCertificateListItem[] = [{
  certificate_id: "cert-1",
  site_id: "site-1",
  case_id: "case-1",
  certificate_type: "GMP",
  line_code: "A",
  production_line_id: "line-1",
  production_line_code: "A",
  production_line_identity_state: "canonical",
  context_match_kind: "exact_line",
  latest_flag: true,
  certificate_number: "GMP-001",
  issue_date: "2026-09-01",
  expiry_date: "2027-09-01",
  applicable_standard: "WHO-GMP",
  issuing_authority: null,
  status: "active",
}];

function detail(): BusinessEligibilityDetail {
  return {
    business_eligibility_certificate_id: "dkkd-1",
    row_version: 4,
    site_id: "site-1",
    company_id: "company-1",
    latest_flag: false,
    certificate_number: "DDKD-001",
    issued_on: "2026-10-01",
    expires_on: "2027-10-01",
    notes: "ghi chú",
    decision_reference: null,
    issuance_sequence_text: "1",
    issuance_history_text: null,
    company_name: "Công ty A",
    company_legal_address: null,
    facility_name: "Nhà máy A",
    address: null,
    professional_responsible_person_name: "PTCM A",
    quality_assurance_person_name: null,
    professional_qualification_text: null,
    professional_license_number: null,
    professional_license_issued_on: null,
    professional_license_issuer: null,
    responsible_license_issued_on: null,
    responsible_license_issuer: null,
    business_activity_text: null,
    current_status_text: null,
    handled_by_name: null,
    application_dossier_reference: null,
    replaces_certificate_number: null,
    replaced_by_certificate_number: null,
    linked_gxp_certificates: [{
      certificate_id: "cert-1",
      certificate_type: "GMP",
      line_code: "A",
      certificate_number: "GMP-001",
      issue_date: "2026-09-01",
      link_role: "source_certificate",
    }],
    action_readiness: [
      { action_key: "edit_latest_version", label: "Cập nhật GCN đủ điều kiện", available: true, reason_code: null, required_permissions: ["certificate.edit"], expected_version: 4 },
      { action_key: "promote_current", label: "Đặt làm GCN đủ điều kiện hiện hành", available: true, reason_code: null, required_permissions: ["certificate.approve"], expected_version: 4 },
    ],
  };
}

function baseProps() {
  return {
    items,
    listLoading: false,
    listError: null,
    selectedCertificateId: "dkkd-1",
    onSelectCertificate: vi.fn(),
    detail: detail(),
    detailLoading: false,
    detailError: null,
    issueReadiness: { action_key: "issue_business_eligibility" as const, label: "Cấp GCN đủ điều kiện", available: true, reason_code: null, required_permissions: ["certificate.issue"] },
    basisCertificates: basis,
    basisLoading: false,
    basisError: null,
    onIssue: vi.fn().mockResolvedValue(undefined),
    onEditLatestVersion: vi.fn().mockResolvedValue(undefined),
    onPromoteCurrent: vi.fn().mockResolvedValue(undefined),
    promotionError: null,
    promotionPending: false,
  };
}

describe("Eligibility certificate keyboard and identity", () => {
  function keyboardProps() {
    const props = baseProps();
    return { ...props, items: [items[0], { ...items[0], business_eligibility_certificate_id: "dkkd-1-2" }] };
  }
  it("moves focus independently and activates exact IDs even with identical reference numbers", () => {
    const props = keyboardProps();
    render(<BusinessEligibilityWorkspace {...props} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.filter(row => row.tabIndex === 0)).toHaveLength(1);
    act(() => rows[0].focus());
    fireEvent.keyDown(rows[0], { key: "ArrowDown" });
    expect(rows[1]).toHaveFocus();
    expect(rows[0]).toHaveAttribute("aria-selected", "true");
    expect(rows[1]).toHaveAttribute("aria-selected", "false");
    expect(props.onSelectCertificate).not.toHaveBeenCalled();
    fireEvent.keyDown(rows[1], { key: "Enter" });
    expect(props.onSelectCertificate).toHaveBeenLastCalledWith("dkkd-1-2");
    fireEvent.keyDown(rows[1], { key: "Home" });
    expect(rows[0]).toHaveFocus();
    fireEvent.keyDown(rows[0], { key: "End" });
    expect(rows[1]).toHaveFocus();
    fireEvent.keyDown(rows[1], { key: " " });
    fireEvent.click(rows[1]);
    expect(props.onSelectCertificate.mock.calls).toEqual([["dkkd-1-2"], ["dkkd-1-2"], ["dkkd-1-2"]]);
    expect(screen.queryByRole("grid")).not.toBeInTheDocument();
  });
  it.each(["loading", "error", "empty"])("renders initial %s without exposing stale detail", (state) => {
    const props = keyboardProps();
    const { container } = render(<BusinessEligibilityWorkspace {...props} issueReadiness={null} items={[]} selectedCertificateId={null} detail={null} listLoading={state === "loading"} listError={state === "error" ? "list unavailable" : null} />);
    if (state === "error") expect(screen.getByRole("alert")).toHaveTextContent("list unavailable");
    else expect(screen.getByText(state === "loading" ? "Đang tải GCN đủ điều kiện" : "Chưa có GCN đủ điều kiện")).toBeInTheDocument();
    expect(container.querySelector(".certificate-detail-grid")).not.toBeInTheDocument();
    expect(props.onSelectCertificate).not.toHaveBeenCalled();
  });
  it("retains the focused row across refresh, loading and error without activation", () => {
    const props = keyboardProps();
    const { rerender } = render(<BusinessEligibilityWorkspace {...props} />);
    const row = screen.getAllByRole("row")[2];
    act(() => row.focus());
    rerender(<BusinessEligibilityWorkspace {...props} listLoading={true} detailLoading={true} detail={null} />);
    expect(row).toHaveFocus();
    expect(screen.getByRole("table")).toHaveAttribute("aria-busy", "true");
    rerender(<BusinessEligibilityWorkspace {...props} items={props.items.map(item => ({ ...item }))} listError="refresh failed" />);
    expect(row).toHaveFocus();
    expect(screen.getByRole("alert")).toHaveTextContent("refresh failed");
    fireEvent.keyDown(row, { key: "Enter" });
    expect(props.onSelectCertificate).not.toHaveBeenCalled();
    rerender(<BusinessEligibilityWorkspace {...props} />);
    expect(row).toHaveFocus();
  });
  it("hides mismatched detail and actions in the very first selected-ID render", () => {
    const props = keyboardProps();
    const { container, rerender } = render(<BusinessEligibilityWorkspace {...props} />);
    expect(container.querySelector(".certificate-detail-grid")).toBeInTheDocument();
    rerender(<BusinessEligibilityWorkspace {...props} selectedCertificateId="dkkd-1-2" />);
    expect(container.querySelector(".certificate-detail-grid")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Cập nhật/ })).not.toBeInTheDocument();
    rerender(<BusinessEligibilityWorkspace {...props} selectedCertificateId="dkkd-1-2" detail={{ ...props.detail!, business_eligibility_certificate_id: "dkkd-1-2", facility_name: "Certificate B detail" }} />);
    expect(screen.getByText("Certificate B detail")).toBeInTheDocument();
  });
  it("retains draft and version token across same-certificate refresh and restores dialog focus", async () => {
    const props = keyboardProps();
    const { rerender } = render(<BusinessEligibilityWorkspace {...props} />);
    const trigger = screen.getByRole("button", { name: "Cập nhật GCN đủ điều kiện" });
    trigger.focus();
    fireEvent.click(trigger);
    const input = screen.getByRole("textbox", { name: "Số GCN ĐĐK" });
    expect(input).toHaveFocus();
    fireEvent.change(input, { target: { value: "draft survives" } });
    rerender(<BusinessEligibilityWorkspace {...props} detail={{ ...detail(), row_version: 5, replaces_certificate_number: "predecessor", replaced_by_certificate_number: "successor" }} />);
    expect(input).toHaveValue("draft survives");
    expect(screen.getByText("predecessor")).toBeInTheDocument();
    expect(screen.getByText("successor")).toBeInTheDocument();
    rerender(<BusinessEligibilityWorkspace {...props} detail={{ ...detail(), action_readiness: detail().action_readiness!.map(action => ({ ...action, available: false, reason_code: "missing_permission" })) }} />);
    expect(screen.getByRole("button", { name: "Lưu thay đổi" })).toBeDisabled();
    expect(input).toHaveValue("draft survives");
    rerender(<BusinessEligibilityWorkspace {...props} />);
    const cancel = screen.getByRole("button", { name: "Hủy" });
    cancel.focus();
    fireEvent.keyDown(cancel, { key: "Tab" });
    expect(input).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Lưu thay đổi" }));
    await waitFor(() => expect(props.onEditLatestVersion).toHaveBeenCalledWith(expect.objectContaining({ expected_version: 4, certificate_number: "draft survives" })));
    expect(trigger).toHaveFocus();
  });
});

describe("BusinessEligibilityWorkspace write workflow", () => {
  it.each(["issue", "edit"])("contains focus while %s is pending, ignores Escape and restores trigger after save", async mode => {
    const props = baseProps();
    let finish!: () => void;
    const save = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
    if (mode === "issue") props.onIssue = save; else props.onEditLatestVersion = save;
    render(<BusinessEligibilityWorkspace {...props} />);
    const trigger = screen.getByRole("button", { name: mode === "issue" ? "Cấp GCN đủ điều kiện" : "Cập nhật GCN đủ điều kiện" });
    act(() => trigger.focus());
    fireEvent.click(trigger);
    const input = screen.getByRole("textbox", { name: "Số GCN ĐĐK" });
    expect(input).toHaveFocus();
    fireEvent.change(input, { target: { value: "pending draft" } });
    fireEvent.click(screen.getByRole("button", { name: mode === "issue" ? "Cấp GCN" : "Lưu thay đổi" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveFocus();
    for (const shiftKey of [false, true]) {
      const event = new KeyboardEvent("keydown", { key: "Tab", shiftKey, bubbles: true, cancelable: true });
      act(() => dialog.dispatchEvent(event));
      expect(event.defaultPrevented).toBe(true);
      expect(dialog).toHaveFocus();
    }
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(dialog).toBeInTheDocument();
    expect(input).toHaveValue("pending draft");
    expect(save).toHaveBeenCalledTimes(1);
    await act(async () => finish());
    expect(trigger).toHaveFocus();
    fireEvent.click(trigger);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
  it("allows first issue when the list is empty and does not auto-promote", async () => {
    const props = baseProps();
    render(<BusinessEligibilityWorkspace {...props} detail={null} items={[]} selectedCertificateId={null} />);

    fireEvent.click(screen.getByRole("button", { name: "Cấp GCN đủ điều kiện" }));
    const dialog = screen.getByRole("dialog", { name: "Cấp GCN đủ điều kiện" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Số GCN ĐĐK" }), { target: { value: "DDKD-NEW" } });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /Chọn căn cứ GMP A · GMP-001/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Cấp GCN" }));

    await waitFor(() => expect(props.onIssue).toHaveBeenCalledWith(expect.objectContaining({
      certificate_number: "DDKD-NEW",
      linked_certificates: [{ certificate_id: "cert-1", link_role: "source_certificate" }],
    })));
    expect(props.onPromoteCurrent).not.toHaveBeenCalled();
  });

  it("edits only the canonical mutable surface and sends the parent expected_version", async () => {
    const props = baseProps();
    render(<BusinessEligibilityWorkspace {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Cập nhật GCN đủ điều kiện" }));
    const dialog = screen.getByRole("dialog", { name: "Cập nhật GCN đủ điều kiện" });
    expect(within(dialog).getByRole("textbox", { name: "Số GCN ĐĐK" })).toHaveValue("DDKD-001");
    expect(within(dialog).queryByText(/QĐ cấp/i)).not.toBeInTheDocument();
    fireEvent.change(within(dialog).getByRole("combobox", { name: /Vai trò căn cứ GMP A · GMP-001/ }), { target: { value: "replacement_certificate" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() => expect(props.onEditLatestVersion).toHaveBeenCalledWith(expect.objectContaining({
      expected_version: 4,
      certificate_number: "DDKD-001",
      expires_on: "2027-10-01",
      notes: "ghi chú",
      linked_certificates: [{ certificate_id: "cert-1", link_role: "replacement_certificate" }],
    })));
  });

  it("uses backend promotion readiness and the projected expected_version", () => {
    const props = baseProps();
    render(<BusinessEligibilityWorkspace {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Đặt làm GCN đủ điều kiện hiện hành" }));
    expect(props.onPromoteCurrent).toHaveBeenCalledWith(4);
  });

  it.each([403, 422])("keeps edit dialog open for non-stale mutation failures (%s)", async (status) => {
    const props = baseProps();
    props.onEditLatestVersion.mockRejectedValue(Object.assign(new Error(`${status} failure`), { status }));
    render(<BusinessEligibilityWorkspace {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Cập nhật GCN đủ điều kiện" }));
    const dialog = screen.getByRole("dialog", { name: "Cập nhật GCN đủ điều kiện" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Lưu thay đổi" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(`${status} failure`);
    expect(screen.getByRole("dialog", { name: "Cập nhật GCN đủ điều kiện" })).toBeInTheDocument();
  });

  it("preserves a stale edit and surfaces 409 without retry", async () => {
    const props = baseProps();
    props.onEditLatestVersion.mockRejectedValue(Object.assign(new Error("Dữ liệu GCN đủ điều kiện đã thay đổi."), { status: 409 }));
    render(<BusinessEligibilityWorkspace {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Cập nhật GCN đủ điều kiện" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Số GCN ĐĐK" }), { target: { value: "unsaved draft" } });
    fireEvent.click(within(screen.getByRole("dialog", { name: "Cập nhật GCN đủ điều kiện" })).getByRole("button", { name: "Lưu thay đổi" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Dữ liệu GCN đủ điều kiện đã thay đổi.");
    expect(props.onEditLatestVersion).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("textbox", { name: "Số GCN ĐĐK" })).toHaveValue("unsaved draft");
    expect(screen.getByRole("textbox", { name: "Số GCN ĐĐK" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Lưu thay đổi" })).toBeDisabled();
  });

  it("keeps an immediately opened edit dialog stable while the same certificate version refreshes", () => {
    const props = baseProps();
    const { rerender } = render(<BusinessEligibilityWorkspace {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Cập nhật GCN đủ điều kiện" }));
    expect(screen.getByRole("dialog", { name: "Cập nhật GCN đủ điều kiện" })).toBeInTheDocument();

    rerender(<BusinessEligibilityWorkspace {...props} detail={{ ...detail() }} />);
    expect(screen.getByRole("dialog", { name: "Cập nhật GCN đủ điều kiện" })).toBeInTheDocument();

    rerender(<BusinessEligibilityWorkspace {...props} detail={{ ...detail(), row_version: 5 }} />);
    expect(screen.getByRole("dialog", { name: "Cập nhật GCN đủ điều kiện" })).toBeInTheDocument();
  });

  it("does not expose write controls when backend readiness is absent", () => {
    const props = baseProps();
    render(<BusinessEligibilityWorkspace {...props} issueReadiness={null} detail={{ ...detail(), action_readiness: [] }} />);
    expect(screen.queryByRole("button", { name: "Cấp GCN đủ điều kiện" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cập nhật GCN đủ điều kiện" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Đặt làm GCN đủ điều kiện hiện hành" })).not.toBeInTheDocument();
  });
});
