import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "../../components/EmptyState";
import { formatCompactDate } from "../../lib/presentation";
import type { CaseAssessmentUpsertRequest, CaseWorkspace } from "../../types";
import { EditableDetailValue } from "./EditableDetailValue";

type ProcessingDraft = {
  assessed_on: string;
  assessor_name: string;
  assessment_result: string;
  notes: string;
};

function normalizeDateInputValue(value: string | null): string {
  const normalized = String(value ?? "").trim();
  const match = normalized.match(/^(\d{4}-\d{2}-\d{2})/);
  return match ? match[1] : "";
}

function toDateTimePayload(value: string): string | null {
  const normalized = value.trim();
  return normalized ? `${normalized}T00:00:00Z` : null;
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
    return "Không thể lưu vì bước xử lý đã bị thay đổi hoặc hồ sơ đã ở trạng thái kết thúc. Tải lại workspace rồi thử lại.";
  }
  if (status === 403) {
    return `Bạn không có quyền cập nhật bước xử lý này. ${error.message}`;
  }
  if (status === 422) {
    return `Dữ liệu xử lý chưa hợp lệ. ${error.message}`;
  }
  return error.message || "Không lưu được bước xử lý.";
}

function buildDraft(caseWorkspace: CaseWorkspace): ProcessingDraft {
  return {
    assessed_on: normalizeDateInputValue(caseWorkspace.processing.assessed_on),
    assessor_name: caseWorkspace.processing.assessor_name ?? "",
    assessment_result: caseWorkspace.processing.assessment_result ?? "",
    notes: caseWorkspace.processing.notes ?? "",
  };
}

const PROCESSING_EVENT_LABELS: Record<string, string> = {
  application_submitted: "Tiếp nhận hồ sơ",
  assessment_completed: "Thẩm định hoàn tất",
  plan_created: "Lập kế hoạch",
  decision_issued: "Ban hành quyết định",
  inspection_executed: "Thực hiện kiểm tra",
  outcome_recorded: "Ghi nhận kết quả",
  certificate_issued: "Cấp chứng nhận",
};

export function CaseProcessingWorkspace({
  caseWorkspace,
  onSave,
}: {
  caseWorkspace: CaseWorkspace;
  onSave: (payload: CaseAssessmentUpsertRequest) => Promise<void>;
}) {
  const currentDraft = useMemo(() => buildDraft(caseWorkspace), [caseWorkspace]);
  const [draft, setDraft] = useState<ProcessingDraft>(currentDraft);
  const [editingField, setEditingField] = useState<keyof ProcessingDraft | null>(null);
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
        expected_version: caseWorkspace.processing.row_version,
        assessed_on: toDateTimePayload(draft.assessed_on),
        assessor_name: normalizeText(draft.assessor_name),
        assessment_result: normalizeText(draft.assessment_result),
        notes: normalizeText(draft.notes),
      });
      setEditingField(null);
    } catch (error) {
      const nextError = error instanceof Error ? error : new Error("Không lưu được bước xử lý.");
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
        <h4>Thông tin xử lý</h4>
        <div className="detail-grid compact-grid">
          <EditableDetailValue
            editButtonLabel="Sửa Ngày thẩm định"
            error={editingField === "assessed_on" ? errorMessage : null}
            isEditing={editingField === "assessed_on"}
            label="Ngày thẩm định"
            onCancel={cancelEdit}
            onEdit={() => {
              setEditingField("assessed_on");
              setErrorMessage(null);
            }}
            onSave={() => void saveField()}
            pending={pending}
            value={formatCompactDate(caseWorkspace.processing.assessed_on)}
          >
            <input
              aria-label="Ngày thẩm định"
              disabled={pending}
              onChange={(event) => setDraft((current) => ({ ...current, assessed_on: event.target.value }))}
              type="date"
              value={draft.assessed_on}
            />
          </EditableDetailValue>

          <EditableDetailValue
            editButtonLabel="Sửa Người thẩm định"
            error={editingField === "assessor_name" ? errorMessage : null}
            isEditing={editingField === "assessor_name"}
            label="Người thẩm định"
            onCancel={cancelEdit}
            onEdit={() => {
              setEditingField("assessor_name");
              setErrorMessage(null);
            }}
            onSave={() => void saveField()}
            pending={pending}
            value={caseWorkspace.processing.assessor_name}
          >
            <input
              aria-label="Người thẩm định"
              disabled={pending}
              onChange={(event) => setDraft((current) => ({ ...current, assessor_name: event.target.value }))}
              value={draft.assessor_name}
            />
          </EditableDetailValue>

          <EditableDetailValue
            editButtonLabel="Sửa Kết quả"
            error={editingField === "assessment_result" ? errorMessage : null}
            isEditing={editingField === "assessment_result"}
            label="Kết quả"
            multiline
            onCancel={cancelEdit}
            onEdit={() => {
              setEditingField("assessment_result");
              setErrorMessage(null);
            }}
            onSave={() => void saveField()}
            pending={pending}
            value={caseWorkspace.processing.assessment_result}
          >
            <textarea
              aria-label="Kết quả"
              className="inspection-textarea"
              disabled={pending}
              onChange={(event) => setDraft((current) => ({ ...current, assessment_result: event.target.value }))}
              rows={4}
              value={draft.assessment_result}
            />
          </EditableDetailValue>
        </div>
      </section>

      <section className="workspace-section">
        <h4>Các mốc xử lý hành chính</h4>
        {caseWorkspace.processing.events.length > 0 ? (
          <div className="table-scroll table-scroll-history">
            <table className="dense-table event-milestone-table">
              <thead>
                <tr>
                  <th>Mốc</th>
                  <th>Ngày</th>
                  <th>Nội dung</th>
                </tr>
              </thead>
              <tbody>
                {caseWorkspace.processing.events.map((event, index) => (
                  <tr key={`${event.event_type}:${event.occurred_at ?? "none"}:${index}`}>
                    <td>{PROCESSING_EVENT_LABELS[event.event_type] ?? event.event_type}</td>
                    <td>{formatCompactDate(event.occurred_at)}</td>
                    <td>{event.payload ?? "Chưa có"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="Chưa có mốc xử lý" description="Chưa có inspection event canonical nào cho bước xử lý của hồ sơ này." />
        )}
      </section>
    </div>
  );
}
