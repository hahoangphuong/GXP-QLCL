import { useEffect, useMemo, useState } from "react";

import { formatCompactDate } from "../../lib/presentation";
import type {
  CaseWorkspace,
  InspectionOutcomeUpsertRequest,
  InspectionPlanUpsertRequest,
  InspectionTeamIdentityOption,
  InspectionTeamUpsertRequest,
} from "../../types";
import { EditableDetailValue } from "./EditableDetailValue";
import { DetailValue } from "./DetailValue";

type InspectionPlanDraft = {
  plan_start_on: string;
  plan_end_on: string;
  planning_sheet_name: string;
  decision_document_hint: string;
};

type InspectionOutcomeDraft = {
  inspected_on: string;
  inspected_to_on: string;
  decision_reference: string;
  bbkt_reference: string;
  outcome_result: string;
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
    decision_document_hint: caseWorkspace.inspection.decision_document_hint ?? "",
  };
}

function buildOutcomeDraft(caseWorkspace: CaseWorkspace): InspectionOutcomeDraft {
  return {
    inspected_on: normalizeDateInputValue(caseWorkspace.inspection.inspected_on),
    inspected_to_on: normalizeDateInputValue(caseWorkspace.inspection.inspected_to_on),
    decision_reference: caseWorkspace.inspection.decision_reference ?? "",
    bbkt_reference: caseWorkspace.inspection.bbkt_reference ?? "",
    outcome_result: caseWorkspace.inspection.outcome_result ?? "",
  };
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
  const [editingField, setEditingField] = useState<"plan_start_on" | "plan_end_on" | null>(null);
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
      await onSave({
        expected_version: caseWorkspace.inspection.plan_row_version,
        plan_start_on: normalizeText(draft.plan_start_on),
        plan_end_on: normalizeText(draft.plan_end_on),
        planning_sheet_name: normalizeText(draft.planning_sheet_name),
        decision_document_hint: normalizeText(draft.decision_document_hint),
      });
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
        role_label: member.role_label,
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
    return "";
  }

  function setIdentity(index: number, value: string) {
    const [kind, id] = value.split(":", 2);
    setMembers((current) => current.map((member, memberIndex) => memberIndex !== index ? member : {
      ...member,
      inspector_profile_id: kind === "profile" && id ? id : null,
      person_id: kind === "person" && id ? id : null,
    }));
  }

  function moveMember(index: number, direction: -1 | 1) {
    setMembers((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next.map((member, sort_order) => ({ ...member, sort_order }));
    });
  }

  async function save() {
    if (pending || !team || members.length === 0 || members.some((member) => !identityValue(member))) return;
    setPending(true);
    setErrorMessage(null);
    try {
      await onSave({
        expected_version: team.row_version,
        members: members.map((member, sort_order) => ({ ...member, role_label: normalizeText(member.role_label ?? ""), sort_order })),
      });
      setEditing(false);
    } catch (error) {
      const nextError = error instanceof Error ? error : new Error("Không lưu được đoàn kiểm tra.");
      if (getErrorStatus(nextError) === 409) {
        setEditing(false);
        setMembers((team.members ?? []).map((member) => ({
          inspector_profile_id: member.inspector_profile_id,
          person_id: member.person_id,
          role_label: member.role_label,
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
        <strong>{member.display_name ?? "Định danh chưa resolve"}</strong><span>{member.role_label ?? "Chưa có vai trò"}</span>
        {member.identity_status === "unresolved" ? <span className="form-error">Không thể round-trip định danh này.</span> : null}
      </div>)}
      {!readiness.available && readiness.reason_code ? <p className="workspace-note">Không thể chỉnh sửa: {readiness.reason_code}.</p> : null}
      {errorMessage ? <p className="form-error" role="alert">{errorMessage}</p> : null}
      {editing ? <div className="inspection-team-editor">
        <p className="workspace-note">Lưu sẽ thay toàn bộ danh sách từ dữ liệu có cấu trúc này. Mô tả legacy chỉ đọc, không được dùng để tạo thành viên.</p>
        {members.map((member, index) => <div className="inspection-team-edit-row" key={`${identityValue(member)}-${index}`}>
          <select aria-label={`Định danh thành viên ${index + 1}`} disabled={pending} onChange={(event) => setIdentity(index, event.target.value)} value={identityValue(member)}>
            <option value="">Chọn định danh</option>
            {options.map((option) => <option key={`${option.identity_kind}:${option.inspector_profile_id ?? option.person_id}`} value={`${option.identity_kind === "inspector_profile" ? "profile" : "person"}:${option.inspector_profile_id ?? option.person_id}`}>
              {option.display_name}{option.is_active === false ? " (không hoạt động)" : ""}
            </option>)}
          </select>
          <input aria-label={`Vai trò thành viên ${index + 1}`} disabled={pending} onChange={(event) => setMembers((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, role_label: event.target.value } : item))} placeholder="Vai trò" value={member.role_label ?? ""} />
          <button aria-label={`Đưa thành viên ${index + 1} lên`} disabled={pending || index === 0} onClick={() => moveMember(index, -1)} type="button">Lên</button>
          <button aria-label={`Đưa thành viên ${index + 1} xuống`} disabled={pending || index === members.length - 1} onClick={() => moveMember(index, 1)} type="button">Xuống</button>
          <button aria-label={`Xóa thành viên ${index + 1}`} disabled={pending} onClick={() => setMembers((current) => current.filter((_, itemIndex) => itemIndex !== index).map((item, sort_order) => ({ ...item, sort_order })))} type="button">Xóa</button>
        </div>)}
        <div className="panel-actions">
          <button disabled={pending} onClick={() => setMembers((current) => [...current, { inspector_profile_id: null, person_id: null, role_label: null, sort_order: current.length }])} type="button">Thêm thành viên</button>
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
    "inspected_on" | "inspected_to_on" | "decision_reference" | "bbkt_reference" | "outcome_result" | null
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
      await onSave({
        expected_version: caseWorkspace.inspection.outcome_row_version,
        inspected_on: normalizeText(draft.inspected_on),
        inspected_to_on: normalizeText(draft.inspected_to_on),
        decision_reference: normalizeText(draft.decision_reference),
        bbkt_reference: normalizeText(draft.bbkt_reference),
        outcome_result: normalizeText(draft.outcome_result),
      });
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
        <EditableDetailValue
          editButtonLabel="Sửa Từ ngày kiểm tra"
          error={editingField === "inspected_on" ? errorMessage : null}
          isEditing={editingField === "inspected_on"}
          label="Từ ngày kiểm tra"
          onCancel={cancelEdit}
          onEdit={() => {
            setEditingField("inspected_on");
            setErrorMessage(null);
          }}
          onSave={() => void saveField()}
          pending={pending}
          value={formatCompactDate(caseWorkspace.inspection.inspected_on)}
        >
          <input
            aria-label="Từ ngày kiểm tra"
            disabled={pending}
            onChange={(event) => setDraft((current) => ({ ...current, inspected_on: event.target.value }))}
            type="date"
            value={draft.inspected_on}
          />
        </EditableDetailValue>

        <EditableDetailValue
          editButtonLabel="Sửa Đến ngày kiểm tra"
          error={editingField === "inspected_to_on" ? errorMessage : null}
          isEditing={editingField === "inspected_to_on"}
          label="Đến ngày kiểm tra"
          onCancel={cancelEdit}
          onEdit={() => {
            setEditingField("inspected_to_on");
            setErrorMessage(null);
          }}
          onSave={() => void saveField()}
          pending={pending}
          value={formatCompactDate(caseWorkspace.inspection.inspected_to_on)}
        >
          <input
            aria-label="Đến ngày kiểm tra"
            disabled={pending}
            onChange={(event) => setDraft((current) => ({ ...current, inspected_to_on: event.target.value }))}
            type="date"
            value={draft.inspected_to_on}
          />
        </EditableDetailValue>

        <EditableDetailValue
          editButtonLabel="Sửa Quyết định kiểm tra"
          error={editingField === "decision_reference" ? errorMessage : null}
          isEditing={editingField === "decision_reference"}
          label="Quyết định kiểm tra"
          onCancel={cancelEdit}
          onEdit={() => {
            setEditingField("decision_reference");
            setErrorMessage(null);
          }}
          onSave={() => void saveField()}
          pending={pending}
          value={caseWorkspace.inspection.decision_reference}
        >
          <input
            aria-label="Quyết định kiểm tra"
            disabled={pending}
            onChange={(event) => setDraft((current) => ({ ...current, decision_reference: event.target.value }))}
            value={draft.decision_reference}
          />
        </EditableDetailValue>

        <EditableDetailValue
          editButtonLabel="Sửa Biên bản kiểm tra"
          error={editingField === "bbkt_reference" ? errorMessage : null}
          isEditing={editingField === "bbkt_reference"}
          label="Biên bản kiểm tra"
          onCancel={cancelEdit}
          onEdit={() => {
            setEditingField("bbkt_reference");
            setErrorMessage(null);
          }}
          onSave={() => void saveField()}
          pending={pending}
          value={caseWorkspace.inspection.bbkt_reference}
        >
          <input
            aria-label="Biên bản kiểm tra"
            disabled={pending}
            onChange={(event) => setDraft((current) => ({ ...current, bbkt_reference: event.target.value }))}
            value={draft.bbkt_reference}
          />
        </EditableDetailValue>

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
      </div>
    </section>
  );
}

export function CaseInspectionWorkspace({
  caseWorkspace,
  onInspectionPlanSave,
  onInspectionOutcomeSave,
  onInspectionTeamSave,
  onLoadInspectionTeamIdentityOptions,
}: {
  caseWorkspace: CaseWorkspace;
  onInspectionPlanSave: (payload: InspectionPlanUpsertRequest) => Promise<void>;
  onInspectionOutcomeSave: (payload: InspectionOutcomeUpsertRequest) => Promise<void>;
  onInspectionTeamSave: (payload: InspectionTeamUpsertRequest) => Promise<void>;
  onLoadInspectionTeamIdentityOptions: () => Promise<InspectionTeamIdentityOption[]>;
}) {
  return (
    <div className="inspection-workspace">
      <div className="inspection-detail-grid">
        <InspectionPlanSection caseWorkspace={caseWorkspace} onSave={onInspectionPlanSave} />
        <InspectionTeamSection caseWorkspace={caseWorkspace} onLoadIdentityOptions={onLoadInspectionTeamIdentityOptions} onSave={onInspectionTeamSave} />
        <InspectionOutcomeSection caseWorkspace={caseWorkspace} onSave={onInspectionOutcomeSave} />
      </div>
    </div>
  );
}
