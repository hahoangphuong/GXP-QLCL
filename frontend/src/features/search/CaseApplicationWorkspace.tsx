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
  const [draft, setDraft] = useState<FormDraft>(currentDraft);
  const [draftVersion, setDraftVersion] = useState(caseWorkspace.application.row_version);
  const [editingField, setEditingField] = useState<"submitted_on" | "dossier_code" | null>(null);
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
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
      const value = editingField === "submitted_on"
        ? toSubmittedOnPayload(draft.submitted_on)
        : normalizeText(draft.dossier_code);
      await onSave({ expected_version: draftVersion, [editingField]: value });
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
    <div className="event-step-stack">
      <section className={`workspace-section case-application-section${assessment ? " legacy-dossier-section" : ""}`}>
        <h4 className={assessment ? "sr-only" : undefined}>Thông tin hồ sơ</h4>
        <div className="detail-grid compact-grid detail-form-matrix case-application-grid case-application-primary">
          <EditableDetailValue
            editButtonLabel="Sửa Ngày nộp"
            error={editingField === "submitted_on" ? errorMessage : null}
            isEditing={editingField === "submitted_on"}
            label="Ngày nộp"
            onCancel={cancelEdit}
            onEdit={() => {
              setDraftVersion(caseWorkspace.application.row_version);
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
              setDraftVersion(caseWorkspace.application.row_version);
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
