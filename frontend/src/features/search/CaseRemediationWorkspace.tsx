import { useEffect, useMemo, useState, type FormEvent } from "react";

import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { formatCompactDate, formatStatusLabel } from "../../lib/presentation";
import type {
  CapaCycleAssessRequest,
  CapaCycleCreateRequest,
  CapaCycleSubmitRequest,
  CapaCycleUpdateRequest,
  CaseWorkspace,
  CaseWorkspaceRemediationCycle,
} from "../../types";
import { EditableDetailValue } from "./EditableDetailValue";
import { DetailValue } from "./DetailValue";

type CycleDraft = {
  requested_on: string;
  submitted_on: string;
  assessed_on: string;
  notes: string;
  result: string;
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

function buildCycleDraft(cycle: CaseWorkspaceRemediationCycle | null): CycleDraft {
  return {
    requested_on: normalizeDateInputValue(cycle?.requested_on ?? null),
    submitted_on: normalizeDateInputValue(cycle?.submitted_on ?? null),
    assessed_on: normalizeDateInputValue(cycle?.assessed_on ?? null),
    notes: cycle?.notes ?? "",
    result: cycle?.result ?? "",
  };
}

function getErrorStatus(error: Error): number | null {
  const status = (error as Error & { status?: unknown }).status;
  return typeof status === "number" ? status : null;
}

function getCreateErrorMessage(error: Error): string {
  const status = getErrorStatus(error);
  if (status === 403) {
    return "Bạn không có quyền thực hiện thao tác này.";
  }
  if (status === 409) {
    return "Không thể tạo vòng khắc phục vì hồ sơ đã bị thay đổi hoặc đã ở trạng thái kết thúc. Tải lại workspace rồi thử lại.";
  }
  if (status === 422) {
    return `Dữ liệu khắc phục chưa hợp lệ. ${error.message}`;
  }
  return error.message || "Không tạo được vòng khắc phục.";
}

function getCycleErrorMessage(error: Error): string {
  const status = getErrorStatus(error);
  if (status === 403) {
    return "Bạn không có quyền thực hiện thao tác này.";
  }
  if (status === 409) {
    return "Không thể lưu vì vòng khắc phục đã bị thay đổi hoặc hồ sơ đã ở trạng thái kết thúc. Tải lại workspace rồi thử lại.";
  }
  if (status === 422) {
    return `Dữ liệu khắc phục chưa hợp lệ. ${error.message}`;
  }
  return error.message || "Không lưu được vòng khắc phục.";
}

function getSubmitErrorMessage(error: Error): string {
  const status = getErrorStatus(error);
  if (status === 403) {
    return "Bạn không có quyền thực hiện thao tác này.";
  }
  if (status === 409) {
    return "Không thể ghi nhận tiếp nhận khắc phục vì vòng hiện tại đã thay đổi hoặc không còn ở trạng thái hợp lệ. Tải lại workspace rồi thử lại.";
  }
  if (status === 422) {
    return `Dữ liệu tiếp nhận khắc phục chưa hợp lệ. ${error.message}`;
  }
  return error.message || "Không ghi nhận được tiếp nhận khắc phục.";
}

function getAssessErrorMessage(error: Error): string {
  const status = getErrorStatus(error);
  if (status === 403) {
    return "Bạn không có quyền thực hiện thao tác này.";
  }
  if (status === 409) {
    return "Không thể đánh giá khắc phục vì vòng hiện tại đã thay đổi hoặc không còn ở trạng thái hợp lệ. Tải lại workspace rồi thử lại.";
  }
  if (status === 422) {
    return `Dữ liệu đánh giá khắc phục chưa hợp lệ. ${error.message}`;
  }
  return error.message || "Không đánh giá được vòng khắc phục.";
}

function buildSelectedCycleId(
  cycles: CaseWorkspaceRemediationCycle[],
  selectedCycleId: string | null,
): string | null {
  if (selectedCycleId && cycles.some((cycle) => cycle.capa_cycle_id === selectedCycleId)) {
    return selectedCycleId;
  }
  return cycles.at(-1)?.capa_cycle_id ?? null;
}

function getSelectedCycle(
  cycles: CaseWorkspaceRemediationCycle[],
  selectedCycleId: string | null,
): CaseWorkspaceRemediationCycle | null {
  return cycles.find((cycle) => cycle.capa_cycle_id === selectedCycleId) ?? cycles.at(-1) ?? null;
}

function isCreateAvailable(caseWorkspace: CaseWorkspace): boolean {
  const state = caseWorkspace.case_summary.state;
  if (state !== "inspection_completed") {
    return false;
  }
  const latestCycle = caseWorkspace.remediation.cycles.at(-1);
  if (!latestCycle) {
    return true;
  }
  return latestCycle.status === "rejected";
}

function isUpdateAvailable(cycle: CaseWorkspaceRemediationCycle | null): boolean {
  return cycle?.status === "requested" || cycle?.status === "rejected";
}

function isSubmitAvailable(cycle: CaseWorkspaceRemediationCycle | null): boolean {
  return cycle?.status === "requested" || cycle?.status === "rejected";
}

function isAssessAvailable(cycle: CaseWorkspaceRemediationCycle | null): boolean {
  return cycle?.status === "submitted";
}

export function CaseRemediationWorkspace({
  caseWorkspace,
  selectedCycleId,
  onSelectedCycleChange,
  onCreateCycle,
  onUpdateCycle,
  onSubmitCycle,
  onAssessCycle,
}: {
  caseWorkspace: CaseWorkspace;
  selectedCycleId: string | null;
  onSelectedCycleChange: (cycleId: string | null) => void;
  onCreateCycle: (payload: CapaCycleCreateRequest) => Promise<void>;
  onUpdateCycle: (cycleId: string, payload: CapaCycleUpdateRequest) => Promise<void>;
  onSubmitCycle: (cycleId: string, payload: CapaCycleSubmitRequest) => Promise<void>;
  onAssessCycle: (cycleId: string, payload: CapaCycleAssessRequest) => Promise<void>;
}) {
  const cycles = caseWorkspace.remediation.cycles;
  const effectiveSelectedCycleId = useMemo(
    () => buildSelectedCycleId(cycles, selectedCycleId),
    [cycles, selectedCycleId],
  );
  const selectedCycle = useMemo(
    () => getSelectedCycle(cycles, effectiveSelectedCycleId),
    [cycles, effectiveSelectedCycleId],
  );
  const currentDraft = useMemo(() => buildCycleDraft(selectedCycle), [selectedCycle]);
  const [draft, setDraft] = useState<CycleDraft>(currentDraft);
  const [isCreating, setIsCreating] = useState(false);
  const [editingField, setEditingField] = useState<"requested_on" | "notes" | null>(null);
  const [pendingAction, setPendingAction] = useState<"create" | "update" | "submit" | "assess" | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (effectiveSelectedCycleId !== selectedCycleId) {
      onSelectedCycleChange(effectiveSelectedCycleId);
    }
  }, [effectiveSelectedCycleId, onSelectedCycleChange, selectedCycleId]);

  useEffect(() => {
    if (!isCreating && !editingField) {
      setDraft(currentDraft);
      setErrorMessage(null);
    }
  }, [currentDraft, editingField, isCreating]);

  const createAvailable = isCreateAvailable(caseWorkspace);
  const updateAvailable = isUpdateAvailable(selectedCycle);
  const submitAvailable = isSubmitAvailable(selectedCycle);
  const assessAvailable = isAssessAvailable(selectedCycle);
  const hasOpenEditor = isCreating || editingField !== null;
  const isPending = pendingAction !== null;

  async function handleCreateSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isPending) {
      return;
    }
    setPendingAction("create");
    setErrorMessage(null);
    try {
      await onCreateCycle({
        expected_case_version: caseWorkspace.case_summary.row_version,
        requested_on: normalizeText(draft.requested_on),
        notes: normalizeText(draft.notes),
      });
      setIsCreating(false);
    } catch (error) {
      const nextError = error instanceof Error ? error : new Error("Không tạo được vòng khắc phục.");
      setErrorMessage(getCreateErrorMessage(nextError));
    } finally {
      setPendingAction(null);
    }
  }

  async function handleUpdateField() {
    if (!selectedCycle || !editingField || isPending) {
      return;
    }
    setPendingAction("update");
    setErrorMessage(null);
    try {
      await onUpdateCycle(selectedCycle.capa_cycle_id, {
        expected_version: selectedCycle.row_version,
        requested_on: normalizeText(draft.requested_on),
        notes: normalizeText(draft.notes),
      });
      setEditingField(null);
    } catch (error) {
      const nextError = error instanceof Error ? error : new Error("Không lưu được vòng khắc phục.");
      setErrorMessage(getCycleErrorMessage(nextError));
    } finally {
      setPendingAction(null);
    }
  }

  async function handleSubmitAction() {
    if (!selectedCycle || isPending) {
      return;
    }
    setPendingAction("submit");
    setErrorMessage(null);
    try {
      await onSubmitCycle(selectedCycle.capa_cycle_id, {
        expected_version: selectedCycle.row_version,
        submitted_on: draft.submitted_on,
        notes: normalizeText(draft.notes),
      });
    } catch (error) {
      const nextError = error instanceof Error ? error : new Error("Không ghi nhận được tiếp nhận khắc phục.");
      setErrorMessage(getSubmitErrorMessage(nextError));
    } finally {
      setPendingAction(null);
    }
  }

  async function handleAssessAction() {
    if (!selectedCycle || isPending) {
      return;
    }
    setPendingAction("assess");
    setErrorMessage(null);
    try {
      await onAssessCycle(selectedCycle.capa_cycle_id, {
        expected_version: selectedCycle.row_version,
        assessed_on: draft.assessed_on,
        result: draft.result.trim(),
        notes: normalizeText(draft.notes),
      });
    } catch (error) {
      const nextError = error instanceof Error ? error : new Error("Không đánh giá được vòng khắc phục.");
      setErrorMessage(getAssessErrorMessage(nextError));
    } finally {
      setPendingAction(null);
    }
  }

  function startCreate() {
    setDraft(buildCycleDraft(null));
    setErrorMessage(null);
    setEditingField(null);
    setIsCreating(true);
  }

  function cancelEditor() {
    setDraft(currentDraft);
    setErrorMessage(null);
    setIsCreating(false);
    setEditingField(null);
  }

  return (
    <div className="event-step-stack remediation-workspace">
      <section className="panel panel-tight">
        <div className="panel-header">
          <div className="panel-heading-inline">
            <h3>Lịch sử khắc phục</h3>
            <span className="panel-meta">{cycles.length} vòng</span>
          </div>
          {createAvailable ? (
            <div className="panel-actions panel-actions-tight">
              <button disabled={isPending || hasOpenEditor} onClick={startCreate} type="button">
                Thêm vòng khắc phục
              </button>
            </div>
          ) : null}
        </div>
        {cycles.length > 0 ? (
          <div className="table-scroll table-scroll-history">
            <table className="dense-table capa-cycle-table">
              <thead>
                <tr>
                  <th>Lần</th>
                  <th>Ngày yêu cầu</th>
                  <th>Ngày nhận</th>
                  <th>Ngày xử lý</th>
                  <th>Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {cycles.map((cycle) => (
                  <tr
                    aria-selected={effectiveSelectedCycleId === cycle.capa_cycle_id}
                    className={effectiveSelectedCycleId === cycle.capa_cycle_id ? "selected" : ""}
                    key={cycle.capa_cycle_id}
                    onClick={() => {
                      if (isPending) {
                        return;
                      }
                      setIsCreating(false);
                      setEditingField(null);
                      setErrorMessage(null);
                      onSelectedCycleChange(cycle.capa_cycle_id);
                    }}
                    onKeyDown={(event) => {
                      if ((event.key === "Enter" || event.key === " ") && !isPending) {
                        event.preventDefault();
                        setIsCreating(false);
                        setEditingField(null);
                        setErrorMessage(null);
                        onSelectedCycleChange(cycle.capa_cycle_id);
                      }
                    }}
                    tabIndex={0}
                  >
                    <td>{cycle.round_no}</td>
                    <td>{formatCompactDate(cycle.requested_on)}</td>
                    <td>{formatCompactDate(cycle.submitted_on)}</td>
                    <td>{formatCompactDate(cycle.assessed_on)}</td>
                    <td>{formatStatusLabel(cycle.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="Chưa có vòng khắc phục"
            description="Hồ sơ này hiện chưa có CAPA cycle canonical hoặc chưa phát sinh vòng khắc phục mới."
          />
        )}
      </section>

      {isCreating ? (
        <section className="workspace-section">
          <h4>Vòng khắc phục mới</h4>
          <form className="case-application-form" onSubmit={handleCreateSubmit}>
            <div className="detail-grid compact-grid case-application-form-grid">
              <label className="case-application-field">
                <span>Ngày yêu cầu</span>
                <input
                  aria-label="Ngày yêu cầu"
                  disabled={isPending}
                  onChange={(event) => setDraft((current) => ({ ...current, requested_on: event.target.value }))}
                  type="date"
                  value={draft.requested_on}
                />
              </label>
              <DetailValue label="Trạng thái ban đầu" value={formatStatusLabel("requested")} />
              <DetailValue label="Hồ sơ" value={caseWorkspace.case_summary.legacy_inspection_code} />
              <label className="case-application-field case-application-field-full">
                <span>Ghi chú</span>
                <textarea
                  aria-label="Ghi chú khắc phục"
                  className="inspection-textarea"
                  disabled={isPending}
                  onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))}
                  rows={4}
                  value={draft.notes}
                />
              </label>
            </div>
            {errorMessage ? (
              <p className="form-error" role="alert">
                {errorMessage}
              </p>
            ) : null}
            <div className="panel-actions panel-actions-tight">
              <button disabled={isPending} type="submit">
                {pendingAction === "create" ? "Đang tạo..." : "Tạo vòng khắc phục"}
              </button>
              <button className="secondary" disabled={isPending} onClick={cancelEditor} type="button">
                Hủy
              </button>
            </div>
          </form>
        </section>
      ) : selectedCycle ? (
        <>
          <section className="workspace-section">
            <div className="workspace-section-header">
              <div className="panel-heading-inline">
                <h4>Chi tiết vòng khắc phục {selectedCycle.round_no}</h4>
                <StatusBadge value={selectedCycle.status} />
              </div>
              <div className="panel-actions panel-actions-tight">
                {submitAvailable ? (
                  <button
                    disabled={isPending || !draft.submitted_on.trim()}
                    onClick={() => void handleSubmitAction()}
                    type="button"
                  >
                    {pendingAction === "submit" ? "Đang ghi nhận..." : "Ghi nhận tiếp nhận"}
                  </button>
                ) : null}
                {assessAvailable ? (
                  <button
                    disabled={isPending || !draft.assessed_on.trim() || !draft.result.trim()}
                    onClick={() => void handleAssessAction()}
                    type="button"
                  >
                    {pendingAction === "assess" ? "Đang đánh giá..." : "Đánh giá"}
                  </button>
                ) : null}
              </div>
            </div>
            <div className="detail-grid compact-grid remediation-detail-grid">
              <EditableDetailValue
                editButtonLabel="Sửa Ngày yêu cầu"
                error={editingField === "requested_on" ? errorMessage : null}
                isEditing={editingField === "requested_on"}
                label="Ngày yêu cầu"
                onCancel={cancelEditor}
                onEdit={
                  updateAvailable
                    ? () => {
                        setEditingField("requested_on");
                        setErrorMessage(null);
                      }
                    : null
                }
                onSave={() => void handleUpdateField()}
                pending={isPending}
                value={formatCompactDate(selectedCycle.requested_on)}
              >
                <input
                  aria-label="Ngày yêu cầu"
                  disabled={isPending}
                  onChange={(event) => setDraft((current) => ({ ...current, requested_on: event.target.value }))}
                  type="date"
                  value={draft.requested_on}
                />
              </EditableDetailValue>

              <DetailValue label="Ngày nhận" value={formatCompactDate(selectedCycle.submitted_on)} />
              <DetailValue label="Ngày xử lý" value={formatCompactDate(selectedCycle.assessed_on)} />
              <DetailValue label="Người đánh giá" value={selectedCycle.assessor_name} />
              <DetailValue label="Kết quả" value={selectedCycle.result} />
              <DetailValue label="Trạng thái" value={formatStatusLabel(selectedCycle.status)} />

              <EditableDetailValue
                editButtonLabel="Sửa Ghi chú"
                error={editingField === "notes" ? errorMessage : null}
                isEditing={editingField === "notes"}
                label="Ghi chú"
                multiline
                onCancel={cancelEditor}
                onEdit={
                  updateAvailable
                    ? () => {
                        setEditingField("notes");
                        setErrorMessage(null);
                      }
                    : null
                }
                onSave={() => void handleUpdateField()}
                pending={isPending}
                value={selectedCycle.notes}
              >
                <textarea
                  aria-label="Ghi chú khắc phục"
                  className="inspection-textarea"
                  disabled={isPending}
                  onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))}
                  rows={4}
                  value={draft.notes}
                />
              </EditableDetailValue>
            </div>
          </section>

          {(submitAvailable || assessAvailable) ? (
            <section className="workspace-section">
              <h4>Thao tác vòng khắc phục</h4>
              <div className="detail-grid compact-grid remediation-detail-grid">
                <label className="case-application-field">
                  <span>Ngày ghi nhận tiếp nhận</span>
                  <input
                    aria-label="Ngày ghi nhận tiếp nhận"
                    disabled={isPending || !submitAvailable}
                    onChange={(event) => setDraft((current) => ({ ...current, submitted_on: event.target.value }))}
                    type="date"
                    value={draft.submitted_on}
                  />
                </label>
                <label className="case-application-field">
                  <span>Ngày đánh giá</span>
                  <input
                    aria-label="Ngày đánh giá khắc phục"
                    disabled={isPending || !assessAvailable}
                    onChange={(event) => setDraft((current) => ({ ...current, assessed_on: event.target.value }))}
                    type="date"
                    value={draft.assessed_on}
                  />
                </label>
                <label className="case-application-field">
                  <span>Kết quả đánh giá</span>
                  <input
                    aria-label="Kết quả đánh giá khắc phục"
                    disabled={isPending || !assessAvailable}
                    onChange={(event) => setDraft((current) => ({ ...current, result: event.target.value }))}
                    value={draft.result}
                  />
                </label>
                <label className="case-application-field case-application-field-full">
                  <span>Ghi chú dùng cho thao tác</span>
                  <textarea
                    aria-label="Ghi chú thao tác khắc phục"
                    className="inspection-textarea"
                    disabled={isPending || (!submitAvailable && !assessAvailable)}
                    onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))}
                    rows={4}
                    value={draft.notes}
                  />
                </label>
              </div>
              {editingField === null && errorMessage ? (
                <p className="form-error" role="alert">
                  {errorMessage}
                </p>
              ) : null}
            </section>
          ) : editingField === null && errorMessage ? (
            <p className="form-error" role="alert">
              {errorMessage}
            </p>
          ) : null}
        </>
      ) : (
        <section className="workspace-section">
          <EmptyState
            title="Chưa có vòng khắc phục để xem"
            description="Tạo vòng khắc phục mới khi hồ sơ đang ở trạng thái cho phép."
          />
        </section>
      )}
    </div>
  );
}
