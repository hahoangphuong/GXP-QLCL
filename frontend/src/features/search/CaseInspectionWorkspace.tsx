import { useEffect, useMemo, useState } from "react";

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

function InspectionPeriodSection({ caseWorkspace, onSave }: { caseWorkspace: CaseWorkspace; onSave: (payload: InspectionPeriodSegmentsUpsertRequest) => Promise<void> }) {
  const [segments, setSegments] = useState<InspectionPeriodSegmentsUpsertRequest["segments"]>([]);
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const readiness = caseWorkspace.inspection.inspection_period_edit_readiness;
  useEffect(() => {
    if (!editing) setSegments((caseWorkspace.inspection.inspection_period_segments ?? []).map(({ ordinal, started_on, ended_on }) => ({ ordinal, started_on: normalizeDateInputValue(started_on), ended_on: normalizeDateInputValue(ended_on) })));
  }, [caseWorkspace.inspection.inspection_period_segments, editing]);
  const renumber = (next: InspectionPeriodSegmentsUpsertRequest["segments"]) => next.map((segment, index) => ({ ...segment, ordinal: index + 1 }));
  async function save() {
    if (pending || !readiness?.available) return;
    setPending(true); setErrorMessage(null);
    try { await onSave({ expected_version: readiness.expected_version, segments: renumber(segments) }); setEditing(false); }
    catch (error) { setErrorMessage(getSectionErrorMessage(error instanceof Error ? error : new Error("Không lưu được các đợt kiểm tra."), "các đợt kiểm tra")); }
    finally { setPending(false); }
  }
  return <section className="workspace-section inspection-period-section">
    <div className="workspace-section-heading"><h4>Các đợt kiểm tra canonical</h4><button disabled={!readiness?.available || pending} onClick={() => setEditing(true)} type="button">{readiness?.label ?? "Sửa các đợt kiểm tra"}</button></div>
    {!readiness?.available && readiness?.reason_code ? <p className="workspace-note">Không thể chỉnh sửa: {readiness.reason_code}.</p> : null}
    {!editing ? <DetailValue multiline label="Các lần kiểm tra" value={segments.length ? segments.map((segment) => `Lần ${segment.ordinal}: ${formatCompactDate(segment.started_on)} - ${formatCompactDate(segment.ended_on)}`).join("\n") : null} /> : <div className="inspection-period-editor">
      {segments.map((segment, index) => <div className="inspection-team-edit-row" key={segment.ordinal}>
        <span>Lần {index + 1}</span><input aria-label={`Từ ngày lần ${index + 1}`} disabled={pending} onChange={(event) => setSegments((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, started_on: event.target.value } : item))} type="date" value={segment.started_on} />
        <input aria-label={`Đến ngày lần ${index + 1}`} disabled={pending} onChange={(event) => setSegments((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ended_on: event.target.value } : item))} type="date" value={segment.ended_on} />
        <button disabled={pending || index === 0} onClick={() => setSegments((current) => { const next=[...current]; [next[index - 1], next[index]]=[next[index], next[index - 1]]; return renumber(next); })} type="button">Lên</button>
        <button disabled={pending || index === segments.length - 1} onClick={() => setSegments((current) => { const next=[...current]; [next[index + 1], next[index]]=[next[index], next[index + 1]]; return renumber(next); })} type="button">Xuống</button>
        <button disabled={pending} onClick={() => setSegments((current) => renumber(current.filter((_, itemIndex) => itemIndex !== index)))} type="button">Xóa</button>
      </div>)}
      <div className="panel-actions"><button disabled={pending} onClick={() => setSegments((current) => [...current, { ordinal: current.length + 1, started_on: "", ended_on: "" }])} type="button">Thêm lần kiểm tra</button><button disabled={pending} onClick={() => void save()} type="button">Lưu các đợt kiểm tra</button><button disabled={pending} onClick={() => setEditing(false)} type="button">Hủy</button></div>
    </div>}
    {errorMessage ? <p className="form-error" role="alert">{errorMessage}</p> : null}
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
  const [draft, setDraft] = useState<InspectionPlanDraft>(currentDraft);
  const [editingField, setEditingField] = useState<"plan_start_on" | "plan_end_on" | "decision_reference" | "decision_date" | null>(null);
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!editingField) {
      setDraft(currentDraft);
      setErrorMessage(null);
    }
  }, [currentDraft, editingField]);

  async function saveField() {
    if (!editingField || pending) {
      return;
    }
    setPending(true);
    setErrorMessage(null);
    try {
      const value = editingField === "decision_reference"
        ? normalizeText(draft.decision_reference)
        : editingField === "decision_date"
          ? normalizeText(draft.decision_date)
          : normalizeText(draft[editingField]);
      await onSave({ expected_version: caseWorkspace.inspection.plan_row_version, [editingField]: value });
      setEditingField(null);
    } catch (error) {
      const nextError = error instanceof Error ? error : new Error("Không lưu được kế hoạch kiểm tra.");
      setErrorMessage(getSectionErrorMessage(nextError, "Kế hoạch kiểm tra"));
    } finally {
      setPending(false);
    }
  }

  function cancelEdit() {
    setDraft(currentDraft);
    setErrorMessage(null);
    setEditingField(null);
  }

  return (
    <section className="workspace-section inspection-plan-section">
      <h4>Kế hoạch kiểm tra</h4>
      <div className="detail-grid compact-grid detail-form-matrix">
        <EditableDetailValue
          editButtonLabel="Sửa Từ ngày kế hoạch"
          error={editingField === "plan_start_on" ? errorMessage : null}
          isEditing={editingField === "plan_start_on"}
          label="Từ ngày"
          onCancel={cancelEdit}
          onEdit={() => {
            setEditingField("plan_start_on");
            setErrorMessage(null);
          }}
          onSave={() => void saveField()}
          pending={pending}
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
          editButtonLabel="Sửa Số/Tham chiếu QĐKT"
          error={editingField === "decision_reference" ? errorMessage : null}
          isEditing={editingField === "decision_reference"}
          label="Số/Tham chiếu QĐKT"
          onCancel={cancelEdit}
          onEdit={() => { setEditingField("decision_reference"); setErrorMessage(null); }}
          onSave={() => void saveField()}
          pending={pending}
          value={caseWorkspace.inspection.plan_decision_reference}
        >
          <input aria-label="Số/Tham chiếu QĐKT" disabled={pending} onChange={(event) => setDraft((current) => ({ ...current, decision_reference: event.target.value }))} value={draft.decision_reference} />
        </EditableDetailValue>
        <EditableDetailValue
          editButtonLabel="Sửa Ngày QĐKT"
          error={editingField === "decision_date" ? errorMessage : null}
          isEditing={editingField === "decision_date"}
          label="Ngày QĐKT"
          onCancel={cancelEdit}
          onEdit={() => { setEditingField("decision_date"); setErrorMessage(null); }}
          onSave={() => void saveField()}
          pending={pending}
          value={formatCompactDate(caseWorkspace.inspection.plan_decision_date)}
        >
          <input aria-label="Ngày QĐKT" disabled={pending} onChange={(event) => setDraft((current) => ({ ...current, decision_date: event.target.value }))} type="date" value={draft.decision_date} />
        </EditableDetailValue>
        <DetailValue label="Gợi ý tài liệu legacy (chỉ đọc)" value={caseWorkspace.inspection.decision_document_hint} />

        <EditableDetailValue
          editButtonLabel="Sửa Đến ngày kế hoạch"
          error={editingField === "plan_end_on" ? errorMessage : null}
          isEditing={editingField === "plan_end_on"}
          label="Đến ngày"
          onCancel={cancelEdit}
          onEdit={() => {
            setEditingField("plan_end_on");
            setErrorMessage(null);
          }}
          onSave={() => void saveField()}
          pending={pending}
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
  const [editing, setEditing] = useState(false);
  const [options, setOptions] = useState<InspectionTeamIdentityOption[]>([]);
  const [members, setMembers] = useState<InspectionTeamUpsertRequest["members"]>([]);
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!editing) {
      setMembers((team?.members ?? []).map((member) => ({
        inspector_profile_id: member.inspector_profile_id,
        person_id: member.person_id,
        participant_catalog_id: member.participant_catalog_id,
        identity_kind: member.identity_kind === "ORGANIZATION_REPRESENTATIVE" ? "ORGANIZATION_REPRESENTATIVE" : member.inspector_profile_id ? "INSPECTOR_PROFILE" : null,
        role_code: member.sort_order === 1 ? "LEADER" : member.sort_order === 2 ? "SECRETARY" : "MEMBER",
        sort_order: member.sort_order,
      })));
    }
  }, [editing, team]);

  async function startEdit() {
    if (!readiness.available || pending) return;
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
    setPending(true);
    setErrorMessage(null);
    try {
      await onSave({
        expected_version: readiness.expected_version,
        members: members.map((member, index) => ({
          ...member,
          sort_order: index + 1,
          role_code: index === 0 ? "LEADER" : index === 1 ? "SECRETARY" : "MEMBER",
        })),
      });
      setEditing(false);
    } catch (error) {
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
      setPending(false);
    }
  }

  return (
    <section className="workspace-section inspection-team-section">
      <div className="workspace-section-heading"><h4>Đoàn kiểm tra</h4><button disabled={!readiness.available || pending} onClick={() => void startEdit()} type="button">{readiness.label}</button></div>
      <div className="detail-grid compact-grid detail-form-matrix">
        <DetailValue label="Mô tả legacy" multiline value={caseWorkspace.inspection.team_display_text} />
      </div>
      {team?.members.map((member) => <div className="inspection-team-member" key={member.id}>
        <strong>{member.display_name ?? "Định danh chưa resolve"}</strong><span>{member.role_code ?? member.role_label ?? "Chưa có vai trò"}</span>
        {member.identity_status === "unresolved" ? <span className="form-error">Không thể round-trip định danh này.</span> : null}
      </div>)}
      {!readiness.available && readiness.reason_code ? <p className="workspace-note">Không thể chỉnh sửa: {readiness.reason_code}.</p> : null}
      {errorMessage ? <p className="form-error" role="alert">{errorMessage}</p> : null}
      {editing ? <div className="inspection-team-editor">
        <p className="workspace-note">Lưu sẽ thay toàn bộ danh sách từ dữ liệu có cấu trúc này. Mô tả legacy chỉ đọc, không được dùng để tạo thành viên.</p>
        {members.map((member, index) => <div className="inspection-team-edit-row" key={`${identityValue(member)}-${index}`}>
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
          <button disabled={pending || members.length === 0 || members.some((member) => !identityValue(member))} onClick={() => void save()} type="button">{pending ? "Đang lưu..." : "Lưu đoàn kiểm tra"}</button>
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
  const [draft, setDraft] = useState<InspectionOutcomeDraft>(currentDraft);
  const [editingField, setEditingField] = useState<
    "outcome_result" | "minutes_recorded_on" | "minutes_recorded_time" | "compliance_due_on" | null
  >(null);
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!editingField) {
      setDraft(currentDraft);
      setErrorMessage(null);
    }
  }, [currentDraft, editingField]);

  async function saveField() {
    if (!editingField || pending) {
      return;
    }
    setPending(true);
    setErrorMessage(null);
    try {
      await onSave({ expected_version: caseWorkspace.inspection.outcome_row_version, [editingField]: normalizeText(draft[editingField]) });
      setEditingField(null);
    } catch (error) {
      const nextError = error instanceof Error ? error : new Error("Không lưu được kết quả kiểm tra.");
      setErrorMessage(getSectionErrorMessage(nextError, "kết quả kiểm tra"));
    } finally {
      setPending(false);
    }
  }

  function cancelEdit() {
    setDraft(currentDraft);
    setErrorMessage(null);
    setEditingField(null);
  }

  return (
    <section className="workspace-section inspection-outcome-section">
      <h4>Thực hiện & kết quả</h4>
      <div className="detail-grid compact-grid detail-form-matrix">
        <DetailValue label="QĐKT legacy (chỉ đọc)" value={caseWorkspace.inspection.outcome_decision_reference_compatibility} />
        <DetailValue label="Biên bản legacy (chỉ đọc)" value={caseWorkspace.inspection.bbkt_reference} />

        <DetailValue label="Thời điểm thực hiện" value={formatCompactDate(caseWorkspace.inspection.executed_on)} />
        <DetailValue label="Tiêu chuẩn áp dụng" value={caseWorkspace.case_summary.applicable_standard} />

        <EditableDetailValue
          editButtonLabel="Sửa Kết quả kiểm tra"
          error={editingField === "outcome_result" ? errorMessage : null}
          isEditing={editingField === "outcome_result"}
          label="Kết quả kiểm tra"
          multiline
          onCancel={cancelEdit}
          onEdit={() => {
            setEditingField("outcome_result");
            setErrorMessage(null);
          }}
          onSave={() => void saveField()}
          pending={pending}
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
        <EditableDetailValue editButtonLabel="Sửa Ngày biên bản" error={editingField === "minutes_recorded_on" ? errorMessage : null} isEditing={editingField === "minutes_recorded_on"} label="Ngày biên bản/report" onCancel={cancelEdit} onEdit={() => { setEditingField("minutes_recorded_on"); setErrorMessage(null); }} onSave={() => void saveField()} pending={pending} value={formatCompactDate(caseWorkspace.inspection.minutes_recorded_on)}>
          <input aria-label="Ngày biên bản/report" disabled={pending} onChange={(event) => setDraft((current) => ({ ...current, minutes_recorded_on: event.target.value }))} type="date" value={draft.minutes_recorded_on} />
        </EditableDetailValue>
        <EditableDetailValue editButtonLabel="Sửa Giờ biên bản" error={editingField === "minutes_recorded_time" ? errorMessage : null} isEditing={editingField === "minutes_recorded_time"} label="Giờ biên bản/report" onCancel={cancelEdit} onEdit={() => { setEditingField("minutes_recorded_time"); setErrorMessage(null); }} onSave={() => void saveField()} pending={pending} value={caseWorkspace.inspection.minutes_recorded_time}>
          <input aria-label="Giờ biên bản/report" disabled={pending} onChange={(event) => setDraft((current) => ({ ...current, minutes_recorded_time: event.target.value }))} type="time" value={draft.minutes_recorded_time} />
        </EditableDetailValue>
        <EditableDetailValue editButtonLabel="Sửa Hạn tuân thủ" error={editingField === "compliance_due_on" ? errorMessage : null} isEditing={editingField === "compliance_due_on"} label="Hạn tuân thủ/tái kiểm tra" onCancel={cancelEdit} onEdit={() => { setEditingField("compliance_due_on"); setErrorMessage(null); }} onSave={() => void saveField()} pending={pending} value={formatCompactDate(caseWorkspace.inspection.compliance_due_on)}>
          <input aria-label="Hạn tuân thủ/tái kiểm tra" disabled={pending} onChange={(event) => setDraft((current) => ({ ...current, compliance_due_on: event.target.value }))} type="date" value={draft.compliance_due_on} />
        </EditableDetailValue>
      </div>
    </section>
  );
}

export function CaseInspectionWorkspace({
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
  const [finalEvaluation, setFinalEvaluation] = useState("");
  const [finalizationError, setFinalizationError] = useState<string | null>(null);
  const [finalizationPending, setFinalizationPending] = useState(false);
  const finalization = caseWorkspace.inspection.final_evaluation_readiness ?? {
    action_key: "finalize_inspection_outcome",
    label: "Chốt đánh giá cuối cùng",
    available: false,
    reason_code: "readiness_unavailable",
    required_permissions: [],
    expected_version: null,
  };

  async function finalize() {
    if (!onFinalizeInspectionOutcome || !finalization.available || !finalEvaluation.trim() || finalization.expected_version === null) return;
    setFinalizationPending(true);
    setFinalizationError(null);
    try {
      await onFinalizeInspectionOutcome({ expected_version: finalization.expected_version, final_evaluation: finalEvaluation.trim() });
      setFinalEvaluation("");
    } catch (error) {
      setFinalizationError(getSectionErrorMessage(error instanceof Error ? error : new Error("Không thể chốt đánh giá."), "đánh giá cuối cùng"));
    } finally {
      setFinalizationPending(false);
    }
  }
  return (
    <div className="inspection-workspace">
      <div className="inspection-detail-grid">
        <InspectionPlanSection caseWorkspace={caseWorkspace} onSave={onInspectionPlanSave} />
        <InspectionTeamSection caseWorkspace={caseWorkspace} onLoadIdentityOptions={onLoadInspectionTeamIdentityOptions} onSave={onInspectionTeamSave} />
        <InspectionOutcomeSection caseWorkspace={caseWorkspace} onSave={onInspectionOutcomeSave} />
        <InspectionPeriodSection caseWorkspace={caseWorkspace} onSave={onInspectionPeriodSegmentsSave} />
        <CaseApprovalWorkspace caseWorkspace={caseWorkspace} onComplete={onCompleteApprovalSubmission} onCreate={onCreateApprovalSubmission} />
        <CaseLifecycleActions caseWorkspace={caseWorkspace} onTransition={onTransitionCase} />
        <section className="workspace-section">
          <h4>Đánh giá cuối cùng</h4>
          <DetailValue label="Giá trị đã chốt" value={caseWorkspace.inspection.final_evaluation} />
          {caseWorkspace.inspection.final_evaluation === null ? (
            <div className="panel-actions panel-actions-tight">
              <input aria-label="Đánh giá cuối cùng" disabled={!finalization.available || finalizationPending} onChange={(event) => setFinalEvaluation(event.target.value)} value={finalEvaluation} />
              <button disabled={!onFinalizeInspectionOutcome || !finalization.available || finalizationPending || !finalEvaluation.trim()} onClick={() => void finalize()} type="button">
                {finalizationPending ? "Đang chốt..." : finalization.label}
              </button>
            </div>
          ) : null}
          {!finalization.available && finalization.reason_code ? <p className="workspace-note">Không thể chốt: {finalization.reason_code}.</p> : null}
          {finalizationError ? <p className="form-error" role="alert">{finalizationError}</p> : null}
        </section>
      </div>
    </div>
  );
}
