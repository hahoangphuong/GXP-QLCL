import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CaseWorkspace } from "../../types";
import { CaseInspectionWorkspace } from "./CaseInspectionWorkspace";

function workspace(overrides: Partial<CaseWorkspace["inspection"]> = {}): CaseWorkspace {
  return {
    case_summary: { id: "case-1", row_version: 1, legacy_inspection_id: null, legacy_inspection_code: null, site_id: "site-1", legacy_site_id: null, facility_name: "Cơ sở A", company_name: "Công ty A", gxp_type: "GMP", scope_code: null, applicable_standard: "WHO-GMP", inspection_type: "Tái", state: "draft", opened_year: null },
    application: { row_version: null, submitted_on: null, dossier_code: null, dossier_reference: null, applicant_name: null, assigned_specialist: null, assigned_specialist_source: null },
    inspection: {
      plan_row_version: null, plan_decision_reference: null, plan_decision_date: null, decision_document_hint: null, plan_start_on: null, plan_end_on: null, planning_sheet_name: null,
      outcome_row_version: null, inspected_on: null, inspected_to_on: null, executed_on: null, bbkt_reference: null, outcome_result: null,
      inspection_period_edit_readiness: { action_key: "edit_inspection_period", label: "Sửa các đợt kiểm tra", available: true, reason_code: null, required_permissions: ["inspection.edit"], expected_version: 6, mode: "replace" },
      team_display_text: "Legacy: do not parse this text",
      team: { team_id: "team-1", row_version: 7, display_text: "Legacy: do not parse this text", round_trip_safe: true, blocked_reason_code: null, members: [
        { id: "member-1", inspector_profile_id: "profile-1", person_id: null, display_name: "Thanh tra A", role_code: "LEADER", role_label: "Trưởng đoàn", sort_order: 1, identity_kind: "INSPECTOR_PROFILE", identity_status: "resolved" },
        { id: "member-2", inspector_profile_id: null, person_id: "person-2", display_name: "Thành viên B", role_code: "SECRETARY", role_label: "Thư ký", sort_order: 2, identity_kind: "LEGACY_PERSON", identity_status: "resolved" },
      ] },
      team_edit_readiness: { action_key: "edit_inspection_team", label: "Sửa đoàn kiểm tra", available: true, reason_code: null, required_permissions: ["inspection.edit"], expected_version: 7, mode: "replace" },
      ...overrides,
    },
    remediation: { cycles: [] }, processing: { row_version: null, assessed_on: null, assessor_name: null, assessment_result: null, notes: null, events: [] },
    evaluation_scope: null, linked_gxp_certificates: [], linked_business_eligibility_certificates: [], documents: { items: [] }, contextual_document_actions: [], certificate_issue_readiness: null,
  } as unknown as CaseWorkspace;
}

describe("CaseInspectionWorkspace inspection team editor", () => {
  it("does not enable edit without backend readiness or construct members from legacy text", () => {
    render(<CaseInspectionWorkspace caseWorkspace={workspace({ team: null, team_edit_readiness: { action_key: "edit_inspection_team", label: "Sửa đoàn kiểm tra", available: false, reason_code: "structured_read_unavailable", required_permissions: ["inspection.edit"], expected_version: null, mode: null } })} onInspectionOutcomeSave={vi.fn()} onInspectionPeriodSegmentsSave={vi.fn()} onInspectionPlanSave={vi.fn()} onInspectionTeamSave={vi.fn()} onLoadInspectionTeamIdentityOptions={vi.fn()} onCreateApprovalSubmission={vi.fn()} onCompleteApprovalSubmission={vi.fn()} onTransitionCase={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" })).toBeDisabled();
    expect(screen.queryByLabelText("Định danh thành viên 1")).not.toBeInTheDocument();
  });

  it("round-trips structured members, preserves identity kinds, and never submits display text", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const loadOptions = vi.fn().mockResolvedValue([
      { identity_kind: "inspector_profile", inspector_profile_id: "profile-1", person_id: "person-1", display_name: "Thanh tra A", is_active: true },
      { identity_kind: "person", inspector_profile_id: null, person_id: "person-2", display_name: "Thành viên B", is_active: null },
      { identity_kind: "person", inspector_profile_id: null, person_id: "person-3", display_name: "Thành viên C", is_active: null },
    ]);
    render(<CaseInspectionWorkspace caseWorkspace={workspace()} onInspectionOutcomeSave={vi.fn()} onInspectionPeriodSegmentsSave={vi.fn()} onInspectionPlanSave={vi.fn()} onInspectionTeamSave={onSave} onLoadInspectionTeamIdentityOptions={loadOptions} onCreateApprovalSubmission={vi.fn()} onCompleteApprovalSubmission={vi.fn()} onTransitionCase={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" }));
    await screen.findByLabelText("Định danh thành viên 1");
    fireEvent.click(screen.getByRole("button", { name: "Lưu đoàn kiểm tra" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith({
      expected_version: 7,
      members: [
        { inspector_profile_id: "profile-1", person_id: null, participant_catalog_id: undefined, identity_kind: "INSPECTOR_PROFILE", role_code: "LEADER", sort_order: 1 },
        { inspector_profile_id: null, person_id: "person-2", participant_catalog_id: undefined, identity_kind: null, role_code: "SECRETARY", sort_order: 2 },
      ],
    });
    expect(JSON.stringify(onSave.mock.calls[0][0])).not.toContain("Legacy: do not parse this text");
  });

  it("surfaces a stale conflict and discards the open draft", async () => {
    const conflict = Object.assign(new Error("Stale inspection_team update."), { status: 409 });
    const onSave = vi.fn().mockRejectedValue(conflict);
    render(<CaseInspectionWorkspace caseWorkspace={workspace()} onInspectionOutcomeSave={vi.fn()} onInspectionPeriodSegmentsSave={vi.fn()} onInspectionPlanSave={vi.fn()} onInspectionTeamSave={onSave} onLoadInspectionTeamIdentityOptions={vi.fn().mockResolvedValue([])} onCreateApprovalSubmission={vi.fn()} onCompleteApprovalSubmission={vi.fn()} onTransitionCase={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" }));
    await screen.findByLabelText("Định danh thành viên 1");
    fireEvent.click(screen.getByRole("button", { name: "Lưu đoàn kiểm tra" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("đã bị thay đổi");
    expect(screen.queryByLabelText("Định danh thành viên 1")).not.toBeInTheDocument();
  });
});

describe("CaseInspectionWorkspace canonical period editor", () => {
  it("writes id-free contiguous segments after reorder and removal", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<CaseInspectionWorkspace caseWorkspace={workspace({
      outcome_row_version: 6,
      inspection_period_state: "KNOWN",
      inspection_period_segments: [
        { id: "source-3", ordinal: 3, started_on: "2026-10-10", ended_on: "2026-10-11" },
        { id: "source-7", ordinal: 7, started_on: "2026-10-20", ended_on: "2026-10-21" },
      ],
    })} onInspectionOutcomeSave={vi.fn()} onInspectionPeriodSegmentsSave={onSave} onInspectionPlanSave={vi.fn()} onInspectionTeamSave={vi.fn()} onLoadInspectionTeamIdentityOptions={vi.fn()} onCreateApprovalSubmission={vi.fn()} onCompleteApprovalSubmission={vi.fn()} onTransitionCase={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Sửa các đợt kiểm tra" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Lên" })[1]);
    fireEvent.click(screen.getAllByRole("button", { name: "Xóa" })[1]);
    fireEvent.click(screen.getByRole("button", { name: "Lưu các đợt kiểm tra" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith({
      expected_version: 6,
      segments: [{ ordinal: 1, started_on: "2026-10-20", ended_on: "2026-10-21" }],
    }));
  });

  it.each(["MISSING", "PENDING_INPUT", "NON_DATE_EXPRESSION", "UNRESOLVED"])("fails closed for source-owned %s periods", (state) => {
    render(<CaseInspectionWorkspace caseWorkspace={workspace({ outcome_row_version: 6, inspection_period_state: state, inspection_period_edit_readiness: { action_key: "edit_inspection_period", label: "Sửa các đợt kiểm tra", available: false, reason_code: "source_owned_period_state", required_permissions: ["inspection.edit"], expected_version: 6, mode: null } })} onInspectionOutcomeSave={vi.fn()} onInspectionPeriodSegmentsSave={vi.fn()} onInspectionPlanSave={vi.fn()} onInspectionTeamSave={vi.fn()} onLoadInspectionTeamIdentityOptions={vi.fn()} onCreateApprovalSubmission={vi.fn()} onCompleteApprovalSubmission={vi.fn()} onTransitionCase={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Sửa các đợt kiểm tra" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Sửa Từ ngày kiểm tra" })).not.toBeInTheDocument();
  });

  it("fails closed when inspection period state is absent", () => {
    render(<CaseInspectionWorkspace caseWorkspace={workspace({ outcome_row_version: 6, inspection_period_state: null, inspection_period_edit_readiness: { action_key: "edit_inspection_period", label: "Sửa các đợt kiểm tra", available: false, reason_code: "legacy_period_state_unclassified", required_permissions: ["inspection.edit"], expected_version: 6, mode: null } })} onInspectionOutcomeSave={vi.fn()} onInspectionPeriodSegmentsSave={vi.fn()} onInspectionPlanSave={vi.fn()} onInspectionTeamSave={vi.fn()} onLoadInspectionTeamIdentityOptions={vi.fn()} onCreateApprovalSubmission={vi.fn()} onCompleteApprovalSubmission={vi.fn()} onTransitionCase={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Sửa các đợt kiểm tra" })).toBeDisabled();
  });
});
