import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";
import type { BusinessEligibilityDetail, CaseWorkspace, FacilityHistoryItem } from "../../types";
import { EventWorkspace } from "./EventWorkspace";

const certificate = (id: string, notes = id): BusinessEligibilityDetail => ({
  business_eligibility_certificate_id: id, row_version: 7, site_id: "site-uuid", company_id: "company-uuid",
  latest_flag: false, certificate_number: "DDK-SAME", issued_on: "2026-09-01", expires_on: null,
  notes, decision_reference: "QD-01", issuance_sequence_text: "2", issuance_history_text: "Server history text",
  company_name: "Company", company_legal_address: "Headquarters\nSecond line", facility_name: "Facility", address: null,
  professional_responsible_person_name: "Responsible person", quality_assurance_person_name: "QA person",
  professional_qualification_text: "Qualification", professional_license_number: "License",
  professional_license_issued_on: null, professional_license_issuer: null,
  responsible_license_issued_on: null, responsible_license_issuer: null, business_activity_text: "Activity\nSecond activity",
  current_status_text: "Server status", handled_by_name: "Handler", application_dossier_reference: "Dossier",
  replaces_certificate_number: "Previous certificate", replaced_by_certificate_number: "Successor certificate",
  linked_gxp_certificates: ["basis-uuid-A", "basis-uuid-B"].map(certificate_id => ({
    certificate_id, certificate_type: "GMP", line_code: "A", certificate_number: "GXP-SAME",
    issue_date: "2026-08-01", link_role: "source_certificate",
  })),
  action_readiness: [{ action_key: "edit_latest_version", label: "Site-only edit", available: true,
    reason_code: null, required_permissions: ["certificate.edit"], expected_version: 7 }],
});
const callbacks = {
  onTabChange: vi.fn(), onCaseApplicationSave: vi.fn(), onCaseAssessmentSave: vi.fn(), onInspectionPlanSave: vi.fn(),
  onInspectionOutcomeSave: vi.fn(), onInspectionPeriodSegmentsSave: vi.fn(), onCreateApprovalSubmission: vi.fn(),
  onCompleteApprovalSubmission: vi.fn(), onTransitionCase: vi.fn(), onInspectionTeamSave: vi.fn(),
  onLoadInspectionTeamIdentityOptions: vi.fn(), onEvaluationScopeSave: vi.fn(), onOpenDocument: vi.fn(),
  onLoadDocumentDetail: vi.fn(), onCreateDocument: vi.fn(), onIssueCertificate: vi.fn(),
  onSelectedRemediationCycleChange: vi.fn(), onCreateCapaCycle: vi.fn(), onUpdateCapaCycle: vi.fn(),
  onSubmitCapaCycle: vi.fn(), onAssessCapaCycle: vi.fn(), onResolveInspectionFolder: vi.fn(),
};
function props(items = [certificate("eligibility-uuid-A"), certificate("eligibility-uuid-B")]): ComponentProps<typeof EventWorkspace> {
  return {
    ...callbacks, selectedHistory: { id: "case-uuid", source_type: "case" } as FacilityHistoryItem,
    caseWorkspace: { case_summary: { id: "case-uuid", site_id: "site-uuid", production_line_id: "line-uuid" },
      linked_business_eligibility_certificates: items, contextual_document_actions: [] } as unknown as CaseWorkspace,
    caseWorkspaceLoading: false, caseWorkspaceError: null, changeRequestWorkspace: null,
    changeRequestWorkspaceLoading: false, changeRequestWorkspaceError: null,
    changeRequestMutations: {} as ComponentProps<typeof EventWorkspace>["changeRequestMutations"],
    activeTab: "Chứng nhận ĐĐK", selectedRemediationCycleId: null,
  };
}
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("Case ĐĐK presentation and read-only ownership", () => {
  it("places the compact legacy list above canonical details with the Case caption and column order", () => {
    const { container } = render(<EventWorkspace {...props()} />);
    const owner = container.querySelector(".case-business-eligibility-workspace");
    expect(owner).not.toBeNull();
    expect(owner?.children[0]).toHaveClass("certificate-list-panel");
    expect(owner?.children[1]).toHaveClass("certificate-detail-panel");
    const list = screen.getByRole("table", { name: "Giấy ĐĐK đã cấp căn cứ GCN GPs này" });
    expect(within(list).getAllByRole("columnheader").map(node => node.textContent)).toEqual(["Số GCN", "Ngày cấp", "Lần"]);
    expect(Array.from(container.querySelectorAll(".legacy-certificate-heading .detail-label"), node => node.textContent))
      .toEqual(["Số GCN", "Ngày cấp", "QĐ cấp", "Cấp lần"]);
  });

  it("separates keyboard focus from canonical UUID selection even with equal numbers and latest flags", () => {
    render(<EventWorkspace {...props()} />);
    const rows = screen.getAllByRole("row").slice(1);
    act(() => rows[0].focus());
    fireEvent.keyDown(rows[0], { key: "ArrowDown" });
    expect(rows[1]).toHaveFocus();
    expect(rows[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("eligibility-uuid-A")).toBeInTheDocument();
    fireEvent.keyDown(rows[1], { key: "Enter" });
    expect(rows[1]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("eligibility-uuid-B")).toBeInTheDocument();
    fireEvent.keyDown(rows[1], { key: "Home" });
    expect(rows[0]).toHaveFocus();
    fireEvent.keyDown(rows[0], { key: " " });
    expect(screen.getByText("eligibility-uuid-A")).toBeInTheDocument();
  });

  it("preserves selected ID across refresh/reorder, uses the new snapshot, and falls back when that ID disappears", () => {
    const { rerender } = render(<EventWorkspace {...props()} />);
    fireEvent.click(screen.getAllByRole("row")[2]);
    rerender(<EventWorkspace {...props([certificate("eligibility-uuid-B", "Refreshed B"), certificate("eligibility-uuid-A")])} />);
    expect(screen.getByText("Refreshed B")).toBeInTheDocument();
    expect(screen.getAllByRole("row")[1]).toHaveAttribute("aria-selected", "true");
    rerender(<EventWorkspace {...props([certificate("eligibility-uuid-C")])} />);
    expect(screen.getByText("eligibility-uuid-C")).toBeInTheDocument();
    expect(screen.queryByText("Refreshed B")).not.toBeInTheDocument();
    expect(screen.getAllByRole("row")[1]).toHaveAttribute("aria-selected", "true");
    rerender(<EventWorkspace {...props([])} />);
    expect(screen.getByText("Chưa có chứng nhận ĐĐK liên kết")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("retains all basis UUID entries and snapshot fields without adding Case mutations, version history or document actions", () => {
    const { container } = render(<EventWorkspace {...props()} />);
    expect(container.querySelectorAll(".certificate-basis-section li")).toHaveLength(2);
    for (const value of ["Previous certificate", "Successor certificate", "Dossier", "Server history text", "Server status", "License", "QA person"])
      expect(screen.getByText(value)).toBeInTheDocument();
    expect(screen.getByText("Headquarters Second line")).toHaveClass("multiline-value");
    expect(screen.getAllByText("Chưa có").length).toBeGreaterThan(0);
    const owner = container.querySelector(".event-linked-certificate-workspace")!;
    expect(owner.querySelectorAll("button, input, textarea, .document-workspace, .editable-detail-value")).toHaveLength(0);
    for (const key of ["F2", "Enter", "Escape", "F6"]) fireEvent.keyDown(screen.getAllByRole("row")[1], { key });
    for (const callback of Object.values(callbacks)) expect(callback).not.toHaveBeenCalled();
  });

  it.each([
    { caseWorkspaceLoading: true, title: "Đang tải workspace hồ sơ" },
    { caseWorkspaceError: "403 fixture", title: "Không tải được workspace hồ sơ" },
    { selectedHistory: { id: "other-case-uuid", source_type: "case" } as FacilityHistoryItem, title: "Chưa có workspace hồ sơ" },
  ])("does not expose stale ĐĐK details while $title", overrides => {
    const { rerender } = render(<EventWorkspace {...props()} />);
    expect(screen.getByText("eligibility-uuid-A")).toBeInTheDocument();
    rerender(<EventWorkspace {...props()} {...overrides} />);
    expect(screen.getByText(overrides.title)).toBeInTheDocument();
    expect(screen.queryByText("eligibility-uuid-A")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
