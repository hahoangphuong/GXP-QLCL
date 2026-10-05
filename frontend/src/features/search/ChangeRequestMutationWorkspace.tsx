import { useEffect, useState } from "react";

import { formatCompactDate, formatStatusLabel } from "../../lib/presentation";
import type {
  ChangeApprovalUpsertRequest,
  ChangeRequestDetailCreateRequest,
  ChangeRequestDetailUpdateRequest,
  ChangeRequestTransitionRequest,
  ChangeRequestUpdateRequest,
  ChangeRequestWorkspace,
  ChangeRequestWorkspaceDetail,
  LifecycleActionReadiness,
} from "../../types";
import { DetailValue } from "./DetailValue";

export type ChangeRequestMutationHandlers = {
  onUpdateHeader: (payload: ChangeRequestUpdateRequest) => Promise<void>;
  onCreateDetail: (payload: ChangeRequestDetailCreateRequest) => Promise<void>;
  onUpdateDetail: (changeDetailId: string, payload: ChangeRequestDetailUpdateRequest) => Promise<void>;
  onUpsertApproval: (payload: ChangeApprovalUpsertRequest) => Promise<void>;
  onTransition: (payload: ChangeRequestTransitionRequest) => Promise<void>;
};

type HeaderDraft = {
  scopeLabel: string;
  description: string;
  submittedOn: string;
  requesterName: string;
};

type DetailDraft = {
  classificationId: string;
  classificationLabel: string;
  approvalStatus: string;
  oldValue: string;
  newValue: string;
  note: string;
};

type ApprovalDraft = {
  handledOn: string;
  handledByName: string;
  resultLabel: string;
  effectiveOn: string;
  approvalReference: string;
};

function textOrNull(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function numberOrNull(value: string): number | null {
  const normalized = value.trim();
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function action(workspace: ChangeRequestWorkspace, actionKey: string): LifecycleActionReadiness | null {
  return workspace.action_readiness.find((item) => item.action_key === actionKey) ?? null;
}

function expectedVersion(workspace: ChangeRequestWorkspace, readiness: LifecycleActionReadiness | null): number {
  return readiness?.expected_version ?? workspace.row_version;
}

function headerDraftFrom(workspace: ChangeRequestWorkspace): HeaderDraft {
  return {
    scopeLabel: workspace.scope_label ?? "",
    description: workspace.description ?? "",
    submittedOn: workspace.submitted_on ?? "",
    requesterName: workspace.requester_name ?? "",
  };
}

function detailDraftFrom(detail?: ChangeRequestWorkspaceDetail | null): DetailDraft {
  return {
    classificationId: detail?.classification_id === null || detail?.classification_id === undefined ? "" : String(detail.classification_id),
    classificationLabel: detail?.classification_label ?? "",
    approvalStatus: detail?.approval_status ?? "",
    oldValue: detail?.old_value ?? "",
    newValue: detail?.new_value ?? "",
    note: detail?.note ?? "",
  };
}

function approvalDraftFrom(workspace: ChangeRequestWorkspace): ApprovalDraft {
  return {
    handledOn: workspace.handled_on ?? "",
    handledByName: workspace.handled_by_name ?? "",
    resultLabel: workspace.result_label ?? "",
    effectiveOn: workspace.effective_on ?? "",
    approvalReference: workspace.approval_reference ?? "",
  };
}

export function ChangeRequestMutationWorkspace({
  activeTab,
  handlers,
  workspace,
}: {
  activeTab: string;
  handlers: ChangeRequestMutationHandlers;
  workspace: ChangeRequestWorkspace;
}) {
  const [headerEditing, setHeaderEditing] = useState(false);
  const [headerDraft, setHeaderDraft] = useState<HeaderDraft>(() => headerDraftFrom(workspace));
  const [detailEditor, setDetailEditor] = useState<{ mode: "create" | "edit"; detailId: string | null } | null>(null);
  const [detailDraft, setDetailDraft] = useState<DetailDraft>(() => detailDraftFrom());
  const [approvalEditing, setApprovalEditing] = useState(false);
  const [approvalDraft, setApprovalDraft] = useState<ApprovalDraft>(() => approvalDraftFrom(workspace));
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    setHeaderEditing(false);
    setHeaderDraft(headerDraftFrom(workspace));
    setDetailEditor(null);
    setDetailDraft(detailDraftFrom());
    setApprovalEditing(false);
    setApprovalDraft(approvalDraftFrom(workspace));
    setPending(false);
    setErrorMessage(null);
  }, [workspace.id, workspace.row_version]);

  const editHeaderReadiness = action(workspace, "edit_change_request");
  const addDetailReadiness = action(workspace, "add_change_detail");
  const editDetailReadiness = action(workspace, "edit_change_detail");
  const editApprovalReadiness = action(workspace, "edit_change_approval");
  const transitionActions = workspace.action_readiness.filter(
    (item) => item.target_state && item.action_key.startsWith("transition_change_request:"),
  );

  async function runMutation(mutation: () => Promise<void>) {
    setPending(true);
    setErrorMessage(null);
    try {
      await mutation();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Không thể cập nhật yêu cầu thay đổi.");
    } finally {
      setPending(false);
    }
  }

  async function saveHeader() {
    const payload: ChangeRequestUpdateRequest = {
      expected_version: expectedVersion(workspace, editHeaderReadiness),
    };
    const scopeLabel = textOrNull(headerDraft.scopeLabel);
    const description = textOrNull(headerDraft.description);
    const submittedOn = textOrNull(headerDraft.submittedOn);
    const requesterName = textOrNull(headerDraft.requesterName);
    if (scopeLabel !== workspace.scope_label) payload.scope_label = scopeLabel;
    if (description !== workspace.description) payload.description = description;
    if (submittedOn !== workspace.submitted_on) payload.submitted_on = submittedOn;
    if (requesterName !== workspace.requester_name) payload.requester_name = requesterName;
    if (Object.keys(payload).length === 1) {
      setHeaderEditing(false);
      return;
    }
    await runMutation(async () => {
      await handlers.onUpdateHeader(payload);
      setHeaderEditing(false);
    });
  }

  function openCreateDetail() {
    setDetailDraft(detailDraftFrom());
    setDetailEditor({ mode: "create", detailId: null });
    setErrorMessage(null);
  }

  function openEditDetail(detail: ChangeRequestWorkspaceDetail) {
    setDetailDraft(detailDraftFrom(detail));
    setDetailEditor({ mode: "edit", detailId: detail.change_detail_id });
    setErrorMessage(null);
  }

  async function saveDetail() {
    const classificationId = numberOrNull(detailDraft.classificationId);
    const classificationLabel = textOrNull(detailDraft.classificationLabel);
    const approvalStatus = textOrNull(detailDraft.approvalStatus);
    const oldValue = textOrNull(detailDraft.oldValue);
    const newValue = textOrNull(detailDraft.newValue);
    const note = textOrNull(detailDraft.note);

    if (detailEditor?.mode === "create") {
      const payload: ChangeRequestDetailCreateRequest = {
        expected_version: expectedVersion(workspace, addDetailReadiness),
        classification_id: classificationId,
        classification_label: classificationLabel,
        approval_status: approvalStatus,
        old_value: oldValue,
        new_value: newValue,
        note,
      };
      await runMutation(async () => {
        await handlers.onCreateDetail(payload);
        setDetailEditor(null);
      });
      return;
    }

    if (detailEditor?.mode === "edit" && detailEditor.detailId) {
      const current = workspace.details.find((item) => item.change_detail_id === detailEditor.detailId);
      if (!current) {
        setErrorMessage("Chi tiết thay đổi không còn tồn tại trong workspace hiện hành.");
        return;
      }
      const payload: ChangeRequestDetailUpdateRequest = {
        expected_version: expectedVersion(workspace, editDetailReadiness),
      };
      if (classificationId !== current.classification_id) payload.classification_id = classificationId;
      if (classificationLabel !== current.classification_label) payload.classification_label = classificationLabel;
      if (approvalStatus !== current.approval_status) payload.approval_status = approvalStatus;
      if (oldValue !== current.old_value) payload.old_value = oldValue;
      if (newValue !== current.new_value) payload.new_value = newValue;
      if (note !== current.note) payload.note = note;
      if (Object.keys(payload).length === 1) {
        setDetailEditor(null);
        return;
      }
      await runMutation(async () => {
        await handlers.onUpdateDetail(current.change_detail_id, payload);
        setDetailEditor(null);
      });
    }
  }

  async function saveApproval() {
    const payload: ChangeApprovalUpsertRequest = {
      expected_version: expectedVersion(workspace, editApprovalReadiness),
    };
    const handledOn = textOrNull(approvalDraft.handledOn);
    const handledByName = textOrNull(approvalDraft.handledByName);
    const resultLabel = textOrNull(approvalDraft.resultLabel);
    const effectiveOn = textOrNull(approvalDraft.effectiveOn);
    const approvalReference = textOrNull(approvalDraft.approvalReference);
    if (handledOn !== workspace.handled_on) payload.handled_on = handledOn;
    if (handledByName !== workspace.handled_by_name) payload.handled_by_name = handledByName;
    if (resultLabel !== workspace.result_label) payload.result_label = resultLabel;
    if (effectiveOn !== workspace.effective_on) payload.effective_on = effectiveOn;
    if (approvalReference !== workspace.approval_reference) payload.approval_reference = approvalReference;
    if (Object.keys(payload).length === 1) {
      setApprovalEditing(false);
      return;
    }
    await runMutation(async () => {
      await handlers.onUpsertApproval(payload);
      setApprovalEditing(false);
    });
  }

  if (activeTab === "Đề nghị") {
    return (
      <div className="event-step-stack">
        <section className="workspace-section">
          <div className="workspace-section-heading">
            <h4>Thông tin đề nghị thay đổi</h4>
            <button
              disabled={!editHeaderReadiness?.available || pending}
              onClick={() => {
                setHeaderDraft(headerDraftFrom(workspace));
                setHeaderEditing(true);
                setErrorMessage(null);
              }}
              type="button"
            >
              {editHeaderReadiness?.label ?? "Sửa đề nghị"}
            </button>
          </div>
          <div className="detail-grid compact-grid">
            <DetailValue label="Mã thay đổi" value={workspace.legacy_change_request_id ? `TD-${workspace.legacy_change_request_id}` : null} />
            <DetailValue label="Phạm vi" value={workspace.scope_label} />
            <DetailValue label="Ngày đề nghị" value={formatCompactDate(workspace.submitted_on)} />
            <DetailValue label="Đơn vị/người đề nghị" value={workspace.requester_name} />
            <DetailValue label="Trạng thái" value={formatStatusLabel(workspace.state)} />
            <DetailValue label="Mô tả" multiline value={workspace.description} />
          </div>
          {!editHeaderReadiness?.available && editHeaderReadiness?.reason_code ? (
            <p className="workspace-note">Không thể sửa: {editHeaderReadiness.reason_code}.</p>
          ) : null}
          {headerEditing ? (
            <div className="detail-form-grid">
              <label>Phạm vi<input aria-label="Phạm vi thay đổi" disabled={pending} onChange={(event) => setHeaderDraft((current) => ({ ...current, scopeLabel: event.target.value }))} value={headerDraft.scopeLabel} /></label>
              <label>Ngày đề nghị<input aria-label="Ngày đề nghị thay đổi" disabled={pending} onChange={(event) => setHeaderDraft((current) => ({ ...current, submittedOn: event.target.value }))} type="date" value={headerDraft.submittedOn} /></label>
              <label>Đơn vị/người đề nghị<input aria-label="Người đề nghị thay đổi" disabled={pending} onChange={(event) => setHeaderDraft((current) => ({ ...current, requesterName: event.target.value }))} value={headerDraft.requesterName} /></label>
              <label className="full-width-field">Mô tả<textarea aria-label="Mô tả thay đổi" disabled={pending} onChange={(event) => setHeaderDraft((current) => ({ ...current, description: event.target.value }))} value={headerDraft.description} /></label>
              <div className="panel-actions">
                <button disabled={pending} onClick={() => void saveHeader()} type="button">{pending ? "Đang lưu..." : "Lưu đề nghị"}</button>
                <button disabled={pending} onClick={() => setHeaderEditing(false)} type="button">Hủy</button>
              </div>
            </div>
          ) : null}
        </section>
        {errorMessage ? <p className="form-error" role="alert">{errorMessage}</p> : null}
      </div>
    );
  }

  if (activeTab === "Chi tiết") {
    return (
      <div className="event-step-stack">
        <section className="workspace-section">
          <div className="workspace-section-heading">
            <h4>Danh mục chi tiết thay đổi</h4>
            <button disabled={!addDetailReadiness?.available || pending} onClick={openCreateDetail} type="button">
              {addDetailReadiness?.label ?? "Thêm chi tiết"}
            </button>
          </div>
          {workspace.details.length === 0 ? <p className="workspace-note">Chưa có chi tiết thay đổi.</p> : (
            <div className="table-scroll table-scroll-history">
              <table className="dense-table change-request-detail-table">
                <thead><tr><th>Phân loại</th><th>Trạng thái chấp nhận</th><th>Thông tin cũ</th><th>Thông tin mới</th><th>Thao tác</th></tr></thead>
                <tbody>
                  {workspace.details.map((item) => (
                    <tr key={item.change_detail_id}>
                      <td>{item.classification_label ?? "Chưa có"}</td>
                      <td>{item.approval_status ?? "Chưa có"}</td>
                      <td>{item.old_value ?? "Chưa có"}</td>
                      <td>{item.new_value ?? "Chưa có"}</td>
                      <td><button disabled={!editDetailReadiness?.available || pending} onClick={() => openEditDetail(item)} type="button">Sửa</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {detailEditor ? (
            <div className="detail-form-grid">
              <label>Mã phân loại<input aria-label="Mã phân loại thay đổi" disabled={pending} inputMode="numeric" onChange={(event) => setDetailDraft((current) => ({ ...current, classificationId: event.target.value }))} value={detailDraft.classificationId} /></label>
              <label>Phân loại<input aria-label="Phân loại thay đổi" disabled={pending} onChange={(event) => setDetailDraft((current) => ({ ...current, classificationLabel: event.target.value }))} value={detailDraft.classificationLabel} /></label>
              <label>Trạng thái chấp nhận<input aria-label="Trạng thái chi tiết thay đổi" disabled={pending} onChange={(event) => setDetailDraft((current) => ({ ...current, approvalStatus: event.target.value }))} value={detailDraft.approvalStatus} /></label>
              <label>Thông tin cũ<textarea aria-label="Thông tin cũ" disabled={pending} onChange={(event) => setDetailDraft((current) => ({ ...current, oldValue: event.target.value }))} value={detailDraft.oldValue} /></label>
              <label>Thông tin mới<textarea aria-label="Thông tin mới" disabled={pending} onChange={(event) => setDetailDraft((current) => ({ ...current, newValue: event.target.value }))} value={detailDraft.newValue} /></label>
              <label>Ghi chú<textarea aria-label="Ghi chú chi tiết thay đổi" disabled={pending} onChange={(event) => setDetailDraft((current) => ({ ...current, note: event.target.value }))} value={detailDraft.note} /></label>
              <div className="panel-actions">
                <button disabled={pending} onClick={() => void saveDetail()} type="button">{pending ? "Đang lưu..." : detailEditor.mode === "create" ? "Thêm chi tiết" : "Lưu chi tiết"}</button>
                <button disabled={pending} onClick={() => setDetailEditor(null)} type="button">Hủy</button>
              </div>
            </div>
          ) : null}
        </section>
        {errorMessage ? <p className="form-error" role="alert">{errorMessage}</p> : null}
      </div>
    );
  }

  return (
    <div className="event-step-stack">
      <section className="workspace-section">
        <div className="workspace-section-heading">
          <h4>Kết quả xử lý thay đổi</h4>
          <button
            disabled={!editApprovalReadiness?.available || pending}
            onClick={() => {
              setApprovalDraft(approvalDraftFrom(workspace));
              setApprovalEditing(true);
              setErrorMessage(null);
            }}
            type="button"
          >
            {editApprovalReadiness?.label ?? "Cập nhật xử lý"}
          </button>
        </div>
        <div className="detail-grid compact-grid">
          <DetailValue label="Ngày xử lý" value={formatCompactDate(workspace.handled_on)} />
          <DetailValue label="Người xử lý" value={workspace.handled_by_name} />
          <DetailValue label="Kết quả" multiline value={workspace.result_label} />
          <DetailValue label="Hiệu lực" value={formatCompactDate(workspace.effective_on)} />
          <DetailValue label="Tham chiếu phê duyệt" value={workspace.approval_reference} />
        </div>
        {approvalEditing ? (
          <div className="detail-form-grid">
            <label>Ngày xử lý<input aria-label="Ngày xử lý thay đổi" disabled={pending} onChange={(event) => setApprovalDraft((current) => ({ ...current, handledOn: event.target.value }))} type="date" value={approvalDraft.handledOn} /></label>
            <label>Người xử lý<input aria-label="Người xử lý thay đổi" disabled={pending} onChange={(event) => setApprovalDraft((current) => ({ ...current, handledByName: event.target.value }))} value={approvalDraft.handledByName} /></label>
            <label>Kết quả<textarea aria-label="Kết quả xử lý thay đổi" disabled={pending} onChange={(event) => setApprovalDraft((current) => ({ ...current, resultLabel: event.target.value }))} value={approvalDraft.resultLabel} /></label>
            <label>Ngày hiệu lực<input aria-label="Ngày hiệu lực thay đổi" disabled={pending} onChange={(event) => setApprovalDraft((current) => ({ ...current, effectiveOn: event.target.value }))} type="date" value={approvalDraft.effectiveOn} /></label>
            <label>Tham chiếu phê duyệt<input aria-label="Tham chiếu phê duyệt thay đổi" disabled={pending} onChange={(event) => setApprovalDraft((current) => ({ ...current, approvalReference: event.target.value }))} value={approvalDraft.approvalReference} /></label>
            <div className="panel-actions">
              <button disabled={pending} onClick={() => void saveApproval()} type="button">{pending ? "Đang lưu..." : "Lưu xử lý"}</button>
              <button disabled={pending} onClick={() => setApprovalEditing(false)} type="button">Hủy</button>
            </div>
          </div>
        ) : null}
      </section>
      {transitionActions.length > 0 ? (
        <section className="workspace-section">
          <h4>Chuyển trạng thái</h4>
          <div className="panel-actions">
            {transitionActions.map((item) => (
              <button
                disabled={!item.available || pending || !item.target_state}
                key={item.action_key}
                onClick={() => {
                  if (!item.target_state) return;
                  void runMutation(() => handlers.onTransition({
                    expected_version: expectedVersion(workspace, item),
                    target_state: item.target_state as string,
                  }));
                }}
                title={item.reason_code ?? item.label}
                type="button"
              >
                {item.label}
              </button>
            ))}
          </div>
        </section>
      ) : null}
      {errorMessage ? <p className="form-error" role="alert">{errorMessage}</p> : null}
    </div>
  );
}
