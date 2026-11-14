import { useState } from "react";

import type { CaseNonissuanceDecisionRead, CaseNonissuanceDecisionRecordRequest, CaseWorkspace } from "../../types";
import { formatCompactDate } from "../../lib/presentation";
import { useCaseCommandLock, useCaseDraftState } from "./CaseDraftSession";

type Props = {
  caseWorkspace: CaseWorkspace;
  onRecord: (payload: CaseNonissuanceDecisionRecordRequest) => Promise<CaseNonissuanceDecisionRead>;
};

function errorText(error: unknown) {
  const status = (error as Error & { status?: number }).status;
  if (status === 403) return "Bạn không có quyền ghi nhận quyết định không cấp giấy chứng nhận.";
  if (status === 404) return "Không tìm thấy hồ sơ đã chọn.";
  if (status === 409) return "Phiên bản hồ sơ đã thay đổi, hồ sơ đã có quyết định hoặc chưa đủ điều kiện ghi nhận.";
  if (status === 422) return "Dữ liệu quyết định không hợp lệ hoặc hồ sơ chưa đáp ứng điều kiện nghiệp vụ.";
  return error instanceof Error ? error.message : "Không thể ghi nhận quyết định.";
}

export function CaseNonissuanceDecisionWorkspace({ caseWorkspace, onRecord }: Props) {
  const caseId = caseWorkspace.case_summary.id;
  const envelope = caseWorkspace.nonissuance_decision;
  const existing = envelope?.case_id === caseId ? envelope.decision : null;
  const mismatch = Boolean(envelope && envelope.case_id !== caseId);
  const readiness = caseWorkspace.nonissuance_record_readiness;
  const ready = readiness?.case_id === caseId
    && readiness.action_key === "record_certificate_nonissuance_decision"
    && readiness.available && readiness.expected_case_version === caseWorkspace.case_summary.row_version;
  const blockerMessages: Record<string, string> = {
    missing_permission: "Bạn không có quyền ghi nhận quyết định không cấp GCN.",
    case_state_not_eligible: "Hồ sơ chưa ở trạng thái chờ quyết định GCN.",
    nonissuance_already_recorded: "Hồ sơ đã có quyết định không cấp được ghi nhận.",
    final_evaluation_missing: "Hồ sơ chưa có đánh giá cuối cùng.",
    latest_capa_not_accepted: "CAPA mới nhất chưa được chấp nhận.",
    linked_certificate_exists: "Hồ sơ đã liên kết với một giấy chứng nhận.",
  };
  const lock = useCaseCommandLock(`certificate.nonissuance:${caseId}`);
  const [decidedOn, setDecidedOn] = useCaseDraftState("certificate.nonissuance.decidedOn", "");
  const [reference, setReference] = useCaseDraftState("certificate.nonissuance.reference", "");
  const [explanation, setExplanation] = useCaseDraftState("certificate.nonissuance.explanation", "");
  const [reason, setReason] = useCaseDraftState("certificate.nonissuance.reason", "");
  const [error, setError] = useCaseDraftState<string | null>("certificate.nonissuance.error", null);
  const [recorded, setRecorded] = useState<{ caseId: string; decision: NonNullable<CaseNonissuanceDecisionRead["decision"]> } | null>(null);
  const frozen = lock.pending || lock.requiresReview;
  const candidate = existing ?? (recorded?.caseId === caseId ? recorded.decision : null);

  async function record() {
    if (candidate || frozen || mismatch || !ready || caseWorkspace.case_summary.state !== "awaiting_certificate_decision") return;
    const payload: CaseNonissuanceDecisionRecordRequest = {
      expected_case_version: readiness.expected_case_version,
      decided_on: decidedOn,
      decision_reference: reference.trim(),
      explanation: explanation.trim(),
      reason: reason.trim() || null,
    };
    if (!payload.decided_on || !payload.decision_reference || !payload.explanation) {
      setError("Cần nhập ngày, số tham chiếu và nội dung lý do trước khi ghi nhận.");
      return;
    }
    if (!window.confirm("Ghi nhận quyết định không cấp giấy chứng nhận? Thao tác này không tạo văn bản pháp lý và không thay đổi trạng thái hồ sơ.")) return;
    const token = lock.acquire(payload);
    if (!token) return;
    setError(null);
    try {
      const response = await onRecord(payload);
      if (response.case_id !== caseId || !response.decision
          || response.decision.decided_on !== payload.decided_on
          || response.decision.decision_reference !== payload.decision_reference
          || response.decision.explanation !== payload.explanation) {
        lock.requireReview(token, payload);
        setError("Đã gửi yêu cầu nhưng GET canonical chưa xác nhận đúng quyết định. Không gửi lại tự động.");
        return;
      }
      setRecorded({ caseId, decision: response.decision });
      lock.release(token);
    } catch (requestError) {
      lock.requireReview(token, payload);
      setError(`${errorText(requestError)} Không gửi lại tự động; hãy tải lại để đối chiếu canonical.`);
    }
  }

  return <section className="workspace-section" aria-label="Quyết định không cấp giấy chứng nhận">
    <h4>Quyết định không cấp giấy chứng nhận</h4>
    {candidate ? <dl className="detail-grid"><dt>Ngày quyết định</dt><dd>{formatCompactDate(candidate.decided_on)}</dd><dt>Số tham chiếu</dt><dd>{candidate.decision_reference}</dd><dt>Nội dung lý do</dt><dd>{candidate.explanation}</dd><dt>Tình trạng</dt><dd>Bản ghi quyết định; không phải văn bản đã ban hành và không thay đổi trạng thái hồ sơ.</dd></dl> : <>
      {!ready || mismatch || caseWorkspace.case_summary.state !== "awaiting_certificate_decision" ? <p className="workspace-note" role="status">{mismatch ? "Dữ liệu quyết định không thuộc hồ sơ hiện tại; không thể ghi nhận." : readiness?.reason_code ? blockerMessages[readiness.reason_code] : "Backend chưa xác minh điều kiện ghi nhận cho phiên bản hồ sơ hiện tại."}</p> : <div className="editor-form">
        <label>Ngày quyết định<input aria-label="Ngày quyết định không cấp" type="date" value={decidedOn} disabled={frozen} onChange={event => setDecidedOn(event.target.value)} /></label>
        <label>Số tham chiếu<input aria-label="Số tham chiếu quyết định không cấp" value={reference} disabled={frozen} onChange={event => setReference(event.target.value)} /></label>
        <label>Nội dung lý do<textarea aria-label="Nội dung lý do không cấp" value={explanation} disabled={frozen} onChange={event => setExplanation(event.target.value)} /></label>
        <label>Lý do ghi nhận trên hệ thống<textarea aria-label="Lý do ghi nhận quyết định không cấp" value={reason} disabled={frozen} onChange={event => setReason(event.target.value)} /></label>
        <button type="button" disabled={frozen || !ready} onClick={() => void record()}>{frozen ? "Đang đối chiếu..." : "Ghi nhận quyết định không cấp"}</button>
      </div>}
    </>}
    {error ? <p className="form-error" role="alert">{error}</p> : null}
  </section>;
}
