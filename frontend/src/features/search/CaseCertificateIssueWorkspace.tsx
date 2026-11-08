import { useEffect, useRef, useState } from "react";

import type { CertificateIssueActionReadiness, CertificateIssueRequest } from "../../types";
import { useCertificateDialogFocus } from "./useCertificateDialogFocus";
import { useCaseCommandLock, useCaseDraftState } from "./CaseDraftSession";
import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";
import { caseReadinessReason } from "./caseReadinessReason";

type ScopeDraft = CertificateIssueRequest["scopes"][number];
type IssueDraft = {
  certificateNumber: string;
  issueDate: string;
  expiryDate: string;
  reason: string;
  scopes: ScopeDraft[];
};
function emptyIssueDraft(): IssueDraft {
  return { certificateNumber: "", issueDate: "", expiryDate: "", reason: "", scopes: [] };
}

function CertificateIssueDialog({ caseId, readiness, saveAvailable, draft, setDraft, onClose, onIssue }: {
  caseId: string;
  readiness: CertificateIssueActionReadiness;
  saveAvailable: boolean;
  draft: IssueDraft;
  setDraft: (value: IssueDraft | ((current: IssueDraft) => IssueDraft)) => void;
  onClose: () => void;
  onIssue: (payload: CertificateIssueRequest) => Promise<void>;
}) {
  const dialogRef = useCertificateDialogFocus();

  const [pending, setPending] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !pending) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, pending]);

  function updateScope(index: number, field: keyof ScopeDraft, value: string | number | null) {
    setDraft((current) => ({ ...current, scopes: current.scopes.map((scope, scopeIndex) => scopeIndex === index ? { ...scope, [field]: value } : scope) }));
  }

  function addScope() {
    setDraft((current) => ({ ...current, scopes: [...current.scopes, {
      scope_key: null,
      scope_text: "",
      language_code: "vi",
      sort_order: current.scopes.length,
    }] }));
  }

  function moveScope(index: number, direction: -1 | 1) {
    setDraft((current) => {
      const destination = index + direction;
      if (destination < 0 || destination >= current.scopes.length) return current;
      const next = [...current.scopes];
      [next[index], next[destination]] = [next[destination], next[index]];
      return { ...current, scopes: next.map((scope, sort_order) => ({ ...scope, sort_order })) };
    });
  }

  async function submit() {
    if (inFlight.current || !saveAvailable) return;
    inFlight.current = true;
    setPending(true);
    setError(null);
    try {
      await onIssue({
        case_id: caseId,
        certificate_type: readiness.certificate_type,
        issuance_basis: readiness.issuance_basis,
        certificate_number: draft.certificateNumber.trim() || null,
        issue_date: draft.issueDate || null,
        expiry_date: draft.expiryDate || null,
        scopes: draft.scopes.map((scope) => ({
          scope_key: scope.scope_key?.trim() || null,
          scope_text: scope.scope_text,
          language_code: scope.language_code,
          sort_order: scope.sort_order,
        })),
        reason: draft.reason.trim() || null,
      });
      onClose();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Không thể cấp giấy chứng nhận.");
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }

  return <div className="dialog-backdrop" role="presentation">
    <section ref={dialogRef} tabIndex={-1} aria-labelledby="gxp-certificate-issue-title" aria-modal="true" className="panel certificate-edit-dialog" role="dialog">
      <header className="panel-header certificate-edit-dialog-header">
        <div><h2 id="gxp-certificate-issue-title">Cấp giấy chứng nhận GxP</h2><p>Loại GxP và điều kiện cấp do backend xác định theo hồ sơ kiểm tra đang chọn.</p></div>
      </header>
      <div className="certificate-edit-fields">
        <label>Loại GxP<span aria-label="Loại GxP" className="certificate-readonly-value">{readiness.certificate_type}</span></label>
        <label>Số GCN<input aria-label="Số GCN" disabled={pending} onChange={(event) => setDraft(current => ({ ...current, certificateNumber: event.target.value }))} value={draft.certificateNumber} /></label>
        <label>Ngày cấp<input aria-label="Ngày cấp" disabled={pending} onChange={(event) => setDraft(current => ({ ...current, issueDate: event.target.value }))} type="date" value={draft.issueDate} /></label>
        <label>Ngày hết hạn<input aria-label="Ngày hết hạn" disabled={pending} onChange={(event) => setDraft(current => ({ ...current, expiryDate: event.target.value }))} type="date" value={draft.expiryDate} /></label>
        <label className="certificate-edit-reason">Lý do cấp<textarea aria-label="Lý do cấp" disabled={pending} onChange={(event) => setDraft(current => ({ ...current, reason: event.target.value }))} value={draft.reason} /></label>
      </div>
      <section aria-label="Phạm vi chứng nhận có cấu trúc" className="certificate-scope-editor">
        <div className="certificate-scope-editor-header"><h3>Phạm vi chứng nhận</h3><button disabled={pending} onClick={addScope} type="button">Thêm phạm vi</button></div>
        <p className="certificate-scope-note">Khởi tạo rỗng: chưa có ánh xạ nghiệp vụ được xác nhận từ phạm vi đánh giá sang phạm vi chứng nhận.</p>
        {draft.scopes.map((scope, index) => <div className="certificate-scope-row" key={`${scope.sort_order}-${index}`}>
          <label>Mã phạm vi<input aria-label={`Mã phạm vi ${index + 1}`} disabled={pending} onChange={(event) => updateScope(index, "scope_key", event.target.value)} value={scope.scope_key ?? ""} /></label>
          <label>Nội dung phạm vi<textarea aria-label={`Nội dung phạm vi ${index + 1}`} disabled={pending} onChange={(event) => updateScope(index, "scope_text", event.target.value)} value={scope.scope_text} /></label>
          <label>Ngôn ngữ<input aria-label={`Ngôn ngữ phạm vi ${index + 1}`} disabled={pending} onChange={(event) => updateScope(index, "language_code", event.target.value)} value={scope.language_code} /></label>
          <div aria-label={`Thứ tự phạm vi ${index + 1}`} className="certificate-scope-order">{scope.sort_order}</div>
          <div className="certificate-scope-actions">
            <button aria-label={`Đưa phạm vi ${index + 1} lên`} disabled={pending || index === 0} onClick={() => moveScope(index, -1)} type="button">Lên</button>
            <button aria-label={`Đưa phạm vi ${index + 1} xuống`} disabled={pending || index === draft.scopes.length - 1} onClick={() => moveScope(index, 1)} type="button">Xuống</button>
            <button aria-label={`Xóa phạm vi ${index + 1}`} disabled={pending} onClick={() => setDraft(current => ({ ...current, scopes: current.scopes.filter((_, scopeIndex) => scopeIndex !== index).map((scope, sort_order) => ({ ...scope, sort_order })) }))} type="button">Xóa</button>
          </div>
        </div>)}
      </section>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <div className="panel-actions certificate-edit-dialog-actions">
        <button disabled={pending || !saveAvailable} onClick={() => void submit()} type="button">{pending ? "Đang cấp..." : "Cấp giấy chứng nhận"}</button>
        <button disabled={pending} onClick={onClose} type="button">Hủy</button>
      </div>
    </section>
  </div>;
}

export function CaseCertificateIssueWorkspace({ caseId, readiness, onIssue }: {
  caseId: string;
  readiness: CertificateIssueActionReadiness | null;
  onIssue: (payload: CertificateIssueRequest) => Promise<void>;
}) {
  // Issuance is a Case-owned multi-field draft. It survives unmounting this
  // tab but never crosses canonical Case/access-session boundaries.
  const [intent, setIntent] = useCaseDraftState<{ caseId: string; readiness: CertificateIssueActionReadiness } | null>("certificate.issue.intent", null);
  const [draft, setDraft] = useCaseDraftState<IssueDraft>("certificate.issue.draft", emptyIssueDraft);
  const visibleIntent = intent?.caseId === caseId ? intent : null;
  useEffect(() => {
    // In fallback (no CaseDraftSession), retire an old Case intent only after
    // commit. Never write external-store state while rendering a new owner.
    setIntent(current => current?.caseId === caseId ? current : null);
  }, [caseId, setIntent]);
  const commandLock = useCaseCommandLock(`certificate.issue:${caseId}`);
  async function issueOwned(payload: CertificateIssueRequest) {
    const command = commandLock.acquire();
    if (!command) throw new CaseFieldMutationRecoveryError("Chưa xác minh kết quả cấp chứng nhận trước; không gửi lại.");
    try {
      await onIssue(payload);
    } catch (error) {
      if (error instanceof CaseFieldMutationRecoveryError) commandLock.requireReview(command);
      throw error;
    } finally {
      commandLock.release(command);
    }
  }
  if (!readiness || readiness.action_key !== "issue_certificate") return <p className="workspace-note">Chưa có thông tin về điều kiện cấp chứng nhận.</p>;
  return <section className="workspace-section certificate-issue-section">
    <div className="certificate-action-bar">
      <button disabled={!readiness.available || commandLock.pending || commandLock.requiresReview} onClick={() => { setDraft(emptyIssueDraft()); setIntent({ caseId, readiness }); }} title={readiness.reason_code ?? undefined} type="button">{readiness.label}</button>
      {!readiness.available && readiness.reason_code ? <span>{caseReadinessReason(readiness.reason_code)}</span> : null}
    </div>
    {commandLock.requiresReview ? <p role="alert">Chưa xác minh kết quả cấp chứng nhận trước; không gửi lại.</p> : null}
    {visibleIntent ? <CertificateIssueDialog caseId={visibleIntent.caseId} onClose={() => setIntent(current => current === visibleIntent ? null : current)} onIssue={issueOwned} draft={draft} setDraft={setDraft} readiness={visibleIntent.readiness}
      saveAvailable={!commandLock.pending && !commandLock.requiresReview && readiness.available && readiness.certificate_type === visibleIntent.readiness.certificate_type && readiness.issuance_basis === visibleIntent.readiness.issuance_basis} /> : null}
  </section>;
}
