import { useContext, useState } from "react";
import { useCaseCommandLock, useCaseDraftState } from "./CaseDraftSession";
import { ApprovalMutationContext } from "./approvalMutationRecovery";
import type {
  ApprovalDocumentBindRequest, ApprovalDocumentBindingResponse,
  ApprovalDocumentReadback, CaseWorkspace, InspectionApprovalSubmission,
} from "../../types";

type Props = {
  workspace: CaseWorkspace;
  submission: InspectionApprovalSubmission;
  onBind?: (id: string, payload: ApprovalDocumentBindRequest) => Promise<ApprovalDocumentBindingResponse>;
  onReadback?: (id: string) => Promise<ApprovalDocumentReadback>;
  onConfirmed?: (caseId: string) => Promise<void>;
  onOpenCurrentContent?: (submissionId: string, documentId: string) => Promise<void>;
};

type PendingBinding = {
  caseId: string;
  submissionId: string;
  stage: "PCT" | "CT";
  roundNo: number;
  documentId: string;
  expectedVersion: number;
};

const reasons: Record<string, string> = {
  missing_permission: "Thiếu quyền chỉnh sửa trình phê duyệt hoặc đọc tài liệu.",
  terminal_case: "Hồ sơ đã kết thúc; không được liên kết tài liệu.",
  no_eligible_documents: "Chưa có tài liệu đủ điều kiện để liên kết với lần trình này.",
};

function verifiedBinding(readback: ApprovalDocumentReadback, command: PendingBinding): boolean {
  return readback.case_id === command.caseId
    && readback.approval_submission_id === command.submissionId
    && readback.stage === command.stage
    && readback.round_no === command.roundNo
    && readback.links.some(link =>
      link.approval_submission_id === command.submissionId
      && link.document_id === command.documentId
      && link.stage === command.stage
      && link.round_no === command.roundNo
      && Boolean(link.binding_id));
}

function openErrorMessage(error: unknown): string {
  const status = (error as Error & { status?: unknown }).status;
  if (status === 403) return "Bạn không có quyền đọc tài liệu đã liên kết với lần trình này.";
  if (status === 404) return "Không tìm thấy liên kết tài liệu canonical của lần trình này.";
  if (status === 409) return "Tài liệu đã liên kết chưa có binary hiện hành hợp lệ để mở.";
  if (status === 503) return "Kho lưu trữ tài liệu hiện không khả dụng. Hãy thử lại sau.";
  return error instanceof Error ? error.message : "Không thể mở nội dung tài liệu đã liên kết.";
}

export function ApprovalRoundDocuments({ workspace, submission, onBind, onReadback, onConfirmed, onOpenCurrentContent }: Props) {
  const caseId = workspace.case_summary.id;
  const id = submission.approval_submission_id;
  const label = `${submission.stage} lần ${submission.round_no}`;
  const lock = useCaseCommandLock(`approval.document-bind:${id}`);
  const { pending: approvalPending, requiresReview: approvalReview } = useContext(ApprovalMutationContext);
  const [documentId, setDocumentId] = useCaseDraftState(`approval.document-bind.${id}.selection`, "");
  const [error, setError] = useCaseDraftState<string | null>(`approval.document-bind.${id}.error`, null);
  const [result, setResult] = useCaseDraftState<string | null>(`approval.document-bind.${id}.result`, null);
  const [checking, setChecking] = useState(false);
  const [openingDocumentId, setOpeningDocumentId] = useState<string | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);
  const readiness = (workspace.inspection.approval_document_bind_readiness ?? []).find(item =>
    item.approval_submission_id === id && item.stage === submission.stage
    && item.round_no === submission.round_no);
  const candidates = (workspace.inspection.approval_document_candidates ?? []).filter(item =>
    item.stage === submission.stage
    && item.family_code === (submission.stage === "PCT" ? "INSPECTION_PT_PCT" : "INSPECTION_PT_CT"));
  const links = (workspace.inspection.approval_document_links ?? []).filter(item =>
    item.approval_submission_id === id && item.stage === submission.stage
    && item.round_no === submission.round_no);
  const canonicalCandidates = new Map(candidates.map(item => [item.document_id, item]));
  const choices = candidates.filter(item => readiness?.eligible_document_ids.includes(item.document_id)
    && (item.bound_submission_id === null || item.bound_submission_id === id));
  const selectedEligible = choices.some(item => item.document_id === documentId);
  const blocked = lock.pending || lock.requiresReview || checking || approvalPending || approvalReview;
  const submitted = lock.commandPayload<PendingBinding>();
  const commandOwned = (command: PendingBinding) => command.caseId === caseId
    && command.submissionId === id && command.stage === submission.stage && command.roundNo === submission.round_no;

  async function verify(command: PendingBinding) {
    if (!onReadback || !commandOwned(command)) return false;
    try {
      const receipt = await onReadback(id);
      if (!verifiedBinding(receipt, command)) return false;
      setResult(`Đã xác minh liên kết canonical cho ${label}.`);
      setError(null);
      // Readback is authoritative; a separate workspace refresh may fail
      // without changing its verified outcome.
      if (onConfirmed) {
        try {
          await onConfirmed(caseId);
        } catch {
          // Workspace refresh is secondary to verified targeted GET evidence.
        }
      }
      return true;
    } catch {
      return false;
    }
  }

  async function bind() {
    if (!onBind || !onReadback || blocked || !readiness?.available
        || readiness.expected_version !== submission.row_version || !selectedEligible) return;
    const command: PendingBinding = {
      caseId, submissionId: id, stage: submission.stage,
      roundNo: submission.round_no, documentId, expectedVersion: readiness.expected_version,
    };
    const token = lock.acquire(command);
    if (!token) return;
    setResult(null); setError(null);
    let definitiveRejection = false;
    try {
      const response = await onBind(id, { document_id: documentId, expected_version: command.expectedVersion });
      if (response.approval_submission_id !== id || response.document_id !== documentId
          || !response.binding_id) throw new Error("Binding response does not match submitted canonical IDs.");
      if (!await verify(command)) throw new Error("Canonical readback did not confirm the submitted binding.");
      setDocumentId("");
    } catch (reason) {
      const status = (reason as Error & { status?: number }).status;
      definitiveRejection = status === 403 || status === 404 || status === 409 || status === 422;
      if (definitiveRejection) {
        setError(reason instanceof Error ? reason.message : "Liên kết bị backend từ chối.");
      } else if (await verify(command)) {
        setDocumentId("");
      } else {
        lock.requireReview(token, command);
        setError("Kết quả liên kết chưa xác minh. Không gửi lại POST; chỉ kiểm tra GET canonical.");
      }
    } finally {
      if (definitiveRejection || !lock.requiresReview) lock.release(token);
    }
  }

  async function recheck() {
    if (!lock.requiresReview || !submitted || !commandOwned(submitted) || checking) return;
    setChecking(true);
    try {
      if (await verify(submitted)) {
        lock.clearVerifiedReview();
        setDocumentId("");
      } else {
        setError("Chưa có bằng chứng canonical xác nhận liên kết. Tiếp tục khóa thao tác ghi.");
      }
    } finally {
      setChecking(false);
    }
  }

  async function open(link: typeof links[number]) {
    if (!onOpenCurrentContent || openingDocumentId !== null) return;
    setOpeningDocumentId(link.document_id);
    setOpenError(null);
    try {
      await onOpenCurrentContent(id, link.document_id);
    } catch (error) {
      setOpenError(openErrorMessage(error));
    } finally {
      setOpeningDocumentId(current => current === link.document_id ? null : current);
    }
  }

  // Older canonical projections do not advertise round-level association.
  // Never show a guessed status or an enabled action in that case.
  if (!workspace.inspection.approval_document_candidates
      && !workspace.inspection.approval_document_links
      && !workspace.inspection.approval_document_bind_readiness) return null;

  return <section className="workspace-section" aria-label={`Tài liệu ${label}`}>
    <h5>Tài liệu {label}</h5>
    <p className="workspace-note">Tài liệu cấp hồ sơ và liên kết từng lần trình là hai dữ kiện khác nhau. Liên kết không xác nhận tài liệu đã ký hoặc ban hành.</p>
    {links.length ? <ul aria-label={`Tài liệu đã liên kết ${label}`}>{links.map(link => {
      const source = canonicalCandidates.get(link.document_id);
      return <li key={link.binding_id}>
        {source?.title || link.document_id} — UUID: {link.document_id}
        {source && !source.open_available ? " (chưa có bản hiện hành mở được)" : ""}
        {!source ? " (không còn metadata tài liệu trong Case; cần xác minh)" : ""}
        {onOpenCurrentContent ? <button type="button" className="secondary" disabled={openingDocumentId !== null}
          aria-label={`Mở tài liệu ${link.document_id} của ${label}`}
          onClick={() => void open(link)}>{openingDocumentId === link.document_id ? "Đang mở…" : "Mở tài liệu"}</button> : null}
      </li>;
    })}</ul> : <p className="workspace-note">Chưa có tài liệu được xác minh liên kết tới lần trình này.</p>}
    <p className="workspace-note">Tài liệu {submission.stage} cấp hồ sơ: {candidates.length}; có thể mở theo metadata: {candidates.filter(item => item.open_available).length}.</p>
    {readiness ? <div className="panel-actions">
      <select aria-label={`Chọn tài liệu cho ${label}`} value={documentId} disabled={blocked || !readiness.available || !onBind || !onReadback}
        onChange={event => { setDocumentId(event.target.value); setError(null); }}>
        <option value="">Chọn tài liệu chưa liên kết</option>
        {choices.map(item => <option key={item.document_id} value={item.document_id}>
          {item.title || item.document_id}{item.open_available ? "" : " — chưa có bản mở được"}
        </option>)}
      </select>
      <button type="button" disabled={blocked || !onBind || !onReadback || !readiness.available
        || readiness.expected_version !== submission.row_version || !selectedEligible}
        onClick={() => void bind()}>Liên kết tài liệu với {label}</button>
    </div> : <p className="workspace-note">Chưa có readiness canonical để liên kết tài liệu.</p>}
    {readiness && !readiness.available ? <p className="workspace-note">{reasons[readiness.reason_code ?? ""] ?? "Backend chưa cho phép liên kết tài liệu."}</p> : null}
    {readiness?.available && readiness.expected_version !== submission.row_version
      ? <p className="workspace-note">Phiên bản lần trình không còn khớp readiness; tải lại hồ sơ trước khi liên kết.</p> : null}
    {lock.pending ? <p role="status">Đang gửi và xác minh liên kết canonical.</p> : null}
    {lock.requiresReview ? <div role="status">
      <p>Kết quả POST chưa xác minh. Chỉ sử dụng GET canonical; không gửi lại liên kết.</p>
      <button type="button" disabled={checking || !onReadback || !submitted || !commandOwned(submitted)}
        onClick={() => void recheck()}>{checking ? "Đang đối chiếu" : "Đối chiếu liên kết canonical"}</button>
    </div> : null}
    {result ? <p role="status">{result}</p> : null}
    {error ? <p role="alert" className="form-error">{error}</p> : null}
    {openError ? <p role="alert" className="form-error">{openError}</p> : null}
  </section>;
}
