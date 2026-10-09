import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GxpCertificateWorkspace } from "./GxpCertificateWorkspace";
import type { GxpCertificateDetail, GxpCertificateListItem } from "../../types";

const items: GxpCertificateListItem[] = [{
  certificate_id: "cert-1", site_id: "site-1", case_id: "case-1", certificate_type: "GMP", line_code: "A", production_line_id: "line-1", production_line_code: "A", production_line_identity_state: "canonical",
  context_match_kind: "exact_line", latest_flag: true, certificate_number: "GCN-001", issue_date: "2026-09-01",
  expiry_date: "2027-09-01", applicable_standard: "WHO-GMP", issuing_authority: null, status: "active",
}];

function detail(editAvailable = true): GxpCertificateDetail {
  return {
    certificate_id: "cert-1", row_version: 7, site_id: "site-1", case_id: "case-1", certificate_type: "GMP", line_code: "A", production_line_id: "line-1", production_line_code: "A", production_line_identity_state: "canonical",
    issuance_basis: "inspection_case", latest_flag: true, certificate_number: "GCN-001", issue_date: "2026-09-01", expiry_date: "2027-09-01",
    applicable_standard: "WHO-GMP", issuing_authority: null, status: "active", facility_name: "Nhà máy A", address: null,
    company_name: "Công ty A", company_legal_address: null, scope_summary: "Display-only summary", limitation_text: null,
    source_description: null,
    scopes: [
      { id: "scope-1", scope_key: "alpha", scope_text: "Phạm vi Alpha", language_code: "vi", sort_order: 3 },
      { id: "scope-2", scope_key: null, scope_text: "Scope Beta", language_code: "en", sort_order: 9 },
    ],
    action_readiness: [{ action_key: "edit_latest_version", label: "Cập nhật chứng nhận", available: editAvailable, reason_code: editAvailable ? null : "missing_permission", required_permissions: ["certificate.edit"], expected_version: 7 }],
  };
}

function renderWorkspace(onEditLatestVersion = vi.fn().mockResolvedValue(undefined), editAvailable = true) {
  render(<GxpCertificateWorkspace
    detail={detail(editAvailable)} detailError={null} detailLoading={false} items={items} listError={null} listLoading={false}
    onEditLatestVersion={onEditLatestVersion} onPromoteCurrent={vi.fn().mockResolvedValue(undefined)} onSelectCertificate={vi.fn()}
    promotionError={null} promotionPending={false} selectedCertificateId="cert-1"
  />);
  return onEditLatestVersion;
}

describe("GxP certificate keyboard and identity", () => {
  function keyboardProps() {
    const props = { items, detail: detail(), listLoading: false, listError: null, selectedCertificateId: "cert-1", onSelectCertificate: vi.fn(), detailLoading: false, detailError: null, onPromoteCurrent: vi.fn(), promotionError: null, promotionPending: false, onEditLatestVersion: vi.fn() };
    return { ...props, items: [items[0], { ...items[0], certificate_id: "cert-1-2" }] };
  }
  it("moves focus independently and activates exact IDs even with identical reference numbers", () => {
    const props = keyboardProps();
    render(<GxpCertificateWorkspace {...props} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.filter(row => row.tabIndex === 0)).toHaveLength(1);
    act(() => rows[0].focus());
    fireEvent.keyDown(rows[0], { key: "ArrowDown" });
    expect(rows[1]).toHaveFocus();
    expect(rows[0]).toHaveAttribute("aria-selected", "true");
    expect(rows[1]).toHaveAttribute("aria-selected", "false");
    expect(props.onSelectCertificate).not.toHaveBeenCalled();
    fireEvent.keyDown(rows[1], { key: "Enter" });
    expect(props.onSelectCertificate).toHaveBeenLastCalledWith("cert-1-2");
    fireEvent.keyDown(rows[1], { key: "Home" });
    expect(rows[0]).toHaveFocus();
    fireEvent.keyDown(rows[0], { key: "End" });
    expect(rows[1]).toHaveFocus();
    fireEvent.keyDown(rows[1], { key: " " });
    fireEvent.click(rows[1]);
    expect(props.onSelectCertificate.mock.calls).toEqual([["cert-1-2"], ["cert-1-2"], ["cert-1-2"]]);
    expect(screen.queryByRole("grid")).not.toBeInTheDocument();
  });
  it.each(["loading", "error", "empty"])("renders initial %s without exposing stale detail", (state) => {
    const props = keyboardProps();
    const { container } = render(<GxpCertificateWorkspace {...props} items={[]} selectedCertificateId={null} detail={null} listLoading={state === "loading"} listError={state === "error" ? "list unavailable" : null} />);
    if (state === "error") expect(screen.getByRole("alert")).toHaveTextContent("list unavailable");
    else expect(screen.getByText(state === "loading" ? "Đang tải giấy chứng nhận GxP" : "Chưa có giấy chứng nhận GxP")).toBeInTheDocument();
    expect(container.querySelector(".certificate-detail-grid")).not.toBeInTheDocument();
    expect(props.onSelectCertificate).not.toHaveBeenCalled();
  });
  it("retains the focused row across refresh, loading and error without activation", () => {
    const props = keyboardProps();
    const { rerender } = render(<GxpCertificateWorkspace {...props} />);
    const row = screen.getAllByRole("row")[2];
    act(() => row.focus());
    rerender(<GxpCertificateWorkspace {...props} listLoading={true} detailLoading={true} detail={null} />);
    expect(row).toHaveFocus();
    expect(screen.getByRole("table")).toHaveAttribute("aria-busy", "true");
    rerender(<GxpCertificateWorkspace {...props} items={props.items.map(item => ({ ...item }))} listError="refresh failed" />);
    expect(row).toHaveFocus();
    expect(screen.getByRole("alert")).toHaveTextContent("refresh failed");
    fireEvent.keyDown(row, { key: "Enter" });
    expect(props.onSelectCertificate).not.toHaveBeenCalled();
    rerender(<GxpCertificateWorkspace {...props} />);
    expect(row).toHaveFocus();
  });
  it("hides mismatched detail and actions in the very first selected-ID render", () => {
    const props = keyboardProps();
    const { container, rerender } = render(<GxpCertificateWorkspace {...props} />);
    expect(container.querySelector(".certificate-detail-grid")).toBeInTheDocument();
    rerender(<GxpCertificateWorkspace {...props} selectedCertificateId="cert-1-2" />);
    expect(container.querySelector(".certificate-detail-grid")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Cập nhật/ })).not.toBeInTheDocument();
    rerender(<GxpCertificateWorkspace {...props} selectedCertificateId="cert-1-2" detail={{ ...props.detail!, certificate_id: "cert-1-2", facility_name: "Certificate B detail" }} />);
    expect(screen.getByText("Certificate B detail")).toBeInTheDocument();
  });
  it("keeps draft, focus and original concurrency token when the same certificate refreshes", async () => {
    const props = keyboardProps();
    props.onEditLatestVersion.mockResolvedValue(undefined);
    const { rerender } = render(<GxpCertificateWorkspace {...props} />);
    const trigger = screen.getByRole("button", { name: "Cập nhật chứng nhận" });
    trigger.focus();
    fireEvent.click(trigger);
    const input = screen.getByRole("textbox", { name: "Số GCN" });
    expect(input).toHaveFocus();
    fireEvent.change(input, { target: { value: "draft survives" } });
    rerender(<GxpCertificateWorkspace {...props} detail={null} detailLoading={true} />);
    expect(screen.getByRole("button", { name: "Lưu thay đổi" })).toBeDisabled();
    expect(input).toHaveValue("draft survives");
    expect(input).toHaveFocus();
    rerender(<GxpCertificateWorkspace {...props} detail={{ ...detail(), row_version: 8, action_readiness: [{ ...detail().action_readiness![0], expected_version: 8 }] }} />);
    rerender(<GxpCertificateWorkspace {...props} detail={detail(false)} />);
    expect(screen.getByRole("button", { name: "Lưu thay đổi" })).toBeDisabled();
    expect(input).toHaveValue("draft survives");
    rerender(<GxpCertificateWorkspace {...props} detail={{ ...detail(), row_version: 8 }} />);
    expect(input).toHaveValue("draft survives");
    const cancel = screen.getByRole("button", { name: "Hủy" });
    cancel.focus();
    fireEvent.keyDown(cancel, { key: "Tab" });
    expect(input).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Lưu thay đổi" }));
    await waitFor(() => expect(props.onEditLatestVersion).toHaveBeenCalledWith(expect.objectContaining({ expected_version: 7, certificate_number: "draft survives" })));
    // During loading the original trigger was removed; avoid stealing focus.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("GxpCertificateWorkspace edit form", () => {
  it("renders no edit control without backend action and disables unavailable backend action", () => {
    render(<GxpCertificateWorkspace
      detail={{ ...detail(), action_readiness: [] }} detailError={null} detailLoading={false} items={items} listError={null} listLoading={false}
      onEditLatestVersion={vi.fn()} onPromoteCurrent={vi.fn()} onSelectCertificate={vi.fn()} promotionError={null} promotionPending={false} selectedCertificateId="cert-1"
    />);
    expect(screen.queryByRole("button", { name: "Cập nhật chứng nhận" })).not.toBeInTheDocument();

    renderWorkspace(vi.fn(), false);
    expect(screen.getByRole("button", { name: "Cập nhật chứng nhận" })).toBeDisabled();
  });

  it("round-trips structured scopes from detail, supports edits, addition, removal, and cancel", async () => {
    const onEditLatestVersion = renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Cập nhật chứng nhận" }));
    const dialog = screen.getByRole("dialog", { name: "Sửa giấy chứng nhận GxP" });
    expect(within(dialog).getByRole("textbox", { name: "Nội dung phạm vi 1" })).toHaveValue("Phạm vi Alpha");
    expect(within(dialog).getByRole("textbox", { name: "Ngôn ngữ phạm vi 2" })).toHaveValue("en");
    expect(within(dialog).queryByDisplayValue("Display-only summary")).not.toBeInTheDocument();

    fireEvent.change(within(dialog).getByRole("textbox", { name: "Nội dung phạm vi 1" }), { target: { value: "Alpha đã sửa" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Thêm phạm vi" }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Mã phạm vi 3" }), { target: { value: "gamma" } });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Nội dung phạm vi 3" }), { target: { value: "Gamma" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Xóa phạm vi 2" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() => expect(onEditLatestVersion).toHaveBeenCalledWith(expect.objectContaining({
      expected_version: 7,
      scopes: [
        { scope_key: "alpha", scope_text: "Alpha đã sửa", language_code: "vi", sort_order: 3 },
        { scope_key: "gamma", scope_text: "Gamma", language_code: "vi", sort_order: 10 },
      ],
    })));

    fireEvent.click(screen.getByRole("button", { name: "Cập nhật chứng nhận" }));
    fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
    expect(screen.queryByRole("dialog", { name: "Sửa giấy chứng nhận GxP" })).not.toBeInTheDocument();
  });

  it.each([403, 422])("keeps the form open and displays mutation failures (%s)", async (status) => {
    const error = Object.assign(new Error(`${status} failure`), { status });
    const onEditLatestVersion = renderWorkspace(vi.fn().mockRejectedValue(error));
    fireEvent.click(screen.getByRole("button", { name: "Cập nhật chứng nhận" }));
    const dialog = screen.getByRole("dialog", { name: "Sửa giấy chứng nhận GxP" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Lưu thay đổi" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(`${status} failure`);
    expect(onEditLatestVersion).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("dialog", { name: "Sửa giấy chứng nhận GxP" })).toBeInTheDocument();
  });

  it("preserves a stale draft, displays 409 and prevents a blind retry", async () => {
    const error = Object.assign(new Error("Dữ liệu chứng nhận đã thay đổi."), { status: 409 });
    const onEditLatestVersion = renderWorkspace(vi.fn().mockRejectedValue(error));
    fireEvent.click(screen.getByRole("button", { name: "Cập nhật chứng nhận" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Số GCN" }), { target: { value: "unsaved draft" } });
    fireEvent.click(within(screen.getByRole("dialog", { name: "Sửa giấy chứng nhận GxP" })).getByRole("button", { name: "Lưu thay đổi" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Dữ liệu chứng nhận đã thay đổi.");
    expect(onEditLatestVersion).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("textbox", { name: "Số GCN" })).toHaveValue("unsaved draft");
    expect(screen.getByRole("textbox", { name: "Số GCN" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Lưu thay đổi" })).toBeDisabled();
  });
});
