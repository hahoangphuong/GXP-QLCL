import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";
import { useCaseCommandLock, useCaseDraftState } from "./CaseDraftSession";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { formatCompactDate, formatStatusLabel } from "../../lib/presentation";
import type { CaseApplicationUpsertRequest, CaseWorkspace, InspectionFolderLookup } from "../../types";
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
  applicant_name: string;
};

type ApplicationSubmission = {
  draft: FormDraft;
  editingField: keyof FormDraft;
  draftVersion: CaseWorkspace["application"]["row_version"];
  errorMessage: string | null;
};

type FolderLookupOwner = {
  identity: string;
  generation: number;
};

type FolderLookupState = {
  owner: FolderLookupOwner;
  pending: boolean;
  result: InspectionFolderLookup | null;
  error: string | null;
};

function buildDraft(caseWorkspace: CaseWorkspace): FormDraft {
  return {
    submitted_on: toDateInputValue(caseWorkspace.application.submitted_on),
    dossier_code: caseWorkspace.application.dossier_code ?? "",
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
  accessGeneration = 0,
  caseWorkspace,
  onSave,
  onResolveInspectionFolder,
  assessment,
}: {
  accessGeneration?: number | null;
  caseWorkspace: CaseWorkspace;
  onSave: (payload: CaseApplicationUpsertRequest) => Promise<void>;
  onResolveInspectionFolder: () => Promise<InspectionFolderLookup>;
  assessment?: ReactNode;
}) {
  const currentDraft = useMemo(() => buildDraft(caseWorkspace), [caseWorkspace]);
  const commandLock = useCaseCommandLock("application");
  const requiresReview = commandLock.requiresReview;
  // A pending or uncertain POST outlives a Case-local editor session. The
  // existing Case/access command owner retains the exact submitted intent.
  const submitted = commandLock.commandPayload<ApplicationSubmission>();
  const activeSubmission = commandLock.pending || requiresReview ? submitted : undefined;
  const [draft, setDraft] = useCaseDraftState<FormDraft>("application.draft", activeSubmission?.draft ?? currentDraft);
  const [draftVersion, setDraftVersion] = useCaseDraftState("application.draftVersion", activeSubmission ? activeSubmission.draftVersion : caseWorkspace.application.row_version);
  const [editingField, setEditingField] = useCaseDraftState<keyof FormDraft | null>("application.editingField", activeSubmission?.editingField ?? null);
  const [pending, setPending] = useCaseDraftState("application.pending", false);
  const [errorMessage, setErrorMessage] = useCaseDraftState<string | null>("application.errorMessage", activeSubmission?.errorMessage ?? null);
  const mutationLocked = pending || commandLock.pending || requiresReview;
  const folderLookupIdentity = JSON.stringify([
    accessGeneration,
    caseWorkspace.case_summary.id,
    caseWorkspace.case_summary.site_id,
    caseWorkspace.case_summary.legacy_site_id,
    caseWorkspace.case_summary.legacy_inspection_code,
  ]);
  const folderLookupOwner = useRef<FolderLookupOwner>({ identity: folderLookupIdentity, generation: 0 });
  const [folderLookupState, setFolderLookupState] = useState<FolderLookupState>({
    owner: folderLookupOwner.current,
    pending: false,
    result: null,
    error: null,
  });

  useLayoutEffect(() => {
    if (folderLookupOwner.current.identity === folderLookupIdentity) {
      return;
    }
    const owner = {
      identity: folderLookupIdentity,
      generation: folderLookupOwner.current.generation + 1,
    };
    folderLookupOwner.current = owner;
    setFolderLookupState({ owner, pending: false, result: null, error: null });
  }, [folderLookupIdentity]);

  useLayoutEffect(() => () => {
    folderLookupOwner.current = {
      identity: "unmounted",
      generation: folderLookupOwner.current.generation + 1,
    };
  }, []);

  const ownedFolderLookupState = folderLookupOwner.current.identity === folderLookupIdentity
    && folderLookupState.owner === folderLookupOwner.current
    ? folderLookupState
    : null;
  const folderLookup = ownedFolderLookupState?.result ?? null;
  const folderLookupError = ownedFolderLookupState?.error ?? null;
  const folderLookupPending = ownedFolderLookupState?.pending ?? false;

  useEffect(() => {
    if (activeSubmission) {
      setDraft(activeSubmission.draft);
      setDraftVersion(activeSubmission.draftVersion);
      setEditingField(activeSubmission.editingField);
      setErrorMessage(activeSubmission.errorMessage);
    } else if (!editingField && !mutationLocked) {
      setDraft(currentDraft);
      setErrorMessage(null);
    }
  }, [activeSubmission, currentDraft, editingField, mutationLocked, setDraft, setDraftVersion, setEditingField, setErrorMessage]);

  async function saveField() {
    if (!editingField || pending || commandLock.pending || requiresReview) {
      return;
    }
    if (draftVersion === null && caseWorkspace.application.row_version !== null) {
      setErrorMessage("Thông tin hồ sơ đã được tạo sau khi bắt đầu sửa. Bản nháp được giữ lại; Hủy sửa rồi mở lại trường để kiểm tra dữ liệu mới.");
      return;
    }
    const value = editingField === "submitted_on"
      ? toSubmittedOnPayload(draft.submitted_on)
      : normalizeText(draft[editingField]);
    const command = commandLock.acquire({
      draft: { ...draft }, editingField, draftVersion, errorMessage: null,
    } satisfies ApplicationSubmission);
    if (!command) return;
    setPending(true);
    setErrorMessage(null);
    try {
      await onSave({ expected_version: draftVersion, [editingField]: value });
      setEditingField(null);
    } catch (error) {
      const nextError = error instanceof Error ? error : new Error("Không lưu được thông tin hồ sơ.");
      if (error instanceof CaseFieldMutationRecoveryError) commandLock.requireReview(command, {
        draft: { ...draft }, editingField, draftVersion, errorMessage: getErrorMessage(nextError),
      } satisfies ApplicationSubmission);
      setErrorMessage(getErrorMessage(nextError));
    } finally {
      commandLock.release(command);
      setPending(false);
    }
  }

  function cancelEdit() {
    if (mutationLocked) return;
    setDraft(currentDraft);
    setErrorMessage(null);
    setEditingField(null);
  }

  async function resolveInspectionFolder() {
    if (folderLookupPending) {
      return;
    }
    const owner = folderLookupOwner.current;
    setFolderLookupState({ owner, pending: true, result: null, error: null });
    try {
      const result = await onResolveInspectionFolder();
      if (folderLookupOwner.current === owner) {
        setFolderLookupState({ owner, pending: false, result, error: null });
      }
    } catch (error) {
      if (folderLookupOwner.current === owner) {
        setFolderLookupState({
          owner,
          pending: false,
          result: null,
          error: error instanceof Error ? error.message : "Không thể tra cứu thư mục kiểm tra.",
        });
      }
    }
  }

  const canResolveInspectionFolder =
    accessGeneration !== null
    && caseWorkspace.case_summary.legacy_site_id !== null
    && caseWorkspace.case_summary.legacy_inspection_code !== null;

  const additionalInformation = (
    <div className="detail-grid compact-grid detail-form-matrix case-application-grid case-application-extra">
      <DetailValue label="Loại kiểm tra" value={caseWorkspace.case_summary.inspection_type} />
      <DetailValue label="GxP" value={caseWorkspace.case_summary.gxp_type} />
      <DetailValue label="Dây chuyền" value={caseWorkspace.case_summary.scope_code} />
      <DetailValue label="Tiêu chuẩn áp dụng" value={caseWorkspace.case_summary.applicable_standard} />
      <DetailValue label="Năm mở hồ sơ" value={String(caseWorkspace.case_summary.opened_year ?? "")} />
      <DetailValue label="Trạng thái hồ sơ" value={formatStatusLabel(caseWorkspace.case_summary.state)} />
    </div>
  );

  return (
    <div className="event-step-stack" data-case-application tabIndex={-1} aria-label="Khu vực hồ sơ đăng ký">
      {requiresReview ? <p className="form-error" role="alert">Chưa xác minh kết quả lưu. Không gửi lại; sao chép bản nháp rồi tải lại hồ sơ.</p> : null}
      <section className={`workspace-section case-application-section${assessment ? " legacy-dossier-section" : ""}`}>
        <h4 className={assessment ? "sr-only" : undefined}>Thông tin hồ sơ</h4>
        <div className="detail-grid compact-grid detail-form-matrix case-application-grid case-application-primary">
          <EditableDetailValue
            editButtonLabel="Sửa Ngày nộp"
            error={editingField === "submitted_on" ? errorMessage : null}
            isEditing={editingField === "submitted_on"}
            label="Ngày nộp"
            onCancel={cancelEdit}
            onEdit={mutationLocked ? null : () => {
              setDraftVersion(caseWorkspace.application.row_version);
              setEditingField("submitted_on");
              setErrorMessage(null);
            }}
            onSave={() => void saveField()}
            pending={mutationLocked}
            saveDisabled={mutationLocked}
            value={formatCompactDate(caseWorkspace.application.submitted_on)}
          >
            <input
              aria-label="Ngày nộp"
              readOnly={mutationLocked}
              onChange={(event) => { if (mutationLocked) return; setDraft((current) => ({ ...current, submitted_on: event.target.value })); }}
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
            onEdit={mutationLocked ? null : () => {
              setDraftVersion(caseWorkspace.application.row_version);
              setEditingField("dossier_code");
              setErrorMessage(null);
            }}
            onSave={() => void saveField()}
            pending={mutationLocked}
            saveDisabled={mutationLocked}
            value={caseWorkspace.application.dossier_code}
          >
            <input
              aria-label="Mã hồ sơ"
              readOnly={mutationLocked}
              onChange={(event) => { if (mutationLocked) return; setDraft((current) => ({ ...current, dossier_code: event.target.value })); }}
              value={draft.dossier_code}
            />
          </EditableDetailValue>

          <EditableDetailValue
            editButtonLabel="Sửa Người nộp hồ sơ"
            error={editingField === "applicant_name" ? errorMessage : null}
            isEditing={editingField === "applicant_name"}
            label="Người nộp hồ sơ"
            onCancel={cancelEdit}
            onEdit={mutationLocked ? null : () => {
              setDraftVersion(caseWorkspace.application.row_version);
              setEditingField("applicant_name");
              setErrorMessage(null);
            }}
            onSave={() => void saveField()}
            pending={mutationLocked}
            saveDisabled={mutationLocked}
            value={caseWorkspace.application.applicant_name}
          >
            <input
              aria-label="Người nộp hồ sơ"
              readOnly={mutationLocked}
              onChange={(event) => { if (mutationLocked) return; setDraft((current) => ({ ...current, applicant_name: event.target.value })); }}
              value={draft.applicant_name}
            />
          </EditableDetailValue>

        </div>
        {assessment}
        {assessment ? <details className="case-application-additional"><summary>Thông tin bổ sung</summary>{additionalInformation}</details> : additionalInformation}
        <div className="panel-actions panel-actions-tight">
          <button disabled={!canResolveInspectionFolder || folderLookupPending} onClick={() => void resolveInspectionFolder()} type="button">
            {folderLookupPending ? "Đang tra cứu..." : "Tra cứu thư mục kiểm tra"}
          </button>
        </div>
        {folderLookup?.status === "resolved" ? <p>Đã tìm thấy thư mục: {folderLookup.relative_path}</p> : null}
        {folderLookup?.status === "ambiguous" ? <p role="alert">Có {folderLookup.candidate_count} thư mục trùng khớp; không chọn tự động.</p> : null}
        {folderLookup?.status === "not_found" ? <p role="alert">Không tìm thấy thư mục kiểm tra khớp chính xác.</p> : null}
        {folderLookup?.status === "invalid" ? <p role="alert">Không đủ định danh legacy để tra cứu thư mục kiểm tra.</p> : null}
        {folderLookupError ? <p className="form-error" role="alert">Không thể truy cập lưu trữ: {folderLookupError}</p> : null}
      </section>
    </div>
  );
}
