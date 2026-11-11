import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CaseWorkspace } from "../../types";
import { CaseDraftSession } from "./CaseDraftSession";
import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";
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


it("retains structured periods, team and final evaluation across tab remount without a second identity lookup", async () => {
  const loadOptions = vi.fn().mockResolvedValue([{ identity_kind: "inspector_profile", inspector_profile_id: "profile-1", person_id: null, display_name: "Thanh tra A", is_active: true }]);
  const onPeriod = vi.fn().mockResolvedValue(undefined), onFinalize = vi.fn().mockResolvedValue(undefined);
  const editor = (show: boolean, version = 6) => <CaseDraftSession identity="case-A">{show ? <CaseInspectionWorkspace caseWorkspace={workspace({ outcome_row_version: version, final_evaluation: null, final_evaluation_readiness: { action_key: "finalize_inspection_outcome", label: "Chốt đánh giá cuối cùng", available: true, expected_version: version, reason_code: null, required_permissions: [] }, inspection_period_segments: [{ id: "period-1", ordinal: 1, started_on: "2026-10-01", ended_on: "2026-10-02" }] })} onInspectionOutcomeSave={vi.fn()} onInspectionPeriodSegmentsSave={onPeriod} onInspectionPlanSave={vi.fn()} onInspectionTeamSave={vi.fn()} onLoadInspectionTeamIdentityOptions={loadOptions} onCreateApprovalSubmission={vi.fn()} onCompleteApprovalSubmission={vi.fn()} onTransitionCase={vi.fn()} onFinalizeInspectionOutcome={onFinalize} /> : null}</CaseDraftSession>;
  const view = render(editor(true));
  fireEvent.click(screen.getByRole("button", { name: "Sửa các đợt kiểm tra" }));
  fireEvent.change(screen.getByLabelText("Từ ngày lần 1"), { target: { value: "2026-09-30" } });
  fireEvent.click(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" }));
  await screen.findByLabelText("Định danh thành viên 1");
  fireEvent.change(screen.getByLabelText("Đánh giá cuối cùng"), { target: { value: "Retained final" } });
  view.rerender(editor(false));view.rerender(editor(true, 9));
  expect(screen.getByLabelText("Từ ngày lần 1")).toHaveValue("2026-09-30");
  expect(screen.getByLabelText("Định danh thành viên 1")).toBeInTheDocument();
  expect(screen.getByLabelText("Đánh giá cuối cùng")).toHaveValue("Retained final");
  expect(loadOptions).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Lưu các đợt kiểm tra" }));
  await waitFor(() => expect(onPeriod).toHaveBeenCalledWith(expect.objectContaining({ expected_version: 6 })));
  fireEvent.click(screen.getByRole("button", { name: "Chốt đánh giá cuối cùng" }));
  await waitFor(() => expect(onFinalize).toHaveBeenCalledWith(expect.objectContaining({ expected_version: 6, final_evaluation: "Retained final" })));
});

describe("final evaluation reconciliation and operator draft", () => {
  function editor(onFinalize: ReturnType<typeof vi.fn>, show = true, identity = "case-A", canFinalize = true) {
    return <CaseDraftSession identity={identity}>{show ? <CaseInspectionWorkspace
      caseWorkspace={workspace({ outcome_row_version: 6, final_evaluation: null,
        final_evaluation_readiness: { action_key: "finalize_inspection_outcome", label: "Chốt đánh giá cuối cùng",
          available: canFinalize, expected_version: 6, reason_code: canFinalize ? null : "blocked", required_permissions: [] } })}
      onInspectionOutcomeSave={vi.fn()} onInspectionPeriodSegmentsSave={vi.fn()} onInspectionPlanSave={vi.fn()}
      onInspectionTeamSave={vi.fn()} onLoadInspectionTeamIdentityOptions={vi.fn()}
      onCreateApprovalSubmission={vi.fn()} onCompleteApprovalSubmission={vi.fn()}
      onTransitionCase={vi.fn()} onFinalizeInspectionOutcome={onFinalize}
    /> : null}</CaseDraftSession>;
  }

  it("holds the exact final assessment as copyable read-only after an unverified mutation, even after tab remount and readiness withdrawal", async () => {
    const onFinalize = vi.fn().mockRejectedValue(new CaseFieldMutationRecoveryError("Không đọc lại được kết quả chốt."));
    const view = render(editor(onFinalize));
    fireEvent.change(screen.getByLabelText("Đánh giá cuối cùng"), { target: { value: "Chấp nhận CAPA sau lần 2; đề nghị cấp giấy." } });
    fireEvent.click(screen.getByRole("button", { name: "Chốt đánh giá cuối cùng" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Không đọc lại được kết quả chốt.");
    const input = screen.getByLabelText("Đánh giá cuối cùng");
    expect(input).toHaveValue("Chấp nhận CAPA sau lần 2; đề nghị cấp giấy.");
    expect(input).toHaveAttribute("readonly");
    expect(screen.getByRole("status")).toHaveTextContent("Giữ nguyên đánh giá cuối cùng đã gửi");
    expect(screen.getByRole("button", { name: "Hủy nhập đánh giá" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Chốt đánh giá cuối cùng" })).toBeDisabled();
    fireEvent.change(input, { target: { value: "Attempted overwrite" } });
    fireEvent.click(screen.getByRole("button", { name: "Hủy nhập đánh giá" }));
    expect(input).toHaveValue("Chấp nhận CAPA sau lần 2; đề nghị cấp giấy.");
    expect(onFinalize).toHaveBeenCalledExactlyOnceWith({
      expected_version: 6, final_evaluation: "Chấp nhận CAPA sau lần 2; đề nghị cấp giấy.",
    });
    view.rerender(editor(onFinalize, false));
    view.rerender(editor(onFinalize, true, "case-A", false));
    const preserved = screen.getByLabelText("Đánh giá cuối cùng");
    expect(preserved).toHaveValue("Chấp nhận CAPA sau lần 2; đề nghị cấp giấy.");
    expect(preserved).toHaveAttribute("readonly");
    expect(preserved).toBeEnabled();
    expect(screen.getByRole("button", { name: "Hủy nhập đánh giá" })).toBeDisabled();
    expect(onFinalize).toHaveBeenCalledOnce();
  });

  it("allows correction or cancellation after a definitive 409 without retaining a recovery lock", async () => {
    const onFinalize = vi.fn().mockRejectedValue(Object.assign(new Error("Stale assessment version"), { status: 409 }));
    render(editor(onFinalize));
    fireEvent.change(screen.getByLabelText("Đánh giá cuối cùng"), { target: { value: "Old assessment" } });
    fireEvent.click(screen.getByRole("button", { name: "Chốt đánh giá cuối cùng" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("hồ sơ đã bị thay đổi");
    const input = screen.getByLabelText("Đánh giá cuối cùng");
    expect(input).not.toHaveAttribute("readonly");
    fireEvent.change(input, { target: { value: "Edited after rejection" } });
    expect(input).toHaveValue("Edited after rejection");
    fireEvent.click(screen.getByRole("button", { name: "Hủy nhập đánh giá" }));
    expect(input).toHaveValue("");
    expect(onFinalize).toHaveBeenCalledOnce();
  });
});

it("keeps keyboard focus on the same team slot when its canonical identity changes", async () => {
  const onSave = vi.fn();
  const loadOptions = vi.fn().mockResolvedValue([
    { identity_kind: "inspector_profile", inspector_profile_id: "profile-1", person_id: null, display_name: "Thanh tra A", is_active: true },
    { identity_kind: "person", inspector_profile_id: null, person_id: "person-2", display_name: "Thành viên B", is_active: null },
    { identity_kind: "person", inspector_profile_id: null, person_id: "person-3", display_name: "Thành viên C", is_active: null },
  ]);
  render(<CaseInspectionWorkspace caseWorkspace={workspace()} onInspectionOutcomeSave={vi.fn()} onInspectionPeriodSegmentsSave={vi.fn()} onInspectionPlanSave={vi.fn()} onInspectionTeamSave={onSave} onLoadInspectionTeamIdentityOptions={loadOptions} onCreateApprovalSubmission={vi.fn()} onCompleteApprovalSubmission={vi.fn()} onTransitionCase={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" }));
  const selector = await screen.findByLabelText("Định danh thành viên 1");
  selector.focus();
  fireEvent.change(selector, { target: { value: "person:person-3" } });
  expect(screen.getByLabelText("Định danh thành viên 1")).toBe(selector);
  expect(selector).toHaveFocus();
  expect(selector).toHaveValue("person:person-3");
  expect(screen.getByLabelText("Định danh thành viên 2")).toHaveValue("person:person-2");
  expect(onSave).not.toHaveBeenCalled();
  expect(loadOptions).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Lưu đoàn kiểm tra" }));
  await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ expected_version: 7, members: [
    expect.objectContaining({ person_id: "person-3", inspector_profile_id: null, role_code: "LEADER", sort_order: 1 }),
    expect.objectContaining({ person_id: "person-2", role_code: "SECRETARY", sort_order: 2 }),
  ] })));
});

it.each([false, true])("does not adopt late team identity lookup after access A → B → A (reject=%s)", async (rejectLookup) => {
  let resolve!: (value: []) => void;
  let reject!: (value: Error) => void;
  const pending = new Promise<[]>((yes, no) => { resolve = yes; reject = no; });
  const loadOptions = vi.fn().mockReturnValue(pending);
  const editor = (identity: string) => <CaseDraftSession identity={identity}><CaseInspectionWorkspace caseWorkspace={workspace()} onInspectionOutcomeSave={vi.fn()} onInspectionPeriodSegmentsSave={vi.fn()} onInspectionPlanSave={vi.fn()} onInspectionTeamSave={vi.fn()} onLoadInspectionTeamIdentityOptions={loadOptions} onCreateApprovalSubmission={vi.fn()} onCompleteApprovalSubmission={vi.fn()} onTransitionCase={vi.fn()} /></CaseDraftSession>;
  const view = render(editor("access-A"));
  fireEvent.click(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" }));
  expect(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" })).toBeDisabled();
  view.rerender(editor("access-B"));
  view.rerender(editor("access-A"));
  await act(async () => {
    if (rejectLookup) reject(Object.assign(new Error("Old account denied"), { status: 403 }));
    else resolve([]);
  });
  expect(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" })).toBeEnabled();
  expect(screen.queryByLabelText("Định danh thành viên 1")).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(loadOptions).toHaveBeenCalledOnce();
});

it("edits the canonical planning-sheet name through inspection.plan, pinned to the original plan version", async () => {
  const save = vi.fn().mockResolvedValue(undefined);
  const source = workspace({ plan_row_version: 6, planning_sheet_name: "Kế hoạch A" });
  render(<CaseDraftSession identity="case-1"><CaseInspectionWorkspace caseWorkspace={source}
    onInspectionPlanSave={save} onInspectionOutcomeSave={vi.fn()} onInspectionPeriodSegmentsSave={vi.fn()}
    onInspectionTeamSave={vi.fn()} onLoadInspectionTeamIdentityOptions={vi.fn()}
    onCreateApprovalSubmission={vi.fn()} onCompleteApprovalSubmission={vi.fn()} onTransitionCase={vi.fn()} /></CaseDraftSession>);
  fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Tên bảng kế hoạch" }));
  fireEvent.change(screen.getByLabelText("Tên bảng kế hoạch"), { target: { value: "  Kế hoạch kỳ 2  " } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu Tên bảng kế hoạch" }));
  await waitFor(() => expect(save).toHaveBeenCalledWith({ expected_version: 6, planning_sheet_name: "Kế hoạch kỳ 2" }));
});

describe("Inspection minutes canonical date/time prerequisites", () => {
  const renderMinutes = (inspection: Partial<CaseWorkspace["inspection"]> = {}, onSave = vi.fn().mockResolvedValue(undefined)) => {
    const props = {
      onInspectionOutcomeSave: onSave, onInspectionPeriodSegmentsSave: vi.fn(), onInspectionPlanSave: vi.fn(),
      onInspectionTeamSave: vi.fn(), onLoadInspectionTeamIdentityOptions: vi.fn(),
      onCreateApprovalSubmission: vi.fn(), onCompleteApprovalSubmission: vi.fn(), onTransitionCase: vi.fn(),
    };
    return { ...render(<CaseDraftSession identity="case-1"><CaseInspectionWorkspace
      caseWorkspace={workspace({ outcome_row_version: 6, ...inspection })} {...props}
    /></CaseDraftSession>), onSave };
  };

  it("does not send minutes time until the date is canonically saved", async () => {
    const { onSave } = renderMinutes();
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Giờ biên bản" }));
    fireEvent.change(screen.getByLabelText("Giờ biên bản/report"), { target: { value: "09:30" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Lưu ngày biên bản trước");
    expect(screen.getByRole("button", { name: "Lưu Giờ biên bản/report" })).toBeDisabled();
    fireEvent.keyDown(screen.getByLabelText("Giờ biên bản/report"), { key: "Enter" });
    expect(onSave).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Hủy sửa Giờ biên bản/report" }));
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Ngày biên bản" }));
    fireEvent.change(screen.getByLabelText("Ngày biên bản/report"), { target: { value: "2026-10-12" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Ngày biên bản/report" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledExactlyOnceWith({ expected_version: 6, minutes_recorded_on: "2026-10-12" }));
  });

  it("does not silently erase an existing time when clearing the minutes date", () => {
    const { onSave } = renderMinutes({ minutes_recorded_on: "2026-10-10", minutes_recorded_time: "15:30" });
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Ngày biên bản" }));
    fireEvent.change(screen.getByLabelText("Ngày biên bản/report"), { target: { value: "" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Xóa giờ biên bản và lưu trước");
    expect(screen.getByRole("button", { name: "Lưu Ngày biên bản/report" })).toBeDisabled();
    expect(onSave).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Hủy sửa Ngày biên bản/report" }));
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Giờ biên bản" }));
    fireEvent.change(screen.getByLabelText("Giờ biên bản/report"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Giờ biên bản/report" }));
    expect(onSave).toHaveBeenCalledWith({ expected_version: 6, minutes_recorded_time: null });
  });

  it("can save time after a canonical date exists without resubmitting the date", async () => {
    const { onSave } = renderMinutes({ minutes_recorded_on: "2026-10-12" });
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Giờ biên bản" }));
    fireEvent.change(screen.getByLabelText("Giờ biên bản/report"), { target: { value: "09:30" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Lưu Giờ biên bản/report" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledExactlyOnceWith({ expected_version: 6, minutes_recorded_time: "09:30" }));
  });

  it("keeps the edit-start version and visible draft on a minutes time conflict", async () => {
    const onSave = vi.fn().mockRejectedValue(Object.assign(new Error("conflict"), { status: 409 }));
    const initial = workspace({ outcome_row_version: 6, minutes_recorded_on: "2026-10-12" });
    const props = { onInspectionOutcomeSave: onSave, onInspectionPeriodSegmentsSave: vi.fn(), onInspectionPlanSave: vi.fn(), onInspectionTeamSave: vi.fn(), onLoadInspectionTeamIdentityOptions: vi.fn(), onCreateApprovalSubmission: vi.fn(), onCompleteApprovalSubmission: vi.fn(), onTransitionCase: vi.fn() };
    const view = render(<CaseDraftSession identity="case-1"><CaseInspectionWorkspace caseWorkspace={initial} {...props}/></CaseDraftSession>);
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Giờ biên bản" }));
    fireEvent.change(screen.getByLabelText("Giờ biên bản/report"), { target: { value: "14:45" } });
    view.rerender(<CaseDraftSession identity="case-1"><CaseInspectionWorkspace caseWorkspace={workspace({ outcome_row_version: 7, minutes_recorded_on: "2026-10-12", minutes_recorded_time: "10:00" })} {...props}/></CaseDraftSession>);
    fireEvent.click(screen.getByRole("button", { name: "Lưu Giờ biên bản/report" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledExactlyOnceWith({ expected_version: 6, minutes_recorded_time: "14:45" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByLabelText("Giờ biên bản/report")).toHaveValue("14:45");
  });
});


describe("final evaluation submitted command ownership across Case A → B → A", () => {
  const ready = { action_key: "finalize_inspection_outcome", label: "Chốt đánh giá cuối cùng",
    available: true, expected_version: 6, reason_code: null, required_permissions: [] };
  function editor(id: string, onFinalize: ReturnType<typeof vi.fn>, available = true) {
    const w = workspace({
      outcome_row_version: available ? 6 : 9, final_evaluation: null,
      final_evaluation_readiness: { ...ready, available, expected_version: available ? 6 : 9, reason_code: available ? null : "blocked" },
    });
    return <CaseDraftSession identity={id}>
      <CaseInspectionWorkspace
        caseWorkspace={{ ...w, case_summary: { ...w.case_summary, id } }}
        onInspectionOutcomeSave={vi.fn()} onInspectionPeriodSegmentsSave={vi.fn()}
        onInspectionPlanSave={vi.fn()} onInspectionTeamSave={vi.fn()}
        onLoadInspectionTeamIdentityOptions={vi.fn()}
        onCreateApprovalSubmission={vi.fn()} onCompleteApprovalSubmission={vi.fn()}
        onTransitionCase={vi.fn()} onFinalizeInspectionOutcome={onFinalize}
      />
    </CaseDraftSession>;
  }

  it("reopens the exact submitted final assessment and version while pending, then after unknown result and readiness withdrawal", async () => {
    let fail!: (reason: Error) => void;
    const onFinalize = vi.fn(() => new Promise<void>((_, reject) => { fail = reject; }));
    const view = render(editor("case-A", onFinalize));
    fireEvent.change(screen.getByLabelText("Đánh giá cuối cùng"), { target: { value: "  CAPA đã khắc phục đủ  " } });
    fireEvent.click(screen.getByRole("button", { name: "Chốt đánh giá cuối cùng" }));
    expect(onFinalize).toHaveBeenCalledOnce();
    expect(onFinalize).toHaveBeenCalledWith({ expected_version: 6, final_evaluation: "CAPA đã khắc phục đủ" });
    view.rerender(editor("case-B", onFinalize));
    expect(screen.getByLabelText("Đánh giá cuối cùng")).toHaveValue("");
    view.rerender(editor("case-A", onFinalize, false));
    const region = screen.getByRole("region", { name: "Khu vực đánh giá cuối cùng" });
    const field = within(region).getByLabelText("Đánh giá cuối cùng");
    expect(field).toHaveValue("CAPA đã khắc phục đủ");
    expect(field).toHaveAttribute("readonly");
    expect(field).toBeEnabled();
    expect(within(region).getByRole("status")).toHaveTextContent("expected_version 6");
    expect(within(region).getByRole("button", { name: "Chốt đánh giá cuối cùng" })).toBeDisabled();
    expect(within(region).getByRole("button", { name: "Hủy nhập đánh giá" })).toBeDisabled();
    fireEvent.change(field, { target: { value: "Do not overwrite" } });
    expect(field).toHaveValue("CAPA đã khắc phục đủ");
    await act(async () => fail(new CaseFieldMutationRecoveryError("canonical readback unknown")));
    expect(within(region).getByRole("status")).toHaveTextContent("Kết quả chốt chưa được xác minh");
    view.rerender(editor("case-B", onFinalize));
    view.rerender(editor("case-A", onFinalize, false));
    expect(screen.getByLabelText("Đánh giá cuối cùng")).toHaveValue("CAPA đã khắc phục đủ");
    expect(screen.getByRole("button", { name: "Hủy nhập đánh giá" })).toBeDisabled();
    expect(onFinalize).toHaveBeenCalledOnce();
  });

  it("does not restore an old finalization after a definitive 409 rejection", async () => {
    const onFinalize = vi.fn().mockRejectedValue(Object.assign(new Error("stale"), { status: 409 }));
    const view = render(editor("case-A", onFinalize));
    fireEvent.change(screen.getByLabelText("Đánh giá cuối cùng"), { target: { value: "Old finalization" } });
    fireEvent.click(screen.getByRole("button", { name: "Chốt đánh giá cuối cùng" }));
    await screen.findByRole("alert");
    view.rerender(editor("case-B", onFinalize));
    view.rerender(editor("case-A", onFinalize));
    expect(screen.getByLabelText("Đánh giá cuối cùng")).toHaveValue("");
    expect(screen.getByLabelText("Đánh giá cuối cùng")).not.toHaveAttribute("readonly");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(onFinalize).toHaveBeenCalledOnce();
  });
});
