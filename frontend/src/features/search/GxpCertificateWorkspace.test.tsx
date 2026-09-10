import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GxpCertificateWorkspace } from "./GxpCertificateWorkspace";
import type { GxpCertificateDetail, GxpCertificateListItem } from "../../types";

const items: GxpCertificateListItem[] = [{
  certificate_id: "cert-1", site_id: "site-1", case_id: "case-1", certificate_type: "GMP", line_code: "A",
  context_match_kind: "exact_line", latest_flag: true, certificate_number: "GCN-001", issue_date: "2026-09-01",
  expiry_date: "2027-09-01", applicable_standard: "WHO-GMP", issuing_authority: null, status: "active",
}];

function detail(editAvailable = true): GxpCertificateDetail {
  return {
    certificate_id: "cert-1", row_version: 7, site_id: "site-1", case_id: "case-1", certificate_type: "GMP", line_code: "A",
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

  it("closes a stale draft and displays the conflict in the action area", async () => {
    const error = Object.assign(new Error("Dữ liệu chứng nhận đã thay đổi."), { status: 409 });
    const onEditLatestVersion = renderWorkspace(vi.fn().mockRejectedValue(error));
    fireEvent.click(screen.getByRole("button", { name: "Cập nhật chứng nhận" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Sửa giấy chứng nhận GxP" })).getByRole("button", { name: "Lưu thay đổi" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Dữ liệu chứng nhận đã thay đổi.");
    expect(onEditLatestVersion).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog", { name: "Sửa giấy chứng nhận GxP" })).not.toBeInTheDocument();
  });
});
