import { useCaseCommandLock, useCaseDraftState } from "./CaseDraftSession";
import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";
import { useEffect, useMemo } from "react";

import { formatCompactDate } from "../../lib/presentation";
import type {
  CaseWorkspace,
  InspectionFinalEvaluationRequest,
  InspectionOutcomeUpsertRequest,
  InspectionPeriodSegmentsUpsertRequest,
  InspectionApprovalSubmissionCreateRequest,
  InspectionApprovalSubmissionCompleteRequest,
  InspectionApprovalSubmissionMutationResponse,
  CaseTransitionRequest,
  InspectionPlanUpsertRequest,
  InspectionTeamIdentityOption,
  InspectionTeamUpsertRequest,
} from "../../types";
import { EditableDetailValue } from "./EditableDetailValue";
import { DetailValue } from "./DetailValue";
import { CaseApprovalWorkspace } from "./CaseApprovalWorkspace";
import { CaseLifecycleActions } from "./CaseLifecycleActions";

type InspectionPlanDraft = {
  plan_start_on: string;
  plan_end_on: string;
  planning_sheet_name: string;
  decision_reference: string;
  decision_date: string;
};

type SubmittedFinalEvaluation = {
  kind: "inspection.final_evaluation";
  caseId: string;
  request: InspectionFinalEvaluationRequest;
};

type InspectionOutcomeDraft = {
  outcome_result: string;
  minutes_recorded_on: string;
  minutes_recorded_time: string;
  compliance_due_on: string;
};

function normalizeDateInputValue(value: string | null): string {
  const normalized = String(value ?? "").trim();
  const match = normalized.match(/^(\d{4}-\d{2}-\d{2})/);
  return match ? match[1] : "";
}

function normalizeText(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function getErrorStatus(error: Error): number | null {
  const status = (error as Error & { status?: unknown }).status;
  return typeof status === "number" ? status : null;
}

function getSectionErrorMessage(error: Error, sectionLabel: string): string {
  const status = getErrorStatus(error);
  if (status === 409) {
    return `Không thể lưu ${sectionLabel.toLowerCase()} vì hồ sơ đã bị thay đổi hoặc đã ở trạng thái kết thúc. Tải lại workspace rồi thử lại.`;
  }
  if (status === 403) {
    return `Bạn không có quyền cập nhật ${sectionLabel.toLowerCase()}. ${error.message}`;
  }
  if (status === 422) {
    return `Dữ liệu ${sectionLabel.toLowerCase()} chưa hợp lệ. ${error.message}`;
  }
  return error.message || `Không lưu được ${sectionLabel.toLowerCase()}.`;
}

function buildPlanDraft(caseWorkspace: CaseWorkspace): InspectionPlanDraft {
  return {
    plan_start_on: normalizeDateInputValue(caseWorkspace.inspection.plan_start_on),
    plan_end_on: normalizeDateInputValue(caseWorkspace.inspection.plan_end_on),
    planning_sheet_name: caseWorkspace.inspection.planning_sheet_name ?? "",
    decision_reference: caseWorkspace.inspection.plan_decision_reference ?? "",
    decision_date: normalizeDateInputValue(caseWorkspace.inspection.plan_decision_date),
  };
}

function buildOutcomeDraft(caseWorkspace: CaseWorkspace): InspectionOutcomeDraft {
  return {
    outcome_result: caseWorkspace.inspection.outcome_result ?? "",
    minutes_recorded_on: normalizeDateInputValue(caseWorkspace.inspection.minutes_recorded_on),
    minutes_recorded_time: caseWorkspace.inspection.minutes_recorded_time ?? "",
    compliance_due_on: normalizeDateInputValue(caseWorkspace.inspection.compliance_due_on),
  };
}

function formatInspectionPeriods(segments: InspectionPeriodSegmentsUpsertRequest["segments"]): string | null {
  return segments.length
    ? segments.map((segment) => `Lần ${segment.ordinal}: ${formatCompactDate(segment.started_on)} - ${formatCompactDate(segment.ended_on)}`).join("\n")
    : null;
}

function InspectionPeriodSection({ caseWorkspace, onSave }: { caseWorkspace: CaseWorkspace; onSave: (payload: InspectionPeriodSegmentsUpsertRequest) => Promise<void> }) {
  const [segments, setSegments] = useCaseDraftState<InspectionPeriodSegmentsUpsertRequest["segments"]>("period.segments", []);
  const [editing, setEditing] = useCaseDraftState("period.editing", false);
  const [pending, setPending] = useCaseDraftState("period.pending", false);
  const commandLock = useCaseCommandLock("inspection.period");
  const [errorMessage, setErrorMessage] = useCaseDraftState<string | null>("period.errorMessage", null);
  const readiness = caseWorkspace.inspection.inspection_period_edit_readiness;
  const frozen = pending || commandLock.pending || commandLock.requiresReview;
  const [draftVersion, setDraftVersion] = useCaseDraftState<number | null>("period.draftVersion", null);
  useEffect(() => {
    if (!editing) setSegments((caseWorkspace.inspection.inspection_period_segments ?? []).map(({ ordinal, started_on, ended_on }) => ({ ordinal, started_on: normalizeDateInputValue(started_on), ended_on: normalizeDateInputValue(ended_on) })));
  }, [caseWorkspace.inspection.inspection_period_segments, editing]);
  const renumber = (next: InspectionPeriodSegmentsUpsertRequest["segments"]) => next.map((segment, index) => ({ ...segment, ordinal: index + 1 }));
  async function save() {
    if (frozen || !readiness?.available) return;
    const command = commandLock.acquire();
    if (!command) return;
    setPending(true); setErrorMessage(null);
    try { await onSave({ expected_version: draftVersion, segments: renumber(segments) }); setEditing(false); }
    catch (error) { if (error instanceof CaseFieldMutationRecoveryError) commandLock.requireReview(command); setErrorMessage(getSectionErrorMessage(error instanceof Error ? error : new Error("Không lưu được các đợt kiểm tra."), "các đợt kiểm tra")); }
    finally { commandLock.release(command); setPending(false); }
  }
  return <section className="workspace-section inspection-period-section">
    <div className="workspace-section-heading"><h4>Các đợt kiểm tra canonical</h4><button disabled={!readiness?.available || frozen || editing} onClick={() => { setDraftVersion(readiness?.expected_version ?? null); setEditing(true); setErrorMessage(null); }} type="button">{readiness?.label ?? "Sửa các đợt kiểm tra"}</button></div>
    {!readiness?.available && readiness?.reason_code ? <p className="workspace-note">Không thể chỉnh sửa: {readiness.reason_code}.</p> : null}
    {!editing ? <DetailValue multiline label="Các lần kiểm tra" value={formatInspectionPeriods(segments)} /> : <div className="inspection-period-editor">
      {segments.map((segment, index) => <div className="inspection-team-edit-row" key={segment.ordinal}>
        <span>Lần {index + 1}</span><input aria-label={`Từ ngày lần ${index + 1}`} disabled={pending || commandLock.pending} readOnly={commandLock.requiresReview} onChange={(event) => { if (frozen) return; setSegments((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, started_on: event.target.value } : item)); }} type="date" value={segment.started_on} />
        <input aria-label={`Đến ngày lần ${index + 1}`} disabled={pending || commandLock.pending} readOnly={commandLock.requiresReview} onChange={(event) => { if (frozen) return; setSegments((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ended_on: event.target.value } : item)); }} type="date" value={segment.ended_on} />
        <button disabled={frozen || index === 0} onClick={() => { if (frozen) return; setSegments((current) => { const next=[...current]; [next[index - 1], next[index]]=[next[index], next[index - 1]]; return renumber(next); }); }} type="button">Lên</button>
        <button disabled={frozen || index === segments.length - 1} onClick={() => { if (frozen) return; setSegments((current) => { const next=[...current]; [next[index + 1], next[index]]=[next[index], next[index + 1]]; return renumber(next); }); }} type="button">Xuống</button>
        <button disabled={frozen} onClick={() => { if (frozen) return; setSegments((current) => renumber(current.filter((_, itemIndex) => itemIndex !== index))); }} type="button">Xóa</button>
      </div>)}
      <div className="panel-actions"><button disabled={frozen} onClick={() => { if (frozen) return; setSegments((current) => [...current, { ordinal: current.length + 1, started_on: "", ended_on: "" }]); }} type="button">Thêm lần kiểm tra</button><button disabled={frozen} onClick={() => void save()} type="button">Lưu các đợt kiểm tra</button><button disabled={frozen} onClick={() => { if (!frozen) setEditing(false); }} type="button">Hủy</button></div>
    </div>}
    {errorMessage || commandLock.requiresReview ? <p className="form-error" role="alert">{errorMessage ?? "Chưa xác minh kết quả lưu. Không gửi lại; tải lại hồ sơ để kiểm tra."}</p> : null}
    {commandLock.requiresReview ? <p className="workspace-note" role="status">Các đợt kiểm tra đã gửi được giữ nguyên để đối chiếu; không sửa, đổi thứ tự, xóa, hủy hoặc gửi lại khi kết quả chưa xác minh.</p> : null}
  </section>;
}

function InspectionPlanSection({
  caseWorkspace,
  onSave,
}: {
  caseWorkspace: CaseWorkspace;
  onSave: (payload: InspectionPlanUpsertRequest) => Promise<void>;
}) {
  const currentDraft = useMemo(() => buildPlanDraft(caseWorkspace), [caseWorkspace]);
  const [draft, setDraft] = useCaseDraftState<InspectionPlanDraft>("plan.draft", currentDraft);
  const [draftVersion, setDraftVersion] = useCaseDraftState("plan.draftVersion", caseWorkspace.inspection.plan_row_version);
  const [editingField, setEditingField] = useCaseDraftState<"plan_start_on" | "plan_end_on" | "planning_sheet_name" | "decision_reference" | "decision_date" | null>("plan.editingField", null);
  const [pending, setPending] = useCaseDraftState("plan.pending", false);
  const commandLock = useCaseCommandLock("inspection.plan");
  const [errorMessage, setErrorMessage] = useCaseDraftState<string | null>("plan.errorMessage", null);

  useEffect(() => {
    if (!editingField) {
      setDraft(currentDraft);
      setErrorMessage(null);
    }
  }, [currentDraft, editingField]);

  async function saveField() {
    if (!editingField || pending || commandLock.pending || commandLock.requiresReview) {
      return;
    }
    const command = commandLock.acquire();
    if (!command) return;
    setPending(true);
    setErrorMessage(null);
    try {
      const value = editingField === "decision_reference"
        ? normalizeText(draft.decision_reference)
        : editingField === "decision_date"
          ? normalizeText(draft.decision_date)
          : normalizeText(draft[editingField]);
      await onSave({ expected_version: draftVersion, [editingField]: value });
      setEditingField(null);
    } catch (error) {
      if (error instanceof CaseFieldMutationRecoveryError) commandLock.requireReview(command);
      const nextError = error instanceof Error ? error : new Error("Không lưu được kế hoạch kiểm tra.");
      setErrorMessage(getSectionErrorMessage(nextError, "Kế hoạch kiểm tra"));
    } finally {
      commandLock.release(command);
      setPending(false);
    }
  }

  function cancelEdit() {
    setDraft(currentDraft);
    setErrorMessage(null);
    setEditingField(null);
  }

  function startEdit(field: NonNullable<typeof editingField>) {
    setDraft(currentDraft);
    setDraftVersion(caseWorkspace.inspection.plan_row_version);
    setEditingField(field);
    setErrorMessage(null);
  }

  return (
    <>
    <section className="workspace-section inspection-plan-section">
      {commandLock.requiresReview ? <p className="form-error" role="alert">Chưa xác minh kết quả lưu. Không gửi lại; sao chép bản nháp rồi tải lại hồ sơ để kiểm tra. {errorMessage}</p> : null}
      <h4 className="sr-only">Kế hoạch kiểm tra</h4>
      <div className="detail-grid compact-grid detail-form-matrix inspection-decision-fields">
        <EditableDetailValue
          editButtonLabel="Sửa Số/Tham chiếu QĐKT"
          error={!commandLock.requiresReview && editingField === "decision_reference" ? errorMessage : null}
          isEditing={editingField === "decision_reference"}
          label="Số/Tham chiếu QĐKT"
          onCancel={cancelEdit}
          onEdit={() => startEdit("decision_reference")}
          onSave={() => void saveField()}
          pending={pending} saveDisabled={commandLock.pending || commandLock.requiresReview}
          value={caseWorkspace.inspection.plan_decision_reference}
        >
          <input aria-label="Số/Tham chiếu QĐKT" disabled={pending} onChange={(event) => setDraft((current) => ({ ...current, decision_reference: event.target.value }))} value={draft.decision_reference} />
        </EditableDetailValue>
        <EditableDetailValue
          editButtonLabel="Sửa Ngày QĐKT"
          error={!commandLock.requiresReview && editingField === "decision_date" ? errorMessage : null}
          isEditing={editingField === "decision_date"}
          label="Ngày QĐKT"
          onCancel={cancelEdit}
          onEdit={() => startEdit("decision_date")}
          onSave={() => void saveField()}
          pending={pending} saveDisabled={commandLock.pending || commandLock.requiresReview}
          value={formatCompactDate(caseWorkspace.inspection.plan_decision_date)}
        >
          <input aria-label="Ngày QĐKT" disabled={pending} onChange={(event) => setDraft((current) => ({ ...current, decision_date: event.target.value }))} type="date" value={draft.decision_date} />
        </EditableDetailValue>
      </div>
    </section>
    <section className="workspace-section inspection-plan-additional-section">
      <div className="detail-grid compact-grid inspection-plan-additional">
        <EditableDetailValue
          editButtonLabel="Sửa Từ ngày kế hoạch"
          error={!commandLock.requiresReview && editingField === "plan_start_on" ? errorMessage : null}
          isEditing={editingField === "plan_start_on"}
          label="Từ ngày"
          onCancel={cancelEdit}
          onEdit={() => {
            startEdit("plan_start_on");
          }}
          onSave={() => void saveField()}
          pending={pending} saveDisabled={commandLock.pending || commandLock.requiresReview}
          value={formatCompactDate(caseWorkspace.inspection.plan_start_on)}
        >
          <input
            aria-label="Từ ngày kế hoạch"
            disabled={pending}
            onChange={(event) => setDraft((current) => ({ ...current, plan_start_on: event.target.value }))}
            type="date"
            value={draft.plan_start_on}
          />
        </EditableDetailValue>
        <EditableDetailValue
          editButtonLabel="Sửa Tên bảng kế hoạch"
          error={!commandLock.requiresReview && editingField === "planning_sheet_name" ? errorMessage : null}
          isEditing={editingField === "planning_sheet_name"}
          label="Tên bảng kế hoạch"
          onCancel={cancelEdit}
          onEdit={() => startEdit("planning_sheet_name")}
          onSave={() => void saveField()}
          pending={pending}
          saveDisabled={commandLock.pending || commandLock.requiresReview}
          value={caseWorkspace.inspection.planning_sheet_name}
        >
          <input
            aria-label="Tên bảng kế hoạch"
            disabled={pending}
            onChange={(event) => setDraft((current) => ({ ...current, planning_sheet_name: event.target.value }))}
            value={draft.planning_sheet_name}
          />
        </EditableDetailValue>
        <DetailValue label="Gợi ý tài liệu legacy (chỉ đọc)" value={caseWorkspace.inspection.decision_document_hint} />

        <EditableDetailValue
          editButtonLabel="Sửa Đến ngày kế hoạch"
          error={!commandLock.requiresReview && editingField === "plan_end_on" ? errorMessage : null}
          isEditing={editingField === "plan_end_on"}
          label="Đến ngày"
          onCancel={cancelEdit}
          onEdit={() => {
            startEdit("plan_end_on");
          }}
          onSave={() => void saveField()}
          pending={pending} saveDisabled={commandLock.pending || commandLock.requiresReview}
          value={formatCompactDate(caseWorkspace.inspection.plan_end_on)}
        >
          <input
            aria-label="Đến ngày kế hoạch"
            disabled={pending}
            onChange={(event) => setDraft((current) => ({ ...current, plan_end_on: event.target.value }))}
            type="date"
            value={draft.plan_end_on}
          />
        </EditableDetailValue>
      </div>
    </section>
    </>
  );
}

function InspectionTeamSection({
  caseWorkspace,
  onLoadIdentityOptions,
  onSave,
}: {
  caseWorkspace: CaseWorkspace;
  onLoadIdentityOptions: () => Promise<InspectionTeamIdentityOption[]>;
  onSave: (payload: InspectionTeamUpsertRequest) => Promise<void>;
}) {
  const team = caseWorkspace.inspection.team;
  const readiness = caseWorkspace.inspection.team_edit_readiness ?? {
    action_key: "edit_inspection_team" as const,
    label: "Sửa đoàn kiểm tra",
    available: false,
    reason_code: "structured_read_unavailable",
    required_permissions: [],
    expected_version: null,
    mode: null,
  };
  const [editing, setEditing] = useCaseDraftState("team.editing", false);
  const [options, setOptions] = useCaseDraftState<InspectionTeamIdentityOption[]>("team.options", []);
  const [members, setMembers] = useCaseDraftState<InspectionTeamUpsertRequest["members"]>("team.members", []);
  const [pending, setPending] = useCaseDraftState("team.pending", false);
  const commandLock = useCaseCommandLock("inspection.team");
  const [errorMessage, setErrorMessage] = useCaseDraftState<string | null>("team.errorMessage", null);

  const [draftVersion, setDraftVersion] = useCaseDraftState<number | null>("team.draftVersion", null);

  useEffect(() => {
    if (!editing && !pending) {
      setMembers((team?.members ?? []).map((member) => ({
        inspector_profile_id: member.inspector_profile_id,
        person_id: member.person_id,
        participant_catalog_id: member.participant_catalog_id,
        identity_kind: member.identity_kind === "ORGANIZATION_REPRESENTATIVE" ? "ORGANIZATION_REPRESENTATIVE" : member.inspector_profile_id ? "INSPECTOR_PROFILE" : null,
        role_code: member.sort_order === 1 ? "LEADER" : member.sort_order === 2 ? "SECRETARY" : "MEMBER",
        sort_order: member.sort_order,
      })));
    }
  }, [editing, pending, team]);

  async function startEdit() {
    if (!readiness.available || pending || editing) return;
    setDraftVersion(readiness.expected_version);
    setErrorMessage(null);
    setPending(true);
    try {
      setOptions(await onLoadIdentityOptions());
      setEditing(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Không tải được danh sách định danh đoàn kiểm tra.");
    } finally {
      setPending(false);
    }
  }

  function identityValue(member: InspectionTeamUpsertRequest["members"][number]) {
    if (member.inspector_profile_id) return `profile:${member.inspector_profile_id}`;
    if (member.person_id) return `person:${member.person_id}`;
    if (member.participant_catalog_id) return `organization:${member.participant_catalog_id}`;
    return "";
  }

  function setIdentity(index: number, value: string) {
    const [kind, id] = value.split(":", 2);
    setMembers((current) => current.map((member, memberIndex) => memberIndex !== index ? member : {
      ...member,
      inspector_profile_id: kind === "profile" && id ? id : null,
      person_id: kind === "person" && id ? id : null,
      participant_catalog_id: kind === "organization" && id ? id : null,
      identity_kind: kind === "organization" ? "ORGANIZATION_REPRESENTATIVE" : kind === "profile" ? "INSPECTOR_PROFILE" : null,
    }));
  }

  function moveMember(index: number, direction: -1 | 1) {
    setMembers((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next.map((member, index) => ({
        ...member,
        sort_order: index + 1,
        role_code: index === 0 ? "LEADER" : index === 1 ? "SECRETARY" : "MEMBER",
      }));
    });
  }

  async function save() {
    if (pending || !readiness.available || members.length === 0 || members.some((member) => !identityValue(member))) return;
    const command = commandLock.acquire();
    if (!command) return;
    setPending(true);
    setErrorMessage(null);
    try {
      await onSave({
        expected_version: draftVersion,
        members: members.map((member, index) => ({
          ...member,
          sort_order: index + 1,
          role_code: index === 0 ? "LEADER" : index === 1 ? "SECRETARY" : "MEMBER",
        })),
      });
      setEditing(false);
    } catch (error) {
      if (error instanceof CaseFieldMutationRecoveryError) commandLock.requireReview(command);
      const nextError = error instanceof Error ? error : new Error("Không lưu được đoàn kiểm tra.");
      if (getErrorStatus(nextError) === 409) {
        setEditing(false);
        setMembers((team?.members ?? []).map((member) => ({
          inspector_profile_id: member.inspector_profile_id,
          person_id: member.person_id,
          identity_kind: member.identity_kind === "ORGANIZATION_REPRESENTATIVE" ? "ORGANIZATION_REPRESENTATIVE" : member.inspector_profile_id ? "INSPECTOR_PROFILE" : null,
          participant_catalog_id: member.participant_catalog_id,
          role_code: member.role_code === "LEADER" || member.role_code === "SECRETARY" ? member.role_code : "MEMBER",
          sort_order: member.sort_order,
        })));
      }
      setErrorMessage(getSectionErrorMessage(nextError, "đoàn kiểm tra"));
    } finally {
      commandLock.release(command);
      setPending(false);
    }
  }

  return (
    <section className="workspace-section inspection-team-section">
      <div className="workspace-section-heading"><h4>Đoàn kiểm tra</h4><button disabled={!readiness.available || pending || editing} onClick={() => void startEdit()} type="button">{readiness.label}</button></div>
      <div className="detail-grid compact-grid detail-form-matrix">
        <DetailValue label="Thanh tra viên" multiline value={caseWorkspace.inspection.team_display_text} />
      </div>
      {team?.members.map((member) => <div className="inspection-team-member" key={member.id}>
        <strong>{member.display_name ?? "Định danh chưa resolve"}</strong><span>{member.role_code ?? member.role_label ?? "Chưa có vai trò"}</span>
        {member.identity_status === "unresolved" ? <span className="form-error">Không thể round-trip định danh này.</span> : null}
      </div>)}
      {!readiness.available && readiness.reason_code ? <p className="workspace-note">Không thể chỉnh sửa: {readiness.reason_code}.</p> : null}
      {errorMessage || commandLock.requiresReview ? <p className="form-error" role="alert">{errorMessage ?? "Chưa xác minh kết quả lưu. Không gửi lại; tải lại hồ sơ để kiểm tra."}</p> : null}
      {editing ? <div className="inspection-team-editor">
        <p className="workspace-note">Lưu sẽ thay toàn bộ danh sách từ dữ liệu có cấu trúc này. Mô tả legacy chỉ đọc, không được dùng để tạo thành viên.</p>
        {/* Editable roles are positional slots; changing their participant must not replace the focused select. */}
        {members.map((member, index) => <div className="inspection-team-edit-row" key={index}>
          <select aria-label={`Định danh thành viên ${index + 1}`} disabled={pending} onChange={(event) => setIdentity(index, event.target.value)} value={identityValue(member)}>
            <option value="">Chọn định danh</option>
            {options.map((option) => <option key={`${option.identity_kind}:${option.inspector_profile_id ?? option.person_id ?? option.participant_catalog_id}`} value={`${option.identity_kind === "inspector_profile" ? "profile" : option.identity_kind === "organization_representative" ? "organization" : "person"}:${option.inspector_profile_id ?? option.person_id ?? option.participant_catalog_id}`}>
              {option.display_name}{option.is_active === false ? " (không hoạt động)" : ""}
            </option>)}
          </select>
          <span className="workspace-note">{index === 0 ? "LEADER" : index === 1 ? "SECRETARY" : "MEMBER"}</span>
          <button aria-label={`Đưa thành viên ${index + 1} lên`} disabled={pending || index === 0} onClick={() => moveMember(index, -1)} type="button">Lên</button>
          <button aria-label={`Đưa thành viên ${index + 1} xuống`} disabled={pending || index === members.length - 1} onClick={() => moveMember(index, 1)} type="button">Xuống</button>
          <button aria-label={`Xóa thành viên ${index + 1}`} disabled={pending} onClick={() => setMembers((current) => current.filter((_, itemIndex) => itemIndex !== index).map((item, itemIndex) => ({ ...item, sort_order: itemIndex + 1, role_code: itemIndex === 0 ? "LEADER" : itemIndex === 1 ? "SECRETARY" : "MEMBER" })))} type="button">Xóa</button>
        </div>)}
        <div className="panel-actions">
          <button disabled={pending} onClick={() => setMembers((current) => [...current, { inspector_profile_id: null, person_id: null, role_code: current.length === 0 ? "LEADER" : current.length === 1 ? "SECRETARY" : "MEMBER", sort_order: current.length + 1 }])} type="button">Thêm thành viên</button>
          <button disabled={pending || commandLock.pending || commandLock.requiresReview || members.length === 0 || members.some((member) => !identityValue(member))} onClick={() => void save()} type="button">{pending ? "Đang lưu..." : "Lưu đoàn kiểm tra"}</button>
          <button disabled={pending} onClick={() => setEditing(false)} type="button">Hủy</button>
        </div>
      </div> : null}
    </section>
  );
}

function InspectionOutcomeSection({
  caseWorkspace,
  onSave,
}: {
  caseWorkspace: CaseWorkspace;
  onSave: (payload: InspectionOutcomeUpsertRequest) => Promise<void>;
}) {
  const currentDraft = useMemo(() => buildOutcomeDraft(caseWorkspace), [caseWorkspace]);
  const [draft, setDraft] = useCaseDraftState<InspectionOutcomeDraft>("outcome.draft", currentDraft);
  const [draftVersion, setDraftVersion] = useCaseDraftState("outcome.draftVersion", caseWorkspace.inspection.outcome_row_version);
  const [editingField, setEditingField] = useCaseDraftState<
    "outcome_result" | "minutes_recorded_on" | "minutes_recorded_time" | "compliance_due_on" | null
  >("outcome.editingField", null);
  const [pending, setPending] = useCaseDraftState("outcome.pending", false);
  const commandLock = useCaseCommandLock("inspection.outcome");
  const [errorMessage, setErrorMessage] = useCaseDraftState<string | null>("outcome.errorMessage", null);

  useEffect(() => {
    if (!editingField) {
      setDraft(currentDraft);
      setErrorMessage(null);
    }
  }, [currentDraft, editingField]);

  // Backend rejects a minutes time without its date. These are separate
  // field-owned writes, so respect the *canonical* value of the other field.
  // Never auto-clear a different field or silently compose a multi-field write.
  const minutesDependencyError =
    editingField === "minutes_recorded_time" && draft.minutes_recorded_time.trim() && !caseWorkspace.inspection.minutes_recorded_on
      ? "Lưu ngày biên bản trước khi nhập giờ biên bản."
      : editingField === "minutes_recorded_on" && !draft.minutes_recorded_on.trim() && !!caseWorkspace.inspection.minutes_recorded_time
        ? "Xóa giờ biên bản và lưu trước khi xóa ngày biên bản."
        : null;

  async function saveField() {
    if (!editingField || pending || commandLock.pending || commandLock.requiresReview || minutesDependencyError) {
      return;
    }
    const command = commandLock.acquire();
    if (!command) return;
    setPending(true);
    setErrorMessage(null);
    try {
      await onSave({ expected_version: draftVersion, [editingField]: normalizeText(draft[editingField]) });
      setEditingField(null);
    } catch (error) {
      if (error instanceof CaseFieldMutationRecoveryError) commandLock.requireReview(command);
      const nextError = error instanceof Error ? error : new Error("Không lưu được kết quả kiểm tra.");
      setErrorMessage(getSectionErrorMessage(nextError, "kết quả kiểm tra"));
    } finally {
      commandLock.release(command);
      setPending(false);
    }
  }

  function cancelEdit() {
    setDraft(currentDraft);
    setErrorMessage(null);
    setEditingField(null);
  }

  function startEdit(field: NonNullable<typeof editingField>) {
    setDraft(currentDraft);
    setDraftVersion(caseWorkspace.inspection.outcome_row_version);
    setEditingField(field);
    setErrorMessage(null);
  }

  return (
    <section className="workspace-section inspection-outcome-section">
      {commandLock.requiresReview ? <p className="form-error" role="alert">Chưa xác minh kết quả lưu. Không gửi lại; sao chép bản nháp rồi tải lại hồ sơ để kiểm tra. {errorMessage}</p> : null}
      <h4 className="sr-only">Thực hiện & kết quả</h4>
      <div className="detail-grid compact-grid detail-form-matrix">
        <div className="inspection-date-fields">
          <DetailValue label="Ngày kiểm tra" multiline value={formatInspectionPeriods(caseWorkspace.inspection.inspection_period_segments ?? [])} />
          <EditableDetailValue editButtonLabel="Sửa Ngày biên bản" error={!commandLock.requiresReview && editingField === "minutes_recorded_on" ? minutesDependencyError || errorMessage : null} isEditing={editingField === "minutes_recorded_on"} label="Ngày biên bản/report" onCancel={cancelEdit} onEdit={() => startEdit("minutes_recorded_on")} onSave={() => void saveField()} pending={pending} saveDisabled={commandLock.pending || commandLock.requiresReview || !!minutesDependencyError} value={formatCompactDate(caseWorkspace.inspection.minutes_recorded_on)}>
            <input aria-label="Ngày biên bản/report" disabled={pending} onChange={(event) => setDraft((current) => ({ ...current, minutes_recorded_on: event.target.value }))} type="date" value={draft.minutes_recorded_on} />
          </EditableDetailValue>
        </div>
        <div className="inspection-result-fields">
          <DetailValue label="Tiêu chuẩn áp dụng" value={caseWorkspace.case_summary.applicable_standard} />
          <EditableDetailValue
            editButtonLabel="Sửa Kết quả kiểm tra"
            error={!commandLock.requiresReview && editingField === "outcome_result" ? errorMessage : null}
            isEditing={editingField === "outcome_result"}
            label="Đánh giá kết quả"
            multiline
            onCancel={cancelEdit}
            onEdit={() => {
              startEdit("outcome_result");
            }}
            onSave={() => void saveField()}
            pending={pending} saveDisabled={commandLock.pending || commandLock.requiresReview}
            value={caseWorkspace.inspection.outcome_result}
          >
            <textarea
              aria-label="Kết quả kiểm tra"
              className="inspection-textarea"
              disabled={pending}
              onChange={(event) => setDraft((current) => ({ ...current, outcome_result: event.target.value }))}
              rows={4}
              value={draft.outcome_result}
            />
          </EditableDetailValue>
        </div>
        <div className="inspection-outcome-additional">
          <DetailValue label="QĐKT legacy (chỉ đọc)" value={caseWorkspace.inspection.outcome_decision_reference_compatibility} />
          <DetailValue label="Biên bản legacy (chỉ đọc)" value={caseWorkspace.inspection.bbkt_reference} />

          <DetailValue label="Thời điểm thực hiện" value={formatCompactDate(caseWorkspace.inspection.executed_on)} />

          <EditableDetailValue editButtonLabel="Sửa Giờ biên bản" error={!commandLock.requiresReview && editingField === "minutes_recorded_time" ? minutesDependencyError || errorMessage : null} isEditing={editingField === "minutes_recorded_time"} label="Giờ biên bản/report" onCancel={cancelEdit} onEdit={() => startEdit("minutes_recorded_time")} onSave={() => void saveField()} pending={pending} saveDisabled={commandLock.pending || commandLock.requiresReview || !!minutesDependencyError} value={caseWorkspace.inspection.minutes_recorded_time}>
            <input aria-label="Giờ biên bản/report" disabled={pending} onChange={(event) => setDraft((current) => ({ ...current, minutes_recorded_time: event.target.value }))} type="time" value={draft.minutes_recorded_time} />
          </EditableDetailValue>
          <EditableDetailValue editButtonLabel="Sửa Hạn tuân thủ" error={!commandLock.requiresReview && editingField === "compliance_due_on" ? errorMessage : null} isEditing={editingField === "compliance_due_on"} label="Hạn tuân thủ/tái kiểm tra" onCancel={cancelEdit} onEdit={() => startEdit("compliance_due_on")} onSave={() => void saveField()} pending={pending} saveDisabled={commandLock.pending || commandLock.requiresReview} value={formatCompactDate(caseWorkspace.inspection.compliance_due_on)}>
            <input aria-label="Hạn tuân thủ/tái kiểm tra" disabled={pending} onChange={(event) => setDraft((current) => ({ ...current, compliance_due_on: event.target.value }))} type="date" value={draft.compliance_due_on} />
          </EditableDetailValue>
        </div>
      </div>
    </section>
  );
}

function CaseInspectionEditor({
  caseWorkspace,
  onInspectionPlanSave,
  onInspectionOutcomeSave,
  onInspectionPeriodSegmentsSave,
  onInspectionTeamSave,
  onLoadInspectionTeamIdentityOptions,
  onFinalizeInspectionOutcome,
  onCreateApprovalSubmission,
  onCompleteApprovalSubmission,
  onTransitionCase,
}: {
  caseWorkspace: CaseWorkspace;
  onInspectionPlanSave: (payload: InspectionPlanUpsertRequest) => Promise<void>;
  onInspectionOutcomeSave: (payload: InspectionOutcomeUpsertRequest) => Promise<void>;
  onInspectionPeriodSegmentsSave: (payload: InspectionPeriodSegmentsUpsertRequest) => Promise<void>;
  onInspectionTeamSave: (payload: InspectionTeamUpsertRequest) => Promise<void>;
  onLoadInspectionTeamIdentityOptions: () => Promise<InspectionTeamIdentityOption[]>;
  onFinalizeInspectionOutcome?: (payload: InspectionFinalEvaluationRequest) => Promise<void>;
  onCreateApprovalSubmission: (stage: "PCT" | "CT", payload: InspectionApprovalSubmissionCreateRequest) => Promise<InspectionApprovalSubmissionMutationResponse>;
  onCompleteApprovalSubmission: (submissionId: string, payload: InspectionApprovalSubmissionCompleteRequest) => Promise<InspectionApprovalSubmissionMutationResponse>;
  onTransitionCase: (payload: CaseTransitionRequest) => Promise<void>;
}) {
  const [finalEvaluation, setFinalEvaluation] = useCaseDraftState("inspection.finalEvaluation", "");
  const [finalDraftVersion, setFinalDraftVersion] = useCaseDraftState<number | null | undefined>("inspection.finalDraftVersion", undefined);
  const [finalizationError, setFinalizationError] = useCaseDraftState<string | null>("inspection.finalizationError", null);
  const [finalizationPending, setFinalizationPending] = useCaseDraftState("inspection.finalizationPending", false);
  const finalLock = useCaseCommandLock("inspection.finalization");
  const finalFrozen = finalLock.pending || finalLock.requiresReview || finalizationPending;
  const submittedPayload = finalLock.pending || finalLock.requiresReview
    ? finalLock.commandPayload<SubmittedFinalEvaluation>() : undefined;
  const submittedFinal = submittedPayload?.kind === "inspection.final_evaluation"
    && submittedPayload.caseId === caseWorkspace.case_summary.id ? submittedPayload.request : null;
  const visibleFinal = submittedFinal?.final_evaluation ?? finalEvaluation;
  const finalization = caseWorkspace.inspection.final_evaluation_readiness ?? {
    action_key: "finalize_inspection_outcome",
    label: "Chốt đánh giá cuối cùng",
    available: false,
    reason_code: "readiness_unavailable",
    required_permissions: [],
    expected_version: null,
  };

  async function finalize() {
    if (finalizationPending || finalLock.pending || finalLock.requiresReview || !onFinalizeInspectionOutcome || !finalization.available || !finalEvaluation.trim() || finalDraftVersion == null) return;
    const request: InspectionFinalEvaluationRequest = {
      expected_version: finalDraftVersion,
      final_evaluation: finalEvaluation.trim(),
    };
    const command = finalLock.acquire({
      kind: "inspection.final_evaluation",
      caseId: caseWorkspace.case_summary.id,
      request: { ...request },
    } satisfies SubmittedFinalEvaluation);
    if (!command) return;
    setFinalizationPending(true);
    setFinalizationError(null);
    try {
      await onFinalizeInspectionOutcome(request);
      setFinalEvaluation("");
      setFinalDraftVersion(undefined);
    } catch (error) {
      if (error instanceof CaseFieldMutationRecoveryError) finalLock.requireReview(command);
      setFinalizationError(getSectionErrorMessage(error instanceof Error ? error : new Error("Không thể chốt đánh giá."), "đánh giá cuối cùng"));
    } finally {
      finalLock.release(command);
      setFinalizationPending(false);
    }
  }
  return (
    <div className="inspection-workspace" data-case-inspection tabIndex={-1} aria-label="Khu vực kiểm tra">
      <div className="inspection-detail-grid">
        <InspectionPlanSection caseWorkspace={caseWorkspace} onSave={onInspectionPlanSave} />
        <InspectionTeamSection key={caseWorkspace.inspection.team?.team_id ?? "new-team"} caseWorkspace={caseWorkspace} onLoadIdentityOptions={onLoadInspectionTeamIdentityOptions} onSave={onInspectionTeamSave} />
        <InspectionOutcomeSection caseWorkspace={caseWorkspace} onSave={onInspectionOutcomeSave} />
        <InspectionPeriodSection caseWorkspace={caseWorkspace} onSave={onInspectionPeriodSegmentsSave} />
        <CaseApprovalWorkspace caseWorkspace={caseWorkspace} onComplete={onCompleteApprovalSubmission} onCreate={onCreateApprovalSubmission} />
        <CaseLifecycleActions caseWorkspace={caseWorkspace} onTransition={onTransitionCase} />
        <section className="workspace-section" data-case-final-evaluation tabIndex={-1} aria-label="Khu vực đánh giá cuối cùng">
          <h4>Đánh giá cuối cùng</h4>
          <DetailValue label="Giá trị đã chốt" value={caseWorkspace.inspection.final_evaluation} />
          {caseWorkspace.inspection.final_evaluation === null || finalDraftVersion !== undefined || submittedFinal !== null ? (
            <div aria-label="Chốt đánh giá cuối cùng" className="panel-actions panel-actions-tight inspection-final-actions" role="group">
              <input aria-label="Đánh giá cuối cùng" disabled={(!finalization.available && !submittedFinal && !finalLock.requiresReview) || finalizationPending} readOnly={finalFrozen} onChange={(event) => { if (finalFrozen) return; if (finalDraftVersion === undefined) setFinalDraftVersion(finalization.expected_version); setFinalEvaluation(event.target.value); }} value={visibleFinal} />
              <button disabled={!onFinalizeInspectionOutcome || !finalization.available || finalizationPending || finalLock.pending || finalLock.requiresReview || finalDraftVersion == null || !finalEvaluation.trim()} onClick={() => void finalize()} type="button">
                {finalizationPending ? "Đang chốt..." : finalization.label}
              </button>
              {(finalDraftVersion !== undefined || submittedFinal !== null) ? <button disabled={finalFrozen} onClick={() => { if (finalFrozen) return; setFinalEvaluation(""); setFinalDraftVersion(undefined); setFinalizationError(null); }} type="button">Hủy nhập đánh giá</button> : null}
            </div>
          ) : null}
          {!finalization.available && finalization.reason_code ? <p className="workspace-note">Không thể chốt: {finalization.reason_code}.</p> : null}
          {finalizationError || finalLock.requiresReview ? <p className="form-error" role="alert">{finalizationError ?? "Chưa xác minh kết quả chốt. Không gửi lại; tải lại hồ sơ để kiểm tra."}</p> : null}
          {submittedFinal ? <p className="workspace-note" role="status">
            {finalLock.pending ? "Đang xác minh kết quả chốt." : "Kết quả chốt chưa được xác minh."}
            {" "}Đã gửi với expected_version {submittedFinal.expected_version}. Giữ nguyên đánh giá cuối cùng đã gửi để sao chép và đối chiếu với hồ sơ canonical; không sửa, hủy hay gửi lại khi kết quả chốt chưa xác minh.
          </p> : finalLock.requiresReview ? <p className="workspace-note" role="status">Kết quả chốt chưa xác minh. Không gửi lại trước khi kiểm tra hồ sơ canonical.</p> : null}
        </section>
      </div>
    </div>
  );
}

export function CaseInspectionWorkspace(props: Parameters<typeof CaseInspectionEditor>[0]) {
  return <CaseInspectionEditor key={props.caseWorkspace.case_summary.id} {...props} />;
}
