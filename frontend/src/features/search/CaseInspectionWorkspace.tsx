import { useEffect, useState, type FormEvent } from "react";

import { formatCompactDate } from "../../lib/presentation";
import type { CaseWorkspace, InspectionOutcomeUpsertRequest, InspectionPlanUpsertRequest } from "../../types";
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

function InspectionPlanEditor({
  caseWorkspace,
  onSave,
}: {
  caseWorkspace: CaseWorkspace;
  onSave: (payload: InspectionPlanUpsertRequest) => Promise<void>;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [draft, setDraft] = useState<InspectionPlanDraft>(() => buildPlanDraft(caseWorkspace));

  useEffect(() => {
    if (!isEditing) {
      setDraft(buildPlanDraft(caseWorkspace));
      setErrorMessage(null);
    }
  }, [caseWorkspace, isEditing]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) {
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
      setIsEditing(false);
    } catch (error) {
      const nextError = error instanceof Error ? error : new Error("Không lưu được kế hoạch kiểm tra.");
      setErrorMessage(getSectionErrorMessage(nextError, "Kế hoạch / quyết định"));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="workspace-section">
      <div className="workspace-section-header">
        <h4>Kế hoạch / quyết định</h4>
        {!isEditing ? (
          <button className="secondary" onClick={() => setIsEditing(true)} type="button">
            Chỉnh sửa
          </button>
        ) : null}
      </div>
      {!isEditing ? (
        <div className="detail-grid compact-grid">
          <DetailValue label="Từ ngày" value={formatCompactDate(caseWorkspace.inspection.plan_start_on)} />
          <DetailValue label="Đến ngày" value={formatCompactDate(caseWorkspace.inspection.plan_end_on)} />
          <DetailValue label="Tên kế hoạch" value={caseWorkspace.inspection.planning_sheet_name} />
          <DetailValue label="Gợi ý tài liệu quyết định" value={caseWorkspace.inspection.decision_document_hint} />
        </div>
      ) : (
        <form className="case-application-form" onSubmit={handleSubmit}>
          <div className="detail-grid compact-grid case-application-form-grid">
            <label className="case-application-field">
              <span>Từ ngày</span>
              <input
                aria-label="Từ ngày kế hoạch"
                disabled={pending}
                onChange={(event) => setDraft((current) => ({ ...current, plan_start_on: event.target.value }))}
                type="date"
                value={draft.plan_start_on}
              />
            </label>
            <label className="case-application-field">
              <span>Đến ngày</span>
              <input
                aria-label="Đến ngày kế hoạch"
                disabled={pending}
                onChange={(event) => setDraft((current) => ({ ...current, plan_end_on: event.target.value }))}
                type="date"
                value={draft.plan_end_on}
              />
            </label>
            <label className="case-application-field">
              <span>Tên kế hoạch</span>
              <input
                aria-label="Tên kế hoạch"
                disabled={pending}
                onChange={(event) => setDraft((current) => ({ ...current, planning_sheet_name: event.target.value }))}
                value={draft.planning_sheet_name}
              />
            </label>
            <label className="case-application-field">
              <span>Gợi ý tài liệu quyết định</span>
              <input
                aria-label="Gợi ý tài liệu quyết định"
                disabled={pending}
                onChange={(event) => setDraft((current) => ({ ...current, decision_document_hint: event.target.value }))}
                value={draft.decision_document_hint}
              />
            </label>
          </div>
          {errorMessage ? (
            <p className="form-error" role="alert">
              {errorMessage}
            </p>
          ) : null}
          <div className="panel-actions panel-actions-tight">
            <button disabled={pending} type="submit">
              {pending ? "Đang lưu..." : "Lưu"}
            </button>
            <button
              className="secondary"
              disabled={pending}
              onClick={() => {
                setDraft(buildPlanDraft(caseWorkspace));
                setErrorMessage(null);
                setIsEditing(false);
              }}
              type="button"
            >
              Hủy
            </button>
          </div>
        </form>
      )}
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
      <div className="workspace-section-header">
        <h4>Đoàn kiểm tra</h4>
      </div>
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

function InspectionOutcomeEditor({
  caseWorkspace,
  onSave,
}: {
  caseWorkspace: CaseWorkspace;
  onSave: (payload: InspectionOutcomeUpsertRequest) => Promise<void>;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [draft, setDraft] = useState<InspectionOutcomeDraft>(() => buildOutcomeDraft(caseWorkspace));

  useEffect(() => {
    if (!isEditing) {
      setDraft(buildOutcomeDraft(caseWorkspace));
      setErrorMessage(null);
    }
  }, [caseWorkspace, isEditing]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) {
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
      setIsEditing(false);
    } catch (error) {
      const nextError = error instanceof Error ? error : new Error("Không lưu được kết quả kiểm tra.");
      setErrorMessage(getSectionErrorMessage(nextError, "Thực hiện & kết quả"));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="workspace-section">
      <div className="workspace-section-header">
        <h4>Thực hiện & kết quả</h4>
        {!isEditing ? (
          <button className="secondary" onClick={() => setIsEditing(true)} type="button">
            Chỉnh sửa
          </button>
        ) : null}
      </div>
      {!isEditing ? (
        <div className="detail-grid compact-grid">
          <DetailValue label="Từ ngày kiểm tra" value={formatCompactDate(caseWorkspace.inspection.inspected_on)} />
          <DetailValue label="Đến ngày kiểm tra" value={formatCompactDate(caseWorkspace.inspection.inspected_to_on)} />
          <DetailValue label="Quyết định kiểm tra" value={caseWorkspace.inspection.decision_reference} />
          <DetailValue label="Biên bản kiểm tra" value={caseWorkspace.inspection.bbkt_reference} />
          <DetailValue label="Thời điểm thực hiện" value={formatCompactDate(caseWorkspace.inspection.executed_on)} />
          <DetailValue label="Kết quả kiểm tra" multiline value={caseWorkspace.inspection.outcome_result} />
        </div>
      ) : (
        <form className="case-application-form" onSubmit={handleSubmit}>
          <div className="detail-grid compact-grid case-application-form-grid">
            <label className="case-application-field">
              <span>Từ ngày kiểm tra</span>
              <input
                aria-label="Từ ngày kiểm tra"
                disabled={pending}
                onChange={(event) => setDraft((current) => ({ ...current, inspected_on: event.target.value }))}
                type="date"
                value={draft.inspected_on}
              />
            </label>
            <label className="case-application-field">
              <span>Đến ngày kiểm tra</span>
              <input
                aria-label="Đến ngày kiểm tra"
                disabled={pending}
                onChange={(event) => setDraft((current) => ({ ...current, inspected_to_on: event.target.value }))}
                type="date"
                value={draft.inspected_to_on}
              />
            </label>
            <label className="case-application-field">
              <span>Quyết định kiểm tra</span>
              <input
                aria-label="Quyết định kiểm tra"
                disabled={pending}
                onChange={(event) => setDraft((current) => ({ ...current, decision_reference: event.target.value }))}
                value={draft.decision_reference}
              />
            </label>
            <label className="case-application-field">
              <span>Biên bản kiểm tra</span>
              <input
                aria-label="Biên bản kiểm tra"
                disabled={pending}
                onChange={(event) => setDraft((current) => ({ ...current, bbkt_reference: event.target.value }))}
                value={draft.bbkt_reference}
              />
            </label>
            <div className="case-application-readonly">
              <DetailValue label="Thời điểm thực hiện" value={formatCompactDate(caseWorkspace.inspection.executed_on)} />
            </div>
            <label className="case-application-field case-application-field-full">
              <span>Kết quả kiểm tra</span>
              <textarea
                aria-label="Kết quả kiểm tra"
                className="inspection-textarea"
                disabled={pending}
                onChange={(event) => setDraft((current) => ({ ...current, outcome_result: event.target.value }))}
                rows={4}
                value={draft.outcome_result}
              />
            </label>
          </div>
          {errorMessage ? (
            <p className="form-error" role="alert">
              {errorMessage}
            </p>
          ) : null}
          <div className="panel-actions panel-actions-tight">
            <button disabled={pending} type="submit">
              {pending ? "Đang lưu..." : "Lưu"}
            </button>
            <button
              className="secondary"
              disabled={pending}
              onClick={() => {
                setDraft(buildOutcomeDraft(caseWorkspace));
                setErrorMessage(null);
                setIsEditing(false);
              }}
              type="button"
            >
              Hủy
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

export function CaseInspectionWorkspace({
  caseWorkspace,
  onInspectionPlanSave,
  onInspectionOutcomeSave,
}: {
  caseWorkspace: CaseWorkspace;
  onInspectionPlanSave: (payload: InspectionPlanUpsertRequest) => Promise<void>;
  onInspectionOutcomeSave: (payload: InspectionOutcomeUpsertRequest) => Promise<void>;
}) {
  return (
    <div className="event-step-stack">
      <InspectionPlanEditor caseWorkspace={caseWorkspace} onSave={onInspectionPlanSave} />
      <InspectionTeamSection caseWorkspace={caseWorkspace} />
      <InspectionOutcomeEditor caseWorkspace={caseWorkspace} onSave={onInspectionOutcomeSave} />
    </div>
  );
}
