import { PersistedCertificateHistory } from "./PersistedCertificateHistory";
import type { HistoryState } from "./usePersistedCertificateHistory";
import type { BusinessEligibilityVersionHistory } from "../../types";
import { useEffect, useId, useRef, useState } from "react";

import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { formatCompactDate } from "../../lib/presentation";
import type {
  BusinessEligibilityDetail,
  BusinessEligibilityIssueActionReadiness,
  BusinessEligibilityIssueRequest,
  BusinessEligibilityLatestVersionUpsertRequest,
  BusinessEligibilityListItem,
  GxpCertificateListItem,
} from "../../types";
import { BusinessEligibilityBasisFields, BusinessEligibilityFacilityFields } from "./BusinessEligibilityDetailFields";
import { DetailValue } from "./DetailValue";
import { useCertificateRows } from "./useCertificateRows";
import { useCertificateDialogFocus } from "./useCertificateDialogFocus";
import { BusinessEligibilitySourceEvidence } from "./BusinessEligibilitySourceEvidence";
import type { EligibilitySourceState } from "./useBusinessEligibilitySourceEvidence";
import { CertificateDocumentMetadata } from "./CertificateDocumentMetadata";
import { useFacilityCommandLock } from "./CaseDraftSession";
import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";
import type { CertificateDocumentMetadataState } from "./useCertificateDocumentMetadata";

type LinkDraft = { certificate_id: string; link_role: string };

function buildLinkDrafts(detail: BusinessEligibilityDetail | null): LinkDraft[] {
  return (detail?.linked_gxp_certificates ?? []).map((item) => ({
    certificate_id: item.certificate_id,
    link_role: item.link_role,
  }));
}

export function BusinessEligibilityMutationDialog({
  mode,
  detail,
  expectedVersion,
  basisCertificates,
  basisLoading,
  basisError,
  onClose,
  onIssue,
  onEdit,
  onStaleConflict,
  saveAvailable = true,
  issueRequiresReview = false,
}: {
  mode: "issue" | "edit";
  detail: BusinessEligibilityDetail | null;
  expectedVersion: number | null;
  basisCertificates: GxpCertificateListItem[];
  basisLoading: boolean;
  basisError: string | null;
  onClose: () => void;
  onIssue: (payload: BusinessEligibilityIssueRequest) => Promise<void>;
  onEdit: (payload: BusinessEligibilityLatestVersionUpsertRequest) => Promise<void>;
  onStaleConflict: (message: string) => void;
  saveAvailable?: boolean;
  issueRequiresReview?: boolean;
}) {
  const [certificateNumber, setCertificateNumber] = useState(detail?.certificate_number ?? "");
  const [issuedOn, setIssuedOn] = useState(detail?.issued_on ?? "");
  const [expiresOn, setExpiresOn] = useState(detail?.expires_on ?? "");
  const [responsiblePerson, setResponsiblePerson] = useState(detail?.professional_responsible_person_name ?? "");
  const [notes, setNotes] = useState(detail?.notes ?? "");
  const [reason, setReason] = useState("");
  const [links, setLinks] = useState<LinkDraft[]>(() => buildLinkDrafts(detail));
  const [pending, setPending] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [conflicted, setConflicted] = useState(false);
  const dialogRef = useCertificateDialogFocus();
  const editLock = useFacilityCommandLock(`business-eligibility.write:${detail?.business_eligibility_certificate_id ?? "none"}`);
  const requiresReview = mode === "edit" ? editLock.requiresReview : issueRequiresReview;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !pending && !requiresReview) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, pending, requiresReview]);

  function selectedRole(certificateId: string): string | null {
    return links.find((item) => item.certificate_id === certificateId)?.link_role ?? null;
  }

  function toggleCertificate(certificateId: string) {
    if (requiresReview) return;
    setLinks((current) => current.some((item) => item.certificate_id === certificateId)
      ? current.filter((item) => item.certificate_id !== certificateId)
      : [...current, { certificate_id: certificateId, link_role: "source_certificate" }]);
  }

  function updateRole(certificateId: string, linkRole: string) {
    if (requiresReview) return;
    setLinks((current) => current.map((item) =>
      item.certificate_id === certificateId ? { ...item, link_role: linkRole } : item));
  }

  async function submit() {
    if (inFlight.current || conflicted || !saveAvailable || requiresReview || (mode === "edit" && editLock.pending)) return;
    const command = mode === "edit" ? editLock.acquire() : null;
    if (mode === "edit" && !command) return;
    if (mode === "edit" && expectedVersion === null) {
      setError("Thiếu phiên bản đồng bộ để cập nhật GCN đủ điều kiện.");
      return;
    }
    inFlight.current = true;
    setPending(true);
    setError(null);
    const common: BusinessEligibilityIssueRequest = {
      certificate_number: certificateNumber.trim() || null,
      issued_on: issuedOn || null,
      expires_on: expiresOn || null,
      professional_responsible_person_name: responsiblePerson.trim() || null,
      notes: notes.trim() || null,
      linked_certificates: links,
      reason: reason.trim() || null,
    };
    try {
      if (mode === "issue") {
        await onIssue(common);
      } else {
        await onEdit({ ...common, expected_version: expectedVersion as number });
      }
      onClose();
    } catch (nextError) {
      if (nextError instanceof CaseFieldMutationRecoveryError && command) editLock.requireReview(command);
      const apiError = nextError as Error & { status?: number };
      if (mode === "edit" && apiError.status === 409) {
        setError(apiError.message);
        setConflicted(true);
        onStaleConflict(apiError.message);
        return;
      }
      setError(nextError instanceof Error ? nextError.message : "Không thể lưu GCN đủ điều kiện.");
    } finally {
      if (command) editLock.release(command);
      inFlight.current = false;
      setPending(false);
    }
  }

  return <div className="dialog-backdrop" role="presentation">
    <section ref={dialogRef} tabIndex={-1} aria-labelledby="business-eligibility-mutation-title" aria-modal="true" className="panel certificate-edit-dialog" role="dialog">
      <header className="panel-header certificate-edit-dialog-header">
        <div>
          <h2 id="business-eligibility-mutation-title">{mode === "issue" ? "Cấp GCN đủ điều kiện" : "Cập nhật GCN đủ điều kiện"}</h2>
          <p>Cấp mới, cập nhật phiên bản và đặt hiện hành là các thao tác độc lập.</p>
        </div>
      </header>
      <div className="certificate-edit-fields">
        <label>Số GCN<input aria-label="Số GCN ĐĐK" readOnly={requiresReview} disabled={pending} onChange={(event) => { if (!requiresReview) setCertificateNumber(event.target.value); }} value={certificateNumber} /></label>
        <label>Ngày cấp<input aria-label="Ngày cấp ĐĐK" readOnly={requiresReview} disabled={pending} onChange={(event) => { if (!requiresReview) setIssuedOn(event.target.value); }} type="date" value={issuedOn} /></label>
        <label>Ngày hết hạn<input aria-label="Ngày hết hạn ĐĐK" readOnly={requiresReview} disabled={pending} onChange={(event) => { if (!requiresReview) setExpiresOn(event.target.value); }} type="date" value={expiresOn} /></label>
        <label>Người PTCM<input aria-label="Người PTCM" readOnly={requiresReview} disabled={pending} onChange={(event) => { if (!requiresReview) setResponsiblePerson(event.target.value); }} value={responsiblePerson} /></label>
        <label>Ghi chú<textarea aria-label="Ghi chú ĐĐK" readOnly={requiresReview} disabled={pending} onChange={(event) => { if (!requiresReview) setNotes(event.target.value); }} value={notes} /></label>
        <label className="certificate-edit-reason">Lý do<textarea aria-label="Lý do ĐĐK" readOnly={requiresReview} disabled={pending} onChange={(event) => { if (!requiresReview) setReason(event.target.value); }} value={reason} /></label>
      </div>
      <section aria-label="GCN GxP làm căn cứ" className="certificate-scope-editor">
        <div className="certificate-scope-editor-header"><h3>GCN GxP làm căn cứ</h3></div>
        {basisLoading ? <p className="workspace-note">Đang tải danh sách GxP…</p> : null}
        {basisError ? <p className="form-error" role="alert">{basisError}</p> : null}
        {!basisLoading && !basisError && basisCertificates.length === 0 ? <p className="workspace-note">Chưa có GCN GxP canonical để chọn làm căn cứ.</p> : null}
        {basisCertificates.map((certificate) => {
          const role = selectedRole(certificate.certificate_id);
          const label = `${certificate.certificate_type} ${certificate.line_code ?? "toàn cơ sở"} · ${certificate.certificate_number ?? certificate.certificate_id}`;
          return <div className="certificate-scope-row" key={certificate.certificate_id}>
            <label>
              <input
                aria-label={`Chọn căn cứ ${label}`}
                checked={role !== null}
                disabled={pending || requiresReview}
                onChange={() => toggleCertificate(certificate.certificate_id)}
                type="checkbox"
              />
              {label}
            </label>
            {role !== null ? <label>Vai trò
              <select aria-label={`Vai trò căn cứ ${label}`} disabled={pending || requiresReview} onChange={(event) => updateRole(certificate.certificate_id, event.target.value)} value={role}>
                <option value="source_certificate">source_certificate</option>
                <option value="replacement_certificate">replacement_certificate</option>
              </select>
            </label> : null}
          </div>;
        })}
      </section>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {conflicted ? <p className="workspace-note">Bản nháp được giữ để đối chiếu. Sao chép nội dung cần giữ, đóng và mở lại form sau khi kiểm tra dữ liệu mới.</p> : null}
      {requiresReview ? <p className="workspace-note" role="status">Kết quả ghi GCN đủ điều kiện chưa xác minh. Giữ nguyên dữ liệu đã gửi để sao chép và đối chiếu canonical; không sửa, hủy hoặc gửi lại.</p> : null}
      <div className="panel-actions certificate-edit-dialog-actions">
        <button disabled={pending || conflicted || !saveAvailable || requiresReview || (mode === "edit" && editLock.pending)} onClick={() => void submit()} type="button">{pending ? "Đang lưu..." : mode === "issue" ? "Cấp GCN" : "Lưu thay đổi"}</button>
        <button disabled={pending || requiresReview} onClick={onClose} type="button">Hủy</button>
      </div>
    </section>
  </div>;
}

export function BusinessEligibilityWorkspace({
  siteId,
  versionHistory,
  documentMetadata,
  sourceEvidence,
  items,
  listLoading,
  listError,
  selectedCertificateId,
  onSelectCertificate,
  detail,
  detailLoading,
  detailError,
  issueReadiness,
  basisCertificates,
  basisLoading,
  basisError,
  onIssue,
  onEditLatestVersion,
  onPromoteCurrent,
  promotionError,
  promotionPending,
}: {
  siteId: string;
  versionHistory?: HistoryState<BusinessEligibilityVersionHistory>;
  documentMetadata?: CertificateDocumentMetadataState;
  sourceEvidence?: EligibilitySourceState;
  items: BusinessEligibilityListItem[];
  listLoading: boolean;
  listError: string | null;
  selectedCertificateId: string | null;
  onSelectCertificate: (certificateId: string) => void;
  detail: BusinessEligibilityDetail | null;
  detailLoading: boolean;
  detailError: string | null;
  issueReadiness: BusinessEligibilityIssueActionReadiness | null;
  basisCertificates: GxpCertificateListItem[];
  basisLoading: boolean;
  basisError: string | null;
  onIssue: (payload: BusinessEligibilityIssueRequest) => Promise<void>;
  onEditLatestVersion: (payload: BusinessEligibilityLatestVersionUpsertRequest) => Promise<void>;
  onPromoteCurrent: (expectedVersion: number) => Promise<void>;
  promotionError: string | null;
  promotionPending: boolean;
}) {
  const [issueIntent, setIssueIntent] = useState<{ siteId: string; owner: string | null } | null>(null);
  const issueLock = useFacilityCommandLock(`business-eligibility.issue:${siteId}`);
  const certificateLock = useFacilityCommandLock(`business-eligibility.write:${selectedCertificateId ?? "none"}`);
  async function promoteOwned(expectedVersion: number) {
    const command = certificateLock.acquire();
    if (!command) return;
    try {
      await onPromoteCurrent(expectedVersion);
    } catch (error) {
      if (error instanceof CaseFieldMutationRecoveryError) certificateLock.requireReview(command);
    } finally {
      certificateLock.release(command);
    }
  }
  async function issueOwned(payload: BusinessEligibilityIssueRequest) {
    const command = issueLock.acquire();
    if (!command) throw new CaseFieldMutationRecoveryError("Chưa xác minh kết quả cấp GCN đủ điều kiện trước; không gửi lại.");
    try {
      await onIssue(payload);
    } catch (error) {
      if (error instanceof CaseFieldMutationRecoveryError) issueLock.requireReview(command);
      throw error;
    } finally {
      issueLock.release(command);
    }
  }
  if (issueIntent && (issueIntent.siteId !== siteId || issueIntent.owner !== issueLock.owner)) setIssueIntent(null);
  const [editDraft, setEditDraft] = useState<{ detail: BusinessEligibilityDetail; expectedVersion: number } | null>(null);
  const [draftSelection, setDraftSelection] = useState(selectedCertificateId);
  if (draftSelection !== selectedCertificateId) {
    setDraftSelection(selectedCertificateId);
    setEditDraft(null);
  }
  const hintId = useId();
  const rowProps = useCertificateRows(items.map((item) => item.business_eligibility_certificate_id), selectedCertificateId, onSelectCertificate, listLoading || Boolean(listError));
  detail = detail?.business_eligibility_certificate_id === selectedCertificateId ? detail : null;
  const visibleDraft = editDraft?.detail.business_eligibility_certificate_id === selectedCertificateId ? editDraft : null;

  const actions = detail?.action_readiness ?? [];
  const edit = actions.find((action) => action.action_key === "edit_latest_version");
  const promote = actions.find((action) => action.action_key === "promote_current");

  return (
    <div className="eligibility-workspace-split master-detail-split master-detail-split-eligibility facility-ddk-workspace">
      <section className="panel panel-tight certificate-list-panel master-list-pane">
        <div className="panel-header">
          <div><h3>Danh mục GCN đủ điều kiện</h3><span className="panel-meta">{items.length} giấy</span></div>
          {issueReadiness ? <button
            disabled={!issueReadiness.available || promotionPending || issueLock.pending || issueLock.requiresReview}
            onClick={() => setIssueIntent({ siteId, owner: issueLock.owner })}
            title={issueReadiness.reason_code ?? undefined}
            type="button"
          >{issueReadiness.label}</button> : null}
        </div>
        {issueLock.requiresReview ? <p role="alert">Chưa xác minh kết quả cấp GCN đủ điều kiện trước; không gửi lại.</p> : null}
        <p className="workspace-note" id={hintId}>↑/↓, Home/End: di chuyển · Enter/Space: chọn giấy</p>
        {listError ? <ErrorState message={listError} /> : null}
        {listLoading && items.length > 0 ? <p role="status" className="workspace-note">Đang tải danh mục ĐĐK…</p> : null}
        {!issueReadiness?.available && issueReadiness?.reason_code ? <p className="workspace-note">{issueReadiness.reason_code}</p> : null}
        {listLoading && items.length === 0 ? <EmptyState title="Đang tải GCN đủ điều kiện" description="Đang đồng bộ danh mục chứng nhận của cơ sở." /> : null}
        {!listLoading && !listError && items.length === 0 ? <EmptyState title="Chưa có GCN đủ điều kiện" description="Có thể cấp bản ghi mới nếu backend cho phép thao tác cấp." /> : null}
        {items.length > 0 ? <div className="table-scroll table-scroll-history">
          <table aria-label="Danh mục GCN đủ điều kiện" aria-describedby={hintId} aria-busy={listLoading} className="dense-table certificate-history-table">
            <colgroup><col className="col-cert-number" /><col className="col-date" /><col className="col-line" /></colgroup>
            <thead><tr><th className="col-cert-number">Số GCN</th><th className="col-date">Ngày cấp</th><th className="col-line">Lần</th></tr></thead>
            <tbody>
              {items.map((item) => <tr
                aria-selected={selectedCertificateId === item.business_eligibility_certificate_id}
                className={selectedCertificateId === item.business_eligibility_certificate_id ? "selected" : ""}
                key={item.business_eligibility_certificate_id}
                {...rowProps(item.business_eligibility_certificate_id)}
              >
                <td><div className="cell-stack"><strong>{item.certificate_number ?? "Chưa có"}</strong>{item.latest_flag ? <span>Hiện hành</span> : null}</div></td>
                <td>{formatCompactDate(item.issued_on)}</td>
                <td>{item.issuance_sequence_text ?? "—"}</td>
              </tr>)}
            </tbody>
          </table>
        </div> : null}
        {detail && !detailLoading && !detailError ? <div className="facility-ddk-dossier">
          <DetailValue label="Hồ sơ đề nghị" value={detail.application_dossier_reference} />
          <DetailValue label="Người xử lý" value={detail.handled_by_name} />
          <BusinessEligibilityBasisFields detail={detail} />
        </div> : null}
      </section>

      <section className="panel panel-tight certificate-detail-panel detail-pane">
        {detailError ? <ErrorState message={detailError} /> : detailLoading || (selectedCertificateId && !detail) ? (
          <EmptyState title="Đang tải chi tiết GCN đủ điều kiện" description="Đang lấy chi tiết giấy đang chọn." />
        ) : !detail ? (
          <EmptyState title="Chưa chọn GCN đủ điều kiện" description="Chọn một giấy trong danh mục hoặc cấp giấy mới." />
        ) : (
          <>
            <BusinessEligibilityFacilityFields detail={detail} />
            {sourceEvidence ? <BusinessEligibilitySourceEvidence state={sourceEvidence} /> : null}
            {documentMetadata ? <CertificateDocumentMetadata state={documentMetadata} /> : null}
            <div className="certificate-action-bar">
              {edit ? <button disabled={!edit.available || promotionPending || certificateLock.pending || certificateLock.requiresReview} onClick={() => setEditDraft({ detail, expectedVersion: edit.expected_version })} title={edit.reason_code ?? undefined} type="button">{edit.label}</button> : null}
              {!edit?.available && edit?.reason_code ? <span>{edit.reason_code}</span> : null}
              {promote ? <button disabled={!promote.available || promotionPending || certificateLock.pending || certificateLock.requiresReview} onClick={() => void promoteOwned(promote.expected_version)} title={promote.reason_code ?? undefined} type="button">{promotionPending ? "Đang cập nhật..." : promote.label}</button> : null}
              {!promote?.available && promote?.reason_code ? <span>{promote.reason_code}</span> : null}
              {promotionError ? <span role="alert">{promotionError}</span> : null}
              {certificateLock.requiresReview ? <span className="workspace-note" role="status">Chưa xác minh kết quả cập nhật hoặc đặt hiện hành GCN đủ điều kiện. Không gửi lại; đối chiếu Certificate canonical.</span> : null}
            </div>
          </>
        )}
        {selectedCertificateId && versionHistory ? <PersistedCertificateHistory kind="ddk" state={versionHistory} /> : null}
      </section>

      {issueIntent && issueIntent.siteId === siteId && issueIntent.owner === issueLock.owner ? <BusinessEligibilityMutationDialog
        basisCertificates={basisCertificates}
        basisError={basisError}
        basisLoading={basisLoading}
        detail={null}
        expectedVersion={null}
        mode="issue"
        saveAvailable={issueReadiness?.available === true && !issueLock.pending && !issueLock.requiresReview}
        issueRequiresReview={issueLock.requiresReview}
        onClose={() => setIssueIntent(current => current === issueIntent ? null : current)}
        onEdit={onEditLatestVersion}
        onIssue={issueOwned}
        onStaleConflict={() => undefined}
      /> : null}

      {visibleDraft ? <BusinessEligibilityMutationDialog
        basisCertificates={basisCertificates}
        basisError={basisError}
        basisLoading={basisLoading}
        detail={visibleDraft.detail}
        expectedVersion={visibleDraft.expectedVersion}
        mode="edit"
        saveAvailable={!detailLoading && edit?.available === true && !certificateLock.pending && !certificateLock.requiresReview}
        onClose={() => setEditDraft(current => current === visibleDraft ? null : current)}
        onEdit={onEditLatestVersion}
        onIssue={onIssue}
        onStaleConflict={() => undefined}
      /> : null}
    </div>
  );
}
