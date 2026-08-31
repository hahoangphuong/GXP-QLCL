import { useEffect, useMemo, useState } from "react";

import { formatCompactDate, formatStatusLabel } from "../../lib/presentation";
import type { CaseApplicationUpsertRequest, CaseWorkspace } from "../../types";
import { DetailValue } from "./DetailValue";

function toDateInputValue(value: string | null): string {
  if (!value) {
    return "";
  }
  const normalized = String(value).trim();
  if (!normalized) {
    return "";
  }
  const match = normalized.match(/^(\d{4}-\d{2}-\d{2})/);
  return match ? match[1] : "";
}

function toSubmittedOnPayload(value: string): string | null {
  const normalized = value.trim();
  return normalized ? `${normalized}T00:00:00Z` : null;
}

type FormDraft = {
  submitted_on: string;
  dossier_code: string;
  dossier_reference: string;
  applicant_name: string;
};

function buildDraft(caseWorkspace: CaseWorkspace): FormDraft {
  return {
    submitted_on: toDateInputValue(caseWorkspace.application.submitted_on),
    dossier_code: caseWorkspace.application.dossier_code ?? "",
    dossier_reference: caseWorkspace.application.dossier_reference ?? "",
    applicant_name: caseWorkspace.application.applicant_name ?? "",
  };
}

function normalizeText(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function getErrorStatus(error: Error): number | null {
  const status = (error as Error & { status?: unknown }).status;
  return typeof status === "number" ? status : null;
}

export function CaseApplicationWorkspace({
  caseWorkspace,
  onSave,
}: {
  caseWorkspace: CaseWorkspace;
  onSave: (payload: CaseApplicationUpsertRequest) => Promise<void>;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [draft, setDraft] = useState<FormDraft>(() => buildDraft(caseWorkspace));

  const currentDraft = useMemo(() => buildDraft(caseWorkspace), [caseWorkspace]);

  useEffect(() => {
    if (!isEditing) {
      setDraft(currentDraft);
      setErrorMessage(null);
    }
  }, [currentDraft, isEditing]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) {
      return;
    }
    setPending(true);
    setErrorMessage(null);
    try {
      await onSave({
        expected_version: caseWorkspace.application.row_version,
        submitted_on: toSubmittedOnPayload(draft.submitted_on),
        dossier_code: normalizeText(draft.dossier_code),
        dossier_reference: normalizeText(draft.dossier_reference),
        applicant_name: normalizeText(draft.applicant_name),
      });
      setIsEditing(false);
    } catch (error) {
      const nextError = error instanceof Error ? error : new Error("Không lưu được thông tin hồ sơ.");
      const status = getErrorStatus(nextError);
      if (status === 409) {
        setErrorMessage("Không thể lưu vì hồ sơ đã bị thay đổi hoặc đã ở trạng thái kết thúc. Tải lại workspace rồi thử lại.");
      } else if (status === 403) {
        setErrorMessage(`Bạn không có quyền cập nhật hồ sơ này. ${nextError.message}`);
      } else if (status === 422) {
        setErrorMessage(`Dữ liệu hồ sơ chưa hợp lệ. ${nextError.message}`);
      } else {
        setErrorMessage(nextError.message);
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="event-step-stack">
      <section className="workspace-section">
        <div className="workspace-section-header">
          <h4>Thông tin hồ sơ</h4>
          {!isEditing ? (
            <button className="secondary" onClick={() => setIsEditing(true)} type="button">
              Chỉnh sửa
            </button>
          ) : null}
        </div>
        {!isEditing ? (
          <div className="detail-grid compact-grid">
            <DetailValue label="Ngày nộp" value={formatCompactDate(caseWorkspace.application.submitted_on)} />
            <DetailValue label="Mã hồ sơ" value={caseWorkspace.application.dossier_code} />
            <DetailValue label="Tham chiếu hồ sơ" value={caseWorkspace.application.dossier_reference} />
            <DetailValue label="Người nộp hồ sơ" value={caseWorkspace.application.applicant_name} />
            <DetailValue label="Loại kiểm tra" value={caseWorkspace.case_summary.inspection_type} />
            <DetailValue label="GxP" value={caseWorkspace.case_summary.gxp_type} />
            <DetailValue label="Dây chuyền" value={caseWorkspace.case_summary.scope_code} />
            <DetailValue label="Tiêu chuẩn áp dụng" value={caseWorkspace.case_summary.applicable_standard} />
            <DetailValue label="Năm mở hồ sơ" value={String(caseWorkspace.case_summary.opened_year ?? "")} />
            <DetailValue label="Trạng thái hồ sơ" value={formatStatusLabel(caseWorkspace.case_summary.state)} />
          </div>
        ) : (
          <form className="case-application-form" onSubmit={handleSubmit}>
            <div className="detail-grid compact-grid case-application-form-grid">
              <label className="case-application-field">
                <span>Ngày nộp</span>
                <input
                  aria-label="Ngày nộp"
                  disabled={pending}
                  onChange={(event) => setDraft((current) => ({ ...current, submitted_on: event.target.value }))}
                  type="date"
                  value={draft.submitted_on}
                />
              </label>
              <label className="case-application-field">
                <span>Mã hồ sơ</span>
                <input
                  aria-label="Mã hồ sơ"
                  disabled={pending}
                  onChange={(event) => setDraft((current) => ({ ...current, dossier_code: event.target.value }))}
                  value={draft.dossier_code}
                />
              </label>
              <label className="case-application-field">
                <span>Tham chiếu hồ sơ</span>
                <input
                  aria-label="Tham chiếu hồ sơ"
                  disabled={pending}
                  onChange={(event) => setDraft((current) => ({ ...current, dossier_reference: event.target.value }))}
                  value={draft.dossier_reference}
                />
              </label>
              <label className="case-application-field">
                <span>Người nộp hồ sơ</span>
                <input
                  aria-label="Người nộp hồ sơ"
                  disabled={pending}
                  onChange={(event) => setDraft((current) => ({ ...current, applicant_name: event.target.value }))}
                  value={draft.applicant_name}
                />
              </label>
              <div className="case-application-readonly">
                <DetailValue label="Loại kiểm tra" value={caseWorkspace.case_summary.inspection_type} />
              </div>
              <div className="case-application-readonly">
                <DetailValue label="GxP" value={caseWorkspace.case_summary.gxp_type} />
              </div>
              <div className="case-application-readonly">
                <DetailValue label="Dây chuyền" value={caseWorkspace.case_summary.scope_code} />
              </div>
              <div className="case-application-readonly">
                <DetailValue label="Tiêu chuẩn áp dụng" value={caseWorkspace.case_summary.applicable_standard} />
              </div>
              <div className="case-application-readonly">
                <DetailValue label="Năm mở hồ sơ" value={String(caseWorkspace.case_summary.opened_year ?? "")} />
              </div>
              <div className="case-application-readonly">
                <DetailValue label="Trạng thái hồ sơ" value={formatStatusLabel(caseWorkspace.case_summary.state)} />
              </div>
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
                  setDraft(currentDraft);
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

      <section className="workspace-section">
        <h4>Đầu mối cơ sở</h4>
        <div className="detail-grid compact-grid">
          <DetailValue
            label={
              caseWorkspace.application.assigned_specialist_source === "company_master"
                ? "Chuyên viên phụ trách cơ sở"
                : "Chuyên viên phụ trách"
            }
            value={caseWorkspace.application.assigned_specialist}
          />
        </div>
      </section>
    </div>
  );
}
