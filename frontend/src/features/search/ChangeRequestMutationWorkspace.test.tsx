import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  BusinessEligibilityDetail,
  ChangeRequestWorkspace,
  GxpCertificateDetail,
  GxpCertificateListItem,
} from "../../types";
import { ChangeRequestMutationWorkspace, type ChangeRequestMutationHandlers } from "./ChangeRequestMutationWorkspace";

function buildWorkspace(overrides: Partial<ChangeRequestWorkspace> = {}): ChangeRequestWorkspace {
  return {
    id: "change-1",
    row_version: 7,
    legacy_change_request_id: null,
    site_id: "site-1",
    facility_name: "Nhà máy A",
    company_name: "Công ty A",
    scope_label: "Đổi kho",
    description: "Mô tả cũ",
    submitted_on: "2026-10-01",
    requester_name: "QA",
    state: "under_review",
    handled_on: null,
    handled_by_name: null,
    result_label: null,
    effective_on: null,
    approval_reference: null,
    documents: { items: [] },
    affected_artifacts: [
      {
        link_id: "affected-cert-1",
        artifact_kind: "certificate",
        artifact_id: "cert-current-1",
        source_affected_artifact_id: null,
      },
      {
        link_id: "affected-dkkd-1",
        artifact_kind: "business_eligibility_certificate",
        artifact_id: "dkkd-current-1",
        source_affected_artifact_id: null,
      },
    ],
    issued_artifacts: [
      {
        link_id: "issued-cert-1",
        artifact_kind: "certificate",
        artifact_id: "cert-successor-1",
        source_affected_artifact_id: "affected-cert-1",
      },
      {
        link_id: "issued-dkkd-1",
        artifact_kind: "business_eligibility_certificate",
        artifact_id: "dkkd-successor-1",
        source_affected_artifact_id: "affected-dkkd-1",
      },
    ],
    details: [
      {
        change_detail_id: "detail-1",
        legacy_change_detail_id: null,
        classification_id: 1,
        classification_label: "Địa chỉ",
        approval_status: null,
        old_value: "A",
        new_value: "B",
        note: null,
      },
    ],
    action_readiness: [
      { action_key: "edit_change_request", label: "Sửa đề nghị", available: true, reason_code: null, required_permissions: ["change_request.edit"], expected_version: 7, target_state: null },
      { action_key: "add_change_detail", label: "Thêm chi tiết", available: true, reason_code: null, required_permissions: ["change_request.edit"], expected_version: 7, target_state: null },
      { action_key: "edit_change_detail", label: "Sửa chi tiết", available: true, reason_code: null, required_permissions: ["change_request.edit"], expected_version: 7, target_state: null },
      { action_key: "edit_change_approval", label: "Cập nhật xử lý", available: true, reason_code: null, required_permissions: ["change_request.approve"], expected_version: 7, target_state: null },
      { action_key: "issue_certificate_successor:affected-cert-1", label: "Tạo GCN điều chỉnh", available: true, reason_code: null, required_permissions: ["change_request.edit", "certificate.issue"], expected_version: 7, target_state: null, source_affected_artifact_id: "affected-cert-1" },
      { action_key: "issue_business_eligibility_successor:affected-dkkd-1", label: "Tạo GCN ĐĐK điều chỉnh", available: true, reason_code: null, required_permissions: ["change_request.edit", "certificate.issue"], expected_version: 7, target_state: null, source_affected_artifact_id: "affected-dkkd-1" },
      { action_key: "edit_issued_certificate:issued-cert-1", label: "Cập nhật chứng nhận", available: true, reason_code: null, required_permissions: ["certificate.edit"], expected_version: 11, target_state: null, source_affected_artifact_id: "affected-cert-1", issued_artifact_link_id: "issued-cert-1", target_artifact_kind: "certificate", target_artifact_id: "cert-successor-1" },
      { action_key: "promote_issued_certificate:issued-cert-1", label: "Đặt làm chứng nhận hiện hành", available: true, reason_code: null, required_permissions: ["certificate.approve"], expected_version: 11, target_state: null, source_affected_artifact_id: "affected-cert-1", issued_artifact_link_id: "issued-cert-1", target_artifact_kind: "certificate", target_artifact_id: "cert-successor-1" },
      { action_key: "edit_issued_business_eligibility:issued-dkkd-1", label: "Cập nhật GCN đủ điều kiện", available: true, reason_code: null, required_permissions: ["certificate.edit"], expected_version: 13, target_state: null, source_affected_artifact_id: "affected-dkkd-1", issued_artifact_link_id: "issued-dkkd-1", target_artifact_kind: "business_eligibility_certificate", target_artifact_id: "dkkd-successor-1" },
      { action_key: "promote_issued_business_eligibility:issued-dkkd-1", label: "Đặt làm GCN đủ điều kiện hiện hành", available: true, reason_code: null, required_permissions: ["certificate.approve"], expected_version: 13, target_state: null, source_affected_artifact_id: "affected-dkkd-1", issued_artifact_link_id: "issued-dkkd-1", target_artifact_kind: "business_eligibility_certificate", target_artifact_id: "dkkd-successor-1" },
      { action_key: "transition_change_request:not-derived", label: "Chấp nhận", available: true, reason_code: null, required_permissions: ["change_request.approve"], expected_version: 7, target_state: "accepted" },
    ],
    ...overrides,
  };
}

function buildHandlers(): ChangeRequestMutationHandlers {
  return {
    onUpdateHeader: vi.fn().mockResolvedValue(undefined),
    onCreateDetail: vi.fn().mockResolvedValue(undefined),
    onUpdateDetail: vi.fn().mockResolvedValue(undefined),
    onUpsertApproval: vi.fn().mockResolvedValue(undefined),
    onTransition: vi.fn().mockResolvedValue(undefined),
    onIssueBusinessEligibilitySuccessor: vi.fn().mockResolvedValue(undefined),
    onIssueCertificateSuccessor: vi.fn().mockResolvedValue(undefined),
    onPromoteIssuedBusinessEligibility: vi.fn().mockResolvedValue(undefined),
    onPromoteIssuedCertificate: vi.fn().mockResolvedValue(undefined),
    onLoadIssuedCertificate: vi.fn().mockResolvedValue({
      certificate_id: "cert-successor-1",
      row_version: 11,
      certificate_number: "GMP-DRAFT",
      issue_date: null,
      expiry_date: null,
      scopes: [],
    } as unknown as GxpCertificateDetail),
    onEditIssuedCertificate: vi.fn().mockResolvedValue(undefined),
    onLoadIssuedBusinessEligibility: vi.fn().mockResolvedValue({
      detail: {
        business_eligibility_certificate_id: "dkkd-successor-1",
        row_version: 13,
        certificate_number: "DDKD-DRAFT",
        issued_on: "2026-10-01",
        expires_on: "2029-10-01",
        professional_responsible_person_name: "Responsible Person",
        notes: "Draft notes",
        linked_gxp_certificates: [{
          certificate_id: "basis-cert-1",
          certificate_type: "GMP",
          line_code: "A",
          certificate_number: "GMP-001",
          issue_date: "2026-09-01",
          link_role: "source_certificate",
        }],
      } as unknown as BusinessEligibilityDetail,
      basisCertificates: [{
        certificate_id: "basis-cert-1",
        certificate_type: "GMP",
        line_code: "A",
        certificate_number: "GMP-001",
        issue_date: "2026-09-01",
        latest_flag: true,
      } as unknown as GxpCertificateListItem],
    }),
    onEditIssuedBusinessEligibility: vi.fn().mockResolvedValue(undefined),
  };
}

describe("ChangeRequestMutationWorkspace backend-owned writes", () => {
  it("uses readiness expected_version and sends only changed header fields, with explicit null for a cleared value", async () => {
    const handlers = buildHandlers();
    render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={buildWorkspace()} />);

    fireEvent.click(screen.getByRole("button", { name: "Sửa đề nghị" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Phạm vi thay đổi" }), { target: { value: "Đổi kho mới" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Mô tả thay đổi" }), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu đề nghị" }));

    await waitFor(() => expect(handlers.onUpdateHeader).toHaveBeenCalledTimes(1));
    expect(handlers.onUpdateHeader).toHaveBeenCalledWith({
      expected_version: 7,
      scope_label: "Đổi kho mới",
      description: null,
    });
  });

  it("issues a certificate successor with the backend readiness token and affected-link identity", async () => {
    const handlers = buildHandlers();
    render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={buildWorkspace()} />);

    fireEvent.click(screen.getByRole("button", { name: "Tạo GCN điều chỉnh" }));

    await waitFor(() => expect(handlers.onIssueCertificateSuccessor).toHaveBeenCalledTimes(1));
    expect(handlers.onIssueCertificateSuccessor).toHaveBeenCalledWith({
      expected_version: 7,
      source_affected_artifact_id: "affected-cert-1",
    });
  });

  it("issues a DDKD successor with the backend readiness token and affected-link identity", async () => {
    const handlers = buildHandlers();
    render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={buildWorkspace()} />);

    fireEvent.click(screen.getByRole("button", { name: "Tạo GCN ĐĐK điều chỉnh" }));

    await waitFor(() => expect(handlers.onIssueBusinessEligibilitySuccessor).toHaveBeenCalledTimes(1));
    expect(handlers.onIssueBusinessEligibilitySuccessor).toHaveBeenCalledWith({
      expected_version: 7,
      source_affected_artifact_id: "affected-dkkd-1",
    });
  });

  it("loads and edits an issued GxP successor with the target-owned readiness token", async () => {
    const handlers = buildHandlers();
    render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={buildWorkspace()} />);

    fireEvent.click(screen.getByRole("button", { name: "Cập nhật chứng nhận" }));

    await waitFor(() => expect(handlers.onLoadIssuedCertificate).toHaveBeenCalledTimes(1));
    expect(handlers.onLoadIssuedCertificate).toHaveBeenCalledWith("cert-successor-1");
    expect(await screen.findByRole("dialog", { name: "Sửa giấy chứng nhận GxP" })).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "Số GCN" }), {
      target: { value: "GMP-ADJUSTED" },
    });
    fireEvent.change(screen.getByLabelText("Ngày cấp"), {
      target: { value: "2026-10-05" },
    });
    fireEvent.change(screen.getByLabelText("Ngày hết hạn"), {
      target: { value: "2029-10-05" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() => expect(handlers.onEditIssuedCertificate).toHaveBeenCalledTimes(1));
    expect(handlers.onEditIssuedCertificate).toHaveBeenCalledWith(
      "cert-successor-1",
      {
        expected_version: 11,
        certificate_number: "GMP-ADJUSTED",
        issue_date: "2026-10-05",
        expiry_date: "2029-10-05",
        scopes: [],
        reason: null,
      },
    );
  });

  it("keeps issued GxP edit disabled when backend readiness blocks it", () => {
    const handlers = buildHandlers();
    const workspace = buildWorkspace({
      action_readiness: buildWorkspace().action_readiness.map((item) =>
        item.action_key === "edit_issued_certificate:issued-cert-1"
          ? { ...item, available: false, reason_code: "missing_permission" }
          : item,
      ),
    });

    render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={workspace} />);

    expect(screen.getByRole("button", { name: "Cập nhật chứng nhận" })).toBeDisabled();
    expect(handlers.onLoadIssuedCertificate).not.toHaveBeenCalled();
    expect(handlers.onEditIssuedCertificate).not.toHaveBeenCalled();
  });

  it("loads and edits an issued DDKD successor with the target-owned readiness token", async () => {
    const handlers = buildHandlers();
    render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={buildWorkspace()} />);

    fireEvent.click(screen.getByRole("button", { name: "Cập nhật GCN đủ điều kiện" }));

    await waitFor(() => expect(handlers.onLoadIssuedBusinessEligibility).toHaveBeenCalledTimes(1));
    expect(handlers.onLoadIssuedBusinessEligibility).toHaveBeenCalledWith("dkkd-successor-1");
    const dialog = await screen.findByRole("dialog", { name: "Cập nhật GCN đủ điều kiện" });
    fireEvent.change(within(dialog).getByRole("combobox", { name: /Vai trò căn cứ GMP A · GMP-001/ }), {
      target: { value: "replacement_certificate" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() => expect(handlers.onEditIssuedBusinessEligibility).toHaveBeenCalledTimes(1));
    expect(handlers.onEditIssuedBusinessEligibility).toHaveBeenCalledWith(
      "dkkd-successor-1",
      {
        expected_version: 13,
        certificate_number: "DDKD-DRAFT",
        issued_on: "2026-10-01",
        expires_on: "2029-10-01",
        professional_responsible_person_name: "Responsible Person",
        notes: "Draft notes",
        linked_certificates: [{
          certificate_id: "basis-cert-1",
          link_role: "replacement_certificate",
        }],
        reason: null,
      },
    );
  });

  it("keeps issued DDKD edit disabled when backend readiness blocks it", () => {
    const handlers = buildHandlers();
    const workspace = buildWorkspace({
      action_readiness: buildWorkspace().action_readiness.map((item) =>
        item.action_key === "edit_issued_business_eligibility:issued-dkkd-1"
          ? { ...item, available: false, reason_code: "missing_permission" }
          : item,
      ),
    });

    render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={workspace} />);

    expect(screen.getByRole("button", { name: "Cập nhật GCN đủ điều kiện" })).toBeDisabled();
    expect(handlers.onLoadIssuedBusinessEligibility).not.toHaveBeenCalled();
    expect(handlers.onEditIssuedBusinessEligibility).not.toHaveBeenCalled();
  });

  it("promotes issued successors with target-owned readiness tokens and target identities", async () => {
    const handlers = buildHandlers();
    render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={buildWorkspace()} />);

    fireEvent.click(screen.getByRole("button", { name: "Đặt làm chứng nhận hiện hành" }));
    await waitFor(() => expect(handlers.onPromoteIssuedCertificate).toHaveBeenCalledTimes(1));
    expect(handlers.onPromoteIssuedCertificate).toHaveBeenCalledWith(
      "cert-successor-1",
      11,
    );

    fireEvent.click(screen.getByRole("button", { name: "Đặt làm GCN đủ điều kiện hiện hành" }));
    await waitFor(() => expect(handlers.onPromoteIssuedBusinessEligibility).toHaveBeenCalledTimes(1));
    expect(handlers.onPromoteIssuedBusinessEligibility).toHaveBeenCalledWith(
      "dkkd-successor-1",
      13,
    );
  });

  it("keeps issued-successor promotion disabled when backend readiness blocks it", () => {
    const handlers = buildHandlers();
    const workspace = buildWorkspace({
      action_readiness: buildWorkspace().action_readiness.map((item) =>
        item.action_key === "promote_issued_certificate:issued-cert-1"
          ? { ...item, available: false, reason_code: "certificate_data_incomplete" }
          : item,
      ),
    });

    render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={workspace} />);

    expect(screen.getByRole("button", { name: "Đặt làm chứng nhận hiện hành" })).toBeDisabled();
    expect(handlers.onPromoteIssuedCertificate).not.toHaveBeenCalled();
  });

  it("keeps DDKD successor controls disabled when backend readiness blocks the action", () => {
    const handlers = buildHandlers();
    const workspace = buildWorkspace({
      action_readiness: buildWorkspace().action_readiness.map((item) =>
        item.action_key === "issue_business_eligibility_successor:affected-dkkd-1"
          ? { ...item, available: false, reason_code: "missing_permission" }
          : item,
      ),
    });

    render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={workspace} />);

    expect(screen.getByRole("button", { name: "Tạo GCN ĐĐK điều chỉnh" })).toBeDisabled();
    expect(handlers.onIssueBusinessEligibilitySuccessor).not.toHaveBeenCalled();
  });

  it("keeps certificate successor controls disabled when backend readiness blocks the action", () => {
    const handlers = buildHandlers();
    const workspace = buildWorkspace({
      action_readiness: buildWorkspace().action_readiness.map((item) =>
        item.action_key === "issue_certificate_successor:affected-cert-1"
          ? { ...item, available: false, reason_code: "missing_permission" }
          : item,
      ),
    });

    render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={workspace} />);

    expect(screen.getByRole("button", { name: "Tạo GCN điều chỉnh" })).toBeDisabled();
    expect(handlers.onIssueCertificateSuccessor).not.toHaveBeenCalled();
  });

  it("keeps edit controls disabled when backend readiness blocks the action", () => {
    const handlers = buildHandlers();
    const workspace = buildWorkspace({
      action_readiness: buildWorkspace().action_readiness.map((item) =>
        item.action_key === "edit_change_request"
          ? { ...item, available: false, reason_code: "missing_permission" }
          : item,
      ),
    });

    render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={workspace} />);

    expect(screen.getByRole("button", { name: "Sửa đề nghị" })).toBeDisabled();
    expect(screen.getByText("Không thể sửa: missing_permission.")).toBeInTheDocument();
  });

  it("creates and updates details with the aggregate readiness token instead of a child-local version", async () => {
    const handlers = buildHandlers();
    const { rerender } = render(<ChangeRequestMutationWorkspace activeTab="Chi tiết" handlers={handlers} workspace={buildWorkspace()} />);

    fireEvent.click(screen.getByRole("button", { name: "Thêm chi tiết" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Phân loại thay đổi" }), { target: { value: "Thiết bị" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Thông tin mới" }), { target: { value: "Máy mới" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu chi tiết mới" }));

    await waitFor(() => expect(handlers.onCreateDetail).toHaveBeenCalledTimes(1));
    expect(handlers.onCreateDetail).toHaveBeenCalledWith(expect.objectContaining({
      expected_version: 7,
      classification_label: "Thiết bị",
      new_value: "Máy mới",
    }));

    rerender(<ChangeRequestMutationWorkspace activeTab="Chi tiết" handlers={handlers} workspace={buildWorkspace({ row_version: 8, action_readiness: buildWorkspace().action_readiness.map((item) => ({ ...item, expected_version: 8 })) })} />);
    fireEvent.click(screen.getByRole("button", { name: "Sửa" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Thông tin mới" }), { target: { value: "C" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu chi tiết" }));

    await waitFor(() => expect(handlers.onUpdateDetail).toHaveBeenCalledTimes(1));
    expect(handlers.onUpdateDetail).toHaveBeenCalledWith("detail-1", {
      expected_version: 8,
      new_value: "C",
    });
  });

  it("rejects an invalid classification id instead of silently clearing it", async () => {
    const handlers = buildHandlers();
    render(<ChangeRequestMutationWorkspace activeTab="Chi tiết" handlers={handlers} workspace={buildWorkspace()} />);

    fireEvent.click(screen.getByRole("button", { name: "Thêm chi tiết" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Mã phân loại thay đổi" }), { target: { value: "not-a-number" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Phân loại thay đổi" }), { target: { value: "Thiết bị" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu chi tiết mới" }));

    expect(handlers.onCreateDetail).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Mã phân loại phải là số nguyên hợp lệ.");
  });

  it("uses backend target_state directly for transitions and never derives state from action_key", async () => {
    const handlers = buildHandlers();
    render(<ChangeRequestMutationWorkspace activeTab="Xử lý" handlers={handlers} workspace={buildWorkspace()} />);

    fireEvent.click(screen.getByRole("button", { name: "Chấp nhận" }));

    await waitFor(() => expect(handlers.onTransition).toHaveBeenCalledTimes(1));
    expect(handlers.onTransition).toHaveBeenCalledWith({
      expected_version: 7,
      target_state: "accepted",
    });
  });

  it("resets an open editor when authoritative row_version changes", () => {
    const handlers = buildHandlers();
    const { rerender } = render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={buildWorkspace()} />);
    fireEvent.click(screen.getByRole("button", { name: "Sửa đề nghị" }));
    expect(screen.getByRole("textbox", { name: "Phạm vi thay đổi" })).toBeInTheDocument();

    rerender(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={buildWorkspace({ row_version: 8, scope_label: "Authoritative" })} />);

    expect(screen.queryByRole("textbox", { name: "Phạm vi thay đổi" })).not.toBeInTheDocument();
    expect(screen.getByText("Authoritative")).toBeInTheDocument();
  });
});
