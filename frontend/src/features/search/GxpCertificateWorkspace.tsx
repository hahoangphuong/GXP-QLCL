import { useEffect, useState } from "react";

import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { formatCompactDate } from "../../lib/presentation";
import type { CertificateLatestVersionUpsertRequest, CertificateScope, GxpCertificateDetail, GxpCertificateListItem } from "../../types";
import { GxpCertificateDetailFields } from "./GxpCertificateDetailFields";

type ScopeDraft = Omit<CertificateScope, "id">;

function buildScopeDrafts(scopes: CertificateScope[]): ScopeDraft[] {
  return scopes.map((scope) => ({
    scope_key: scope.scope_key,
    scope_text: scope.scope_text,
    language_code: scope.language_code,
    sort_order: scope.sort_order,
  }));
}

function GxpCertificateEditDialog({ detail, expectedVersion, onClose, onSave, onStaleConflict }: {
  detail: GxpCertificateDetail;
  expectedVersion: number;
  onClose: () => void;
  onSave: (payload: CertificateLatestVersionUpsertRequest) => Promise<void>;
  onStaleConflict: (message: string) => void;
}) {
  const [certificateNumber, setCertificateNumber] = useState(detail.certificate_number ?? "");
  const [issueDate, setIssueDate] = useState(detail.issue_date ?? "");
  const [expiryDate, setExpiryDate] = useState(detail.expiry_date ?? "");
  const [reason, setReason] = useState("");
  const [scopes, setScopes] = useState<ScopeDraft[]>(() => buildScopeDrafts(detail.scopes));
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
      sort_order: Math.max(-1, ...current.map((scope) => scope.sort_order)) + 1,
    }]);
  }

  function moveScope(index: number, direction: -1 | 1) {
    setScopes((current) => {
      const destination = index + direction;
      if (destination < 0 || destination >= current.length) return current;
      const next = [...current];
      [next[index], next[destination]] = [next[destination], next[index]];
      return next.map((scope, sortOrder) => ({ ...scope, sort_order: sortOrder }));
    });
  }

  async function submit() {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      await onSave({
        expected_version: expectedVersion,
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
      const apiError = nextError as Error & { status?: number };
      if (apiError.status === 409) {
        onStaleConflict(apiError.message);
        return;
      }
      setError(nextError instanceof Error ? nextError.message : "Không thể cập nhật giấy chứng nhận.");
    } finally {
      setPending(false);
    }
  }

  return <div className="dialog-backdrop" role="presentation">
    <section aria-labelledby="gxp-certificate-edit-title" aria-modal="true" className="panel certificate-edit-dialog" role="dialog">
      <header className="panel-header certificate-edit-dialog-header">
        <div><h2 id="gxp-certificate-edit-title">Sửa giấy chứng nhận GxP</h2><p>Thay đổi phiên bản hiện tại theo quyền và trạng thái do backend xác nhận.</p></div>
      </header>
      <div className="certificate-edit-fields">
        <label>Số GCN<input aria-label="Số GCN" disabled={pending} onChange={(event) => setCertificateNumber(event.target.value)} value={certificateNumber} /></label>
        <label>Ngày cấp<input aria-label="Ngày cấp" disabled={pending} onChange={(event) => setIssueDate(event.target.value)} type="date" value={issueDate} /></label>
        <label>Ngày hết hạn<input aria-label="Ngày hết hạn" disabled={pending} onChange={(event) => setExpiryDate(event.target.value)} type="date" value={expiryDate} /></label>
        <label className="certificate-edit-reason">Lý do cập nhật<textarea aria-label="Lý do cập nhật" disabled={pending} onChange={(event) => setReason(event.target.value)} value={reason} /></label>
      </div>
      <section aria-label="Phạm vi chứng nhận có cấu trúc" className="certificate-scope-editor">
        <div className="certificate-scope-editor-header"><h3>Phạm vi chứng nhận</h3><button disabled={pending} onClick={addScope} type="button">Thêm phạm vi</button></div>
        {scopes.map((scope, index) => <div className="certificate-scope-row" key={`${scope.sort_order}-${index}`}>
          <label>Mã phạm vi<input aria-label={`Mã phạm vi ${index + 1}`} disabled={pending} onChange={(event) => updateScope(index, "scope_key", event.target.value)} value={scope.scope_key ?? ""} /></label>
          <label>Nội dung phạm vi<textarea aria-label={`Nội dung phạm vi ${index + 1}`} disabled={pending} onChange={(event) => updateScope(index, "scope_text", event.target.value)} value={scope.scope_text} /></label>
          <label>Ngôn ngữ<input aria-label={`Ngôn ngữ phạm vi ${index + 1}`} disabled={pending} onChange={(event) => updateScope(index, "language_code", event.target.value)} value={scope.language_code} /></label>
          <div aria-label={`Thứ tự phạm vi ${index + 1}`} className="certificate-scope-order">{scope.sort_order}</div>
          <div className="certificate-scope-actions">
            <button aria-label={`Đưa phạm vi ${index + 1} lên`} disabled={pending || index === 0} onClick={() => moveScope(index, -1)} type="button">Lên</button>
            <button aria-label={`Đưa phạm vi ${index + 1} xuống`} disabled={pending || index === scopes.length - 1} onClick={() => moveScope(index, 1)} type="button">Xuống</button>
            <button aria-label={`Xóa phạm vi ${index + 1}`} disabled={pending} onClick={() => setScopes((current) => current.filter((_, scopeIndex) => scopeIndex !== index))} type="button">Xóa</button>
          </div>
        </div>) }
      </section>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <div className="panel-actions certificate-edit-dialog-actions">
        <button disabled={pending} onClick={() => void submit()} type="button">{pending ? "Đang lưu..." : "Lưu thay đổi"}</button>
        <button disabled={pending} onClick={onClose} type="button">Hủy</button>
      </div>
    </section>
  </div>;
}

export function GxpCertificateWorkspace({
  items,
  listLoading,
  listError,
  selectedCertificateId,
  onSelectCertificate,
  detail,
  detailLoading,
  detailError,
  onPromoteCurrent,
  promotionError,
  promotionPending,
  onEditLatestVersion,
}: {
  items: GxpCertificateListItem[];
  listLoading: boolean;
  listError: string | null;
  selectedCertificateId: string | null;
  onSelectCertificate: (certificateId: string) => void;
  detail: GxpCertificateDetail | null;
  detailLoading: boolean;
  detailError: string | null;
  onPromoteCurrent: (expectedVersion: number) => Promise<void>;
  promotionError: string | null;
  promotionPending: boolean;
  onEditLatestVersion: (payload: CertificateLatestVersionUpsertRequest) => Promise<void>;
}) {
  const [editOpen, setEditOpen] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  useEffect(() => setEditOpen(false), [detail?.certificate_id, detail?.row_version]);
  if (listError) {
    return <ErrorState message={listError} />;
  }

  if (listLoading && items.length === 0) {
    return <EmptyState title="Đang tải giấy chứng nhận GxP" description="Đang đồng bộ danh mục chứng nhận và chi tiết theo ngữ cảnh đang chọn." />;
  }

  if (!listLoading && items.length === 0) {
    return <EmptyState title="Chưa có giấy chứng nhận GxP" description="Cơ sở hoặc dây chuyền đang chọn chưa có chứng nhận GxP trong dữ liệu hiện hành." />;
  }

  return (
    <div className="certificate-workspace-split master-detail-split master-detail-split-certificate">
      <section className="panel panel-tight certificate-list-panel master-list-pane">
        <div className="panel-header">
          <h3>Danh mục GCN GxP</h3>
          <span className="panel-meta">{items.length} giấy</span>
        </div>
        <div className="table-scroll table-scroll-history">
          <table className="dense-table certificate-history-table">
            <colgroup>
              <col className="col-line" />
              <col className="col-cert-number" />
              <col className="col-date" />
            </colgroup>
            <thead>
              <tr>
                <th className="col-line">DC</th>
                <th className="col-cert-number">Số GCN</th>
                <th className="col-date">Ngày cấp</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  aria-selected={selectedCertificateId === item.certificate_id}
                  className={selectedCertificateId === item.certificate_id ? "selected" : ""}
                  key={item.certificate_id}
                  onClick={() => onSelectCertificate(item.certificate_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelectCertificate(item.certificate_id);
                    }
                  }}
                  tabIndex={0}
                >
                  <td title={item.line_code ?? "Toàn cơ sở"}>
                    {item.line_code ?? (item.context_match_kind === "site_wide" ? "Toàn cơ sở" : "Cơ sở")}
                  </td>
                  <td title={item.certificate_number ?? ""}>
                    <div className="cell-stack">
                      <strong>{item.certificate_number ?? "Chưa có"}</strong>
                      {item.latest_flag ? <span>Hiện hành</span> : null}
                    </div>
                  </td>
                  <td>{formatCompactDate(item.issue_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel panel-tight certificate-detail-panel detail-pane">
        {detailError ? (
          <ErrorState message={detailError} />
        ) : detailLoading || !detail ? (
          <EmptyState title="Đang tải chi tiết GxP" description="Đang lấy chi tiết giấy chứng nhận đang chọn." />
        ) : (
          <>
            <GxpCertificateDetailFields detail={detail} />
            {(() => {
              const promote = (detail.action_readiness ?? []).find((action) => action.action_key === "promote_current");
              const edit = (detail.action_readiness ?? []).find((action) => action.action_key === "edit_latest_version");
              if (!promote && !edit) return null;
              return (
                <div className="certificate-action-bar">
                  {edit ? <button disabled={!edit.available || promotionPending} onClick={() => { setEditError(null); setEditOpen(true); }} title={edit.reason_code ?? undefined} type="button">{edit.label}</button> : null}
                  {!edit?.available && edit?.reason_code ? <span>{edit.reason_code}</span> : null}
                  {editError ? <span role="alert">{editError}</span> : null}
                  {promote ? <button
                    disabled={!promote.available || promotionPending}
                    onClick={() => void onPromoteCurrent(promote.expected_version)}
                    title={promote.reason_code ?? undefined}
                    type="button"
                  >
                    {promotionPending ? "Đang cập nhật..." : promote.label}
                  </button> : null}
                  {!promote?.available && promote?.reason_code ? <span>{promote.reason_code}</span> : null}
                  {promotionError ? <span role="alert">{promotionError}</span> : null}
                </div>
              );
            })()}
            {(() => {
              const edit = (detail.action_readiness ?? []).find((action) => action.action_key === "edit_latest_version");
              return edit && editOpen ? <GxpCertificateEditDialog detail={detail} expectedVersion={edit.expected_version} onClose={() => setEditOpen(false)} onSave={onEditLatestVersion} onStaleConflict={(message) => { setEditOpen(false); setEditError(message); }} /> : null;
            })()}
          </>
        )}
      </section>
    </div>
  );
}
