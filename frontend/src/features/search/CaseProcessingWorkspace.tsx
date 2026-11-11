import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";
import { useCaseCommandLock, useCaseDraftState } from "./CaseDraftSession";
import { useEffect, useMemo } from "react";

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

type AssessmentReview = {
  draft: ProcessingDraft;
  editingField: keyof ProcessingDraft;
  draftVersion: number | null;
  errorMessage: string;
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

// Present known canonical inspection events without hiding their original evidence.
// Unknown/legacy formats remain unchanged rather than being interpreted as new truth.
const TIMELINE_FIELDS: Record<string, { stage: string; fields: Array<[string, string, boolean?]> }> = {
  plan_created: { stage: "inspection_plan", fields: [
    ["planning_sheet_name", "Tên kế hoạch"], ["plan_start_on", "Từ ngày", true],
    ["plan_end_on", "Đến ngày", true], ["decision_reference", "Tham chiếu QĐKT"],
    ["decision_date", "Ngày QĐKT", true], ["reason", "Lý do"],
  ] },
  decision_issued: { stage: "inspection_decision", fields: [
    ["decision_reference", "Tham chiếu QĐKT"], ["decision_date", "Ngày QĐKT", true],
    ["reason", "Lý do"],
  ] },
  outcome_recorded: { stage: "inspection_outcome", fields: [
    ["inspected_on", "Từ ngày kiểm tra", true], ["inspected_to_on", "Đến ngày kiểm tra", true],
    ["outcome_result", "Kết quả"], ["minutes_recorded_on", "Ngày biên bản", true],
    ["minutes_recorded_time", "Giờ biên bản"], ["compliance_due_on", "Hạn tuân thủ", true],
    ["reason", "Lý do"],
  ] },
};

function InspectionTimelinePayload({ eventType, payload }: { eventType: string; payload: string | null }) {
  const config = TIMELINE_FIELDS[eventType];
  if (!payload || !config) return <>{payload ?? "Chưa có"}</>;
  let parsed: unknown;
  try { parsed = JSON.parse(payload); } catch { return <>{payload}</>; }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return <>{payload}</>;
  const record = parsed as Record<string, unknown>;
  if (record.stage !== config.stage) return <>{payload}</>;
  const summary = config.fields.flatMap(([key, label, isDate]) => {
    const value = record[key];
    if (typeof value !== "string" || !value.trim()) return [];
    return [`${label}: ${isDate ? formatCompactDate(value) : value}`];
  });
  if (summary.length === 0) return <>{payload}</>;
  return <>
    <span>{summary.join(" · ")}</span>
    <details>
      <summary>Dữ liệu sự kiện gốc</summary>
      <code style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{payload}</code>
    </details>
  </>;
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

// Operators can narrow a long canonical Case event history without changing
// its order, raw evidence or the separately owned assessment editor.
function CaseEventTimeline({ caseWorkspace, view }: {
  caseWorkspace: CaseWorkspace;
  view?: "assessment" | "timeline";
}) {
  const events = caseWorkspace.processing.events;
  const caseId = caseWorkspace.case_summary.id;
  const [eventType, setEventType] = useCaseDraftState(`timeline.${caseId}.eventType`, "all");
  const [search, setSearch] = useCaseDraftState(`timeline.${caseId}.search`, "");
  const types = [...new Set(events.map(event => event.event_type))];
  // A refreshed Case may no longer contain the previously selected kind.
  // Treat it as an empty filter result, never infer events from old data.
  const normalized = search.trim().toLocaleLowerCase();
  const visibleEvents = events.map((event, originalIndex) => ({ event, originalIndex })).filter(({ event }) => {
    if (eventType !== "all" && event.event_type !== eventType) return false;
    if (!normalized) return true;
    return [
      event.event_type,
      PROCESSING_EVENT_LABELS[event.event_type] ?? "",
      event.occurred_at ?? "",
      formatCompactDate(event.occurred_at),
      event.payload ?? "",
    ].some(value => value.toLocaleLowerCase().includes(normalized));
  });
  return <section className={`workspace-section${view === "timeline" ? " processing-timeline-section" : ""}`}>
    <h4>Các mốc xử lý hành chính</h4>
    {events.length > 0 ? <>
      <div className="panel-actions" role="group" aria-label="Tra cứu mốc xử lý hành chính">
        <label>Loại mốc
          <select aria-label="Loại mốc xử lý" value={eventType}
            onChange={event => setEventType(event.target.value)}>
            <option value="all">Tất cả loại mốc</option>
            {types.map(type => <option key={type} value={type}>{PROCESSING_EVENT_LABELS[type] ?? type}</option>)}
            {!types.includes(eventType) && eventType !== "all" ? <option value={eventType}>{eventType} (không còn trong dữ liệu)</option> : null}
          </select>
        </label>
        <label>Tìm trong mốc
          <input aria-label="Tìm mốc xử lý" value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder="Loại mốc, ngày, nội dung…" />
        </label>
        {(eventType !== "all" || search) ? <button className="secondary" type="button"
          onClick={() => { setEventType("all"); setSearch(""); }}>Xóa bộ lọc mốc</button> : null}
      </div>
      <p className="workspace-note" role="status">Hiển thị {visibleEvents.length}/{events.length} mốc xử lý canonical theo thứ tự trả về từ API.</p>
      {visibleEvents.length > 0 ? <div
        aria-label={view === "timeline" ? "Cuộn mốc xử lý hành chính" : undefined}
        className="table-scroll table-scroll-history"
        role={view === "timeline" ? "region" : undefined}
        tabIndex={view === "timeline" ? 0 : undefined}
      >
        <table aria-label="Các mốc xử lý hành chính" className="dense-table event-milestone-table">
          <thead><tr><th>Mốc</th><th>Ngày</th><th>Nội dung</th></tr></thead>
          <tbody>
            {visibleEvents.map(({ event, originalIndex }) => (
              <tr key={`${event.event_type}:${event.occurred_at ?? "none"}:${originalIndex}`}>
                <td>{PROCESSING_EVENT_LABELS[event.event_type] ?? event.event_type}</td>
                <td>{formatCompactDate(event.occurred_at)}</td>
                <td><InspectionTimelinePayload eventType={event.event_type} payload={event.payload} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div> : <p className="workspace-note">Không có mốc xử lý phù hợp. Xóa bộ lọc để xem toàn bộ lịch sử.</p>}
    </> : (
      <EmptyState title="Chưa có mốc xử lý" description="Chưa có inspection event canonical nào cho bước xử lý của hồ sơ này." />
    )}
  </section>;
}

export function CaseProcessingWorkspace({
  caseWorkspace,
  onSave,
  view,
}: {
  caseWorkspace: CaseWorkspace;
  onSave: (payload: CaseAssessmentUpsertRequest) => Promise<void>;
  view?: "assessment" | "timeline";
}) {
  const currentDraft = useMemo(() => buildDraft(caseWorkspace), [caseWorkspace]);
  const commandLock = useCaseCommandLock("assessment");
  const requiresReview = commandLock.requiresReview;
  const review = commandLock.commandPayload<AssessmentReview>();
  const [draft, setDraft] = useCaseDraftState<ProcessingDraft>("assessment.draft", review?.draft ?? currentDraft);
  const [editingField, setEditingField] = useCaseDraftState<keyof ProcessingDraft | null>("assessment.editingField", review?.editingField ?? null);
  const [draftVersion, setDraftVersion] = useCaseDraftState("assessment.draftVersion", review ? review.draftVersion : caseWorkspace.processing.row_version);
  const [pending, setPending] = useCaseDraftState("assessment.pending", false);
  const [errorMessage, setErrorMessage] = useCaseDraftState<string | null>("assessment.errorMessage", review?.errorMessage ?? null);

  // The Case-local editor session can be replaced by A → B → A while an HTTP
  // command remains unknown. Recover only the submitted copy from its exact
  // access/Case-scoped command registry, never a canonical result or a retry.
  useEffect(() => {
    if ((!requiresReview && !commandLock.pending) || !review) return;
    setDraft(review.draft);
    setEditingField(review.editingField);
    setDraftVersion(review.draftVersion);
    setErrorMessage(review.errorMessage);
  }, [requiresReview, commandLock.pending, review, setDraft, setEditingField, setDraftVersion, setErrorMessage]);

  useEffect(() => {
    if (!editingField && !requiresReview && !commandLock.pending) {
      setDraft(currentDraft);
      setErrorMessage(null);
    }
  }, [currentDraft, editingField, requiresReview, commandLock.pending, setDraft, setErrorMessage]);

  async function saveField() {
    if (!editingField || pending || commandLock.pending || requiresReview) {
      return;
    }
    // Pin the exact intent before the asynchronous write can outlive this Case session.
    const command = commandLock.acquire({
      draft: { ...draft }, editingField, draftVersion, errorMessage: "",
    } satisfies AssessmentReview);
    if (!command) return;
    setPending(true);
    setErrorMessage(null);
    try {
      // The backend applies only provided fields. Sending the entire draft
      // would rewrite unrelated assessment metadata whenever one field changes.
      const value = editingField === "assessed_on"
        ? toDateTimePayload(draft.assessed_on)
        : normalizeText(draft[editingField]);
      await onSave({ expected_version: draftVersion, [editingField]: value });
      setEditingField(null);
    } catch (error) {
      const nextError = error instanceof Error ? error : new Error("Không lưu được bước xử lý.");
      if (error instanceof CaseFieldMutationRecoveryError) {
        commandLock.requireReview(command, {
          draft: { ...draft }, editingField, draftVersion,
          errorMessage: getErrorMessage(nextError),
        } satisfies AssessmentReview);
      }
      setErrorMessage(getErrorMessage(nextError));
    } finally {
      commandLock.release(command);
      setPending(false);
    }
  }

  function cancelEdit() {
    if (pending || commandLock.pending || requiresReview) return;
    setDraft(currentDraft);
    setErrorMessage(null);
    setEditingField(null);
  }

  return (
    <div className={`event-step-stack${view === "assessment" ? " case-assessment-stack" : view === "timeline" ? " processing-timeline" : ""}`}>
      {requiresReview ? <p className="form-error" role="alert">Chưa xác minh kết quả lưu. Không gửi lại; sao chép bản nháp rồi tải lại hồ sơ.</p> : null}
      {view !== "timeline" ? <section className="workspace-section case-assessment-section">
        <h4 className={view === "assessment" ? "sr-only" : undefined}>{view === "assessment" ? "Thẩm định hồ sơ" : "Thông tin xử lý"}</h4>
        <div className="case-assessment-grid">
        <div className="detail-grid compact-grid detail-form-matrix case-assessment-metadata">
          <EditableDetailValue
            editButtonLabel="Sửa Ngày thẩm định"
            error={editingField === "assessed_on" ? errorMessage : null}
            isEditing={editingField === "assessed_on"}
            label="Ngày thẩm định"
            onCancel={cancelEdit}
            onEdit={requiresReview || commandLock.pending ? null : () => {
              setDraftVersion(caseWorkspace.processing.row_version);
              setEditingField("assessed_on");
              setErrorMessage(null);
            }}
            onSave={() => void saveField()}
            pending={pending || commandLock.pending || requiresReview}
            saveDisabled={requiresReview || commandLock.pending}
            value={formatCompactDate(caseWorkspace.processing.assessed_on)}
          >
            <input
              aria-label="Ngày thẩm định"
              readOnly={pending || commandLock.pending || requiresReview}
              onChange={(event) => { if (pending || commandLock.pending || requiresReview) return; setDraft((current) => ({ ...current, assessed_on: event.target.value })); }}
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
            onEdit={requiresReview || commandLock.pending ? null : () => {
              setDraftVersion(caseWorkspace.processing.row_version);
              setEditingField("assessor_name");
              setErrorMessage(null);
            }}
            onSave={() => void saveField()}
            pending={pending || commandLock.pending || requiresReview}
            saveDisabled={requiresReview || commandLock.pending}
            value={caseWorkspace.processing.assessor_name}
          >
            <input
              aria-label="Người thẩm định"
              readOnly={pending || commandLock.pending || requiresReview}
              onChange={(event) => { if (pending || commandLock.pending || requiresReview) return; setDraft((current) => ({ ...current, assessor_name: event.target.value })); }}
              value={draft.assessor_name}
            />
          </EditableDetailValue>

        </div>
        <div className="case-assessment-result">
          <EditableDetailValue
            editButtonLabel="Sửa Kết quả thẩm định"
            error={editingField === "assessment_result" ? errorMessage : null}
            isEditing={editingField === "assessment_result"}
            label="Kết quả thẩm định"
            multiline
            onCancel={cancelEdit}
            onEdit={requiresReview || commandLock.pending ? null : () => {
              setDraftVersion(caseWorkspace.processing.row_version);
              setEditingField("assessment_result");
              setErrorMessage(null);
            }}
            onSave={() => void saveField()}
            pending={pending || commandLock.pending || requiresReview}
            saveDisabled={requiresReview || commandLock.pending}
            value={caseWorkspace.processing.assessment_result}
          >
            <textarea
              aria-label="Kết quả thẩm định"
              className="inspection-textarea"
              readOnly={pending || commandLock.pending || requiresReview}
              onChange={(event) => { if (pending || commandLock.pending || requiresReview) return; setDraft((current) => ({ ...current, assessment_result: event.target.value })); }}
              rows={4}
              value={draft.assessment_result}
            />
          </EditableDetailValue>
          <EditableDetailValue
            editButtonLabel="Sửa Ghi chú thẩm định"
            error={editingField === "notes" ? errorMessage : null}
            isEditing={editingField === "notes"}
            label="Ghi chú thẩm định"
            multiline
            onCancel={cancelEdit}
            onEdit={requiresReview || commandLock.pending ? null : () => {
              setDraftVersion(caseWorkspace.processing.row_version);
              setEditingField("notes");
              setErrorMessage(null);
            }}
            onSave={() => void saveField()}
            pending={pending || commandLock.pending || requiresReview}
            saveDisabled={requiresReview || commandLock.pending}
            value={caseWorkspace.processing.notes}
          >
            <textarea
              aria-label="Ghi chú thẩm định"
              className="inspection-textarea"
              readOnly={pending || commandLock.pending || requiresReview}
              onChange={(event) => { if (pending || commandLock.pending || requiresReview) return; setDraft((current) => ({ ...current, notes: event.target.value })); }}
              rows={3}
              value={draft.notes}
            />
          </EditableDetailValue>
        </div>
        </div>
      </section> : null}

      {view !== "assessment" ? <CaseEventTimeline caseWorkspace={caseWorkspace} view={view} /> : null}
    </div>
  );
}
