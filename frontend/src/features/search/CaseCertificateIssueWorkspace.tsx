import { useEffect, useState } from "react";

import type { CertificateIssueActionReadiness, CertificateIssueRequest } from "../../types";

type ScopeDraft = CertificateIssueRequest["scopes"][number];

function CertificateIssueDialog({ caseId, readiness, onClose, onIssue }: {
  caseId: string;
  readiness: CertificateIssueActionReadiness;
  onClose: () => void;
  onIssue: (payload: CertificateIssueRequest) => Promise<void>;
}) {
  const [certificateNumber, setCertificateNumber] = useState("");
  const [issueDate, setIssueDate] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [reason, setReason] = useState("");
  const [scopes, setScopes] = useState<ScopeDraft[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !pending) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, pending]);

  function updateScope(index: number, field: keyof ScopeDraft, value: string | number | null) {
    setScopes((current) => current.map((scope, scopeIndex) => scopeIndex === index ? { ...scope, [field]: value } : scope));
  }

  function addScope() {
    setScopes((current) => [...current, {
      scope_key: null,
      scope_text: "",
      language_code: "vi",
      sort_order: current.length,
    }]);
  }

  function moveScope(index: number, direction: -1 | 1) {
    setScopes((current) => {
      const destination = index + direction;
      if (destination < 0 || destination >= current.length) return current;
      const next = [...current];
      [next[index], next[destination]] = [next[destination], next[index]];
      return next.map((scope, sort_order) => ({ ...scope, sort_order }));
    });
  }

  async function submit() {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      await onIssue({
        case_id: caseId,
        certificate_type: readiness.certificate_type,
        issuance_basis: readiness.issuance_basis,
        certificate_number: certificateNumber.trim() || null,
        issue_date: issueDate || null,
        expiry_date: expiryDate || null,
        scopes: scopes.map((scope) => ({
          scope_key: scope.scope_key?.trim() || null,
          scope_text: scope.scope_text,
          language_code: scope.language_code,
          sort_order: scope.sort_order,
        })),
        reason: reason.trim() || null,
      });
      onClose();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Không thể cấp giấy chứng nhận.");
    } finally {
      setPending(false);
    }
  }

  return <div className="dialog-backdrop" role="presentation">
    <section aria-labelledby="gxp-certificate-issue-title" aria-modal="true" className="panel certificate-edit-dialog" role="dialog">
      <header className="panel-header certificate-edit-dialog-header">
        <div><h2 id="gxp-certificate-issue-title">Cấp giấy chứng nhận GxP</h2><p>Loại GxP và điều kiện cấp do backend xác định theo hồ sơ kiểm tra đang chọn.</p></div>
      </header>
      <div className="certificate-edit-fields">
        <label>Loại GxP<span aria-label="Loại GxP" className="certificate-readonly-value">{readiness.certificate_type}</span></label>
        <label>Số GCN<input aria-label="Số GCN" disabled={pending} onChange={(event) => setCertificateNumber(event.target.value)} value={certificateNumber} /></label>
        <label>Ngày cấp<input aria-label="Ngày cấp" disabled={pending} onChange={(event) => setIssueDate(event.target.value)} type="date" value={issueDate} /></label>
        <label>Ngày hết hạn<input aria-label="Ngày hết hạn" disabled={pending} onChange={(event) => setExpiryDate(event.target.value)} type="date" value={expiryDate} /></label>
        <label className="certificate-edit-reason">Lý do cấp<textarea aria-label="Lý do cấp" disabled={pending} onChange={(event) => setReason(event.target.value)} value={reason} /></label>
      </div>
      <section aria-label="Phạm vi chứng nhận có cấu trúc" className="certificate-scope-editor">
        <div className="certificate-scope-editor-header"><h3>Phạm vi chứng nhận</h3><button disabled={pending} onClick={addScope} type="button">Thêm phạm vi</button></div>
        <p className="certificate-scope-note">Khởi tạo rỗng: chưa có ánh xạ nghiệp vụ được xác nhận từ phạm vi đánh giá sang phạm vi chứng nhận.</p>
        {scopes.map((scope, index) => <div className="certificate-scope-row" key={`${scope.sort_order}-${index}`}>
          <label>Mã phạm vi<input aria-label={`Mã phạm vi ${index + 1}`} disabled={pending} onChange={(event) => updateScope(index, "scope_key", event.target.value)} value={scope.scope_key ?? ""} /></label>
          <label>Nội dung phạm vi<textarea aria-label={`Nội dung phạm vi ${index + 1}`} disabled={pending} onChange={(event) => updateScope(index, "scope_text", event.target.value)} value={scope.scope_text} /></label>
          <label>Ngôn ngữ<input aria-label={`Ngôn ngữ phạm vi ${index + 1}`} disabled={pending} onChange={(event) => updateScope(index, "language_code", event.target.value)} value={scope.language_code} /></label>
          <div aria-label={`Thứ tự phạm vi ${index + 1}`} className="certificate-scope-order">{scope.sort_order}</div>
          <div className="certificate-scope-actions">
            <button aria-label={`Đưa phạm vi ${index + 1} lên`} disabled={pending || index === 0} onClick={() => moveScope(index, -1)} type="button">Lên</button>
            <button aria-label={`Đưa phạm vi ${index + 1} xuống`} disabled={pending || index === scopes.length - 1} onClick={() => moveScope(index, 1)} type="button">Xuống</button>
            <button aria-label={`Xóa phạm vi ${index + 1}`} disabled={pending} onClick={() => setScopes((current) => current.filter((_, scopeIndex) => scopeIndex !== index).map((scope, sort_order) => ({ ...scope, sort_order })))} type="button">Xóa</button>
          </div>
        </div>)}
      </section>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <div className="panel-actions certificate-edit-dialog-actions">
        <button disabled={pending} onClick={() => void submit()} type="button">{pending ? "Đang cấp..." : "Cấp giấy chứng nhận"}</button>
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
  const [open, setOpen] = useState(false);
  if (!readiness || readiness.action_key !== "issue_certificate") return null;
  return <section className="workspace-section certificate-issue-section">
    <div className="certificate-action-bar">
      <button disabled={!readiness.available} onClick={() => setOpen(true)} title={readiness.reason_code ?? undefined} type="button">{readiness.label}</button>
      {!readiness.available && readiness.reason_code ? <span>{readiness.reason_code}</span> : null}
    </div>
    {open ? <CertificateIssueDialog caseId={caseId} onClose={() => setOpen(false)} onIssue={onIssue} readiness={readiness} /> : null}
  </section>;
}
