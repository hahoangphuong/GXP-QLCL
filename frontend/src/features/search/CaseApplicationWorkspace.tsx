import { useEffect, useMemo, useState } from "react";

import { formatCompactDate, formatStatusLabel } from "../../lib/presentation";
import type { CaseApplicationUpsertRequest, CaseWorkspace } from "../../types";
import { EditableDetailValue } from "./EditableDetailValue";
import { DetailValue } from "./DetailValue";

function toDateInputValue(value: string | null): string {
  if (!value) {
    return "";
  }
  const normalized = String(value).trim();
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

function getErrorMessage(error: Error): string {
  const status = getErrorStatus(error);
  if (status === 409) {
    return "Không thể lưu vì hồ sơ đã bị thay đổi hoặc đã ở trạng thái kết thúc. Tải lại workspace rồi thử lại.";
  }
  if (status === 403) {
    return `Bạn không có quyền cập nhật hồ sơ này. ${error.message}`;
  }
  if (status === 422) {
    return `Dữ liệu hồ sơ chưa hợp lệ. ${error.message}`;
  }
  return error.message || "Không lưu được thông tin hồ sơ.";
}

export function CaseApplicationWorkspace({
  caseWorkspace,
  onSave,
}: {
  caseWorkspace: CaseWorkspace;
  onSave: (payload: CaseApplicationUpsertRequest) => Promise<void>;
}) {
  const currentDraft = useMemo(() => buildDraft(caseWorkspace), [caseWorkspace]);
  const [draft, setDraft] = useState<FormDraft>(currentDraft);
  const [editingField, setEditingField] = useState<"submitted_on" | "dossier_code" | null>(null);
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
        expected_version: caseWorkspace.application.row_version,
        submitted_on: toSubmittedOnPayload(draft.submitted_on),
        dossier_code: normalizeText(draft.dossier_code),
        dossier_reference: normalizeText(draft.dossier_reference),
        applicant_name: normalizeText(draft.applicant_name),
      });
      setEditingField(null);
    } catch (error) {
      const nextError = error instanceof Error ? error : new Error("Không lưu được thông tin hồ sơ.");
      setErrorMessage(getErrorMessage(nextError));
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
    <div className="event-step-stack">
      <section className="workspace-section">
        <h4>Thông tin hồ sơ</h4>
        <div className="detail-grid compact-grid">
          <EditableDetailValue
            editButtonLabel="Sửa Ngày nộp"
            error={editingField === "submitted_on" ? errorMessage : null}
            isEditing={editingField === "submitted_on"}
            label="Ngày nộp"
            onCancel={cancelEdit}
            onEdit={() => {
              setEditingField("submitted_on");
              setErrorMessage(null);
            }}
            onSave={() => void saveField()}
            pending={pending}
            value={formatCompactDate(caseWorkspace.application.submitted_on)}
          >
            <input
              aria-label="Ngày nộp"
              disabled={pending}
              onChange={(event) => setDraft((current) => ({ ...current, submitted_on: event.target.value }))}
              type="date"
              value={draft.submitted_on}
            />
          </EditableDetailValue>

          <EditableDetailValue
            editButtonLabel="Sửa Mã hồ sơ"
            error={editingField === "dossier_code" ? errorMessage : null}
            isEditing={editingField === "dossier_code"}
            label="Mã hồ sơ"
            onCancel={cancelEdit}
            onEdit={() => {
              setEditingField("dossier_code");
              setErrorMessage(null);
            }}
            onSave={() => void saveField()}
            pending={pending}
            value={caseWorkspace.application.dossier_code}
          >
            <input
              aria-label="Mã hồ sơ"
              disabled={pending}
              onChange={(event) => setDraft((current) => ({ ...current, dossier_code: event.target.value }))}
              value={draft.dossier_code}
            />
          </EditableDetailValue>

          <DetailValue label="Loại kiểm tra" value={caseWorkspace.case_summary.inspection_type} />
          <DetailValue label="GxP" value={caseWorkspace.case_summary.gxp_type} />
          <DetailValue label="Dây chuyền" value={caseWorkspace.case_summary.scope_code} />
          <DetailValue label="Tiêu chuẩn áp dụng" value={caseWorkspace.case_summary.applicable_standard} />
          <DetailValue label="Năm mở hồ sơ" value={String(caseWorkspace.case_summary.opened_year ?? "")} />
          <DetailValue label="Trạng thái hồ sơ" value={formatStatusLabel(caseWorkspace.case_summary.state)} />
        </div>
      </section>
    </div>
  );
}
