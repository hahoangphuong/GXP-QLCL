import { useEffect, useMemo, useState } from "react";

import { formatCompactDate } from "../../lib/presentation";
import type { CaseWorkspace, EvaluationScopeUpsertRequest, InspectionOutcomeUpsertRequest, InspectionPlanUpsertRequest } from "../../types";
import { EditableDetailValue } from "./EditableDetailValue";
import { DetailValue } from "./DetailValue";
import { EvaluationScopeWorkspace } from "./EvaluationScopeWorkspace";

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
    <section className="workspace-section">
      <h4>Kế hoạch kiểm tra</h4>
      <div className="detail-grid compact-grid">
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
}: {
  caseWorkspace: CaseWorkspace;
}) {
  return (
    <section className="workspace-section">
      <h4>Đoàn kiểm tra</h4>
      <div className="detail-grid compact-grid">
        <DetailValue label="Mô tả đoàn kiểm tra" multiline value={caseWorkspace.inspection.team_display_text} />
      </div>
      <p className="workspace-note">
        Section này đang giữ read-only vì canonical write owner yêu cầu `members[]` đầy đủ, trong khi workspace hiện chỉ có
        `display_text`. Mở edit lúc này có thể ghi đè mất cấu trúc thành viên lịch sử.
      </p>
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
    <section className="workspace-section">
      <h4>Thực hiện & kết quả</h4>
      <div className="detail-grid compact-grid">
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
  onEvaluationScopeSave,
}: {
  caseWorkspace: CaseWorkspace;
  onInspectionPlanSave: (payload: InspectionPlanUpsertRequest) => Promise<void>;
  onInspectionOutcomeSave: (payload: InspectionOutcomeUpsertRequest) => Promise<void>;
  onEvaluationScopeSave: (payload: EvaluationScopeUpsertRequest) => Promise<void>;
}) {
  return (
    <div className="event-step-stack">
      <InspectionPlanSection caseWorkspace={caseWorkspace} onSave={onInspectionPlanSave} />
      <InspectionTeamSection caseWorkspace={caseWorkspace} />
      <InspectionOutcomeSection caseWorkspace={caseWorkspace} onSave={onInspectionOutcomeSave} />
      <EvaluationScopeWorkspace caseWorkspace={caseWorkspace} onSave={onEvaluationScopeSave} />
    </div>
  );
}
