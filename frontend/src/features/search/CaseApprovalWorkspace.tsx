import { useMemo, useState } from "react";

import { formatCompactDate } from "../../lib/presentation";
import type {
  CaseWorkspace,
  InspectionApprovalSubmissionCompleteRequest,
  InspectionApprovalSubmissionCreateRequest,
  InspectionApprovalSubmissionMutationResponse,
} from "../../types";

export function CaseApprovalWorkspace({
  caseWorkspace,
  onCreate,
  onComplete,
}: {
  caseWorkspace: CaseWorkspace;
  onCreate: (stage: "PCT" | "CT", payload: InspectionApprovalSubmissionCreateRequest) => Promise<InspectionApprovalSubmissionMutationResponse>;
  onComplete: (id: string, payload: InspectionApprovalSubmissionCompleteRequest) => Promise<InspectionApprovalSubmissionMutationResponse>;
}) {
  const [reference, setReference] = useState("");
  const [submittedOn, setSubmittedOn] = useState("");
  const [submittedTime, setSubmittedTime] = useState("");
  const [createReason, setCreateReason] = useState("");
  const [completedOn, setCompletedOn] = useState("");
  const [completedTime, setCompletedTime] = useState("");
  const [completeReason, setCompleteReason] = useState("");
  const [parentId, setParentId] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submissions = useMemo(
    () => [...(caseWorkspace.inspection.approval_submissions ?? [])].sort(
      (a, b) => a.stage.localeCompare(b.stage) || a.round_no - b.round_no || a.approval_submission_id.localeCompare(b.approval_submission_id),
    ),
    [caseWorkspace.inspection.approval_submissions],
  );
  const completedPct = submissions.filter((item) => item.stage === "PCT" && item.completed_on !== null);
  const action = (key: string) => (caseWorkspace.inspection.approval_actions ?? []).find((item) => item.action_key === key);

  async function create(stage: "PCT" | "CT") {
    const readiness = action(`create_approval_${stage.toLowerCase()}`);
    if (!readiness?.available || pending || (stage === "CT" && !parentId)) return;
    setPending(readiness.action_key);
    setError(null);
    try {
      await onCreate(stage, {
        reference: reference.trim() || null,
        submitted_on: submittedOn || null,
        submitted_time: submittedTime || null,
        pct_submission_id: stage === "CT" ? parentId : null,
        reason: createReason.trim() || null,
      });
    } catch (value) {
      setError(value instanceof Error ? value.message : "Không thể tạo trình phê duyệt.");
    } finally {
      setPending(null);
    }
  }

  async function complete(item: typeof submissions[number]) {
    const readiness = action(`complete_approval:${item.approval_submission_id}`);
    if (!readiness?.available || readiness.expected_version === null || !completedOn || pending) return;
    setPending(readiness.action_key);
    setError(null);
    try {
      await onComplete(item.approval_submission_id, {
        expected_version: readiness.expected_version,
        completed_on: completedOn,
        completed_time: completedTime || null,
        reason: completeReason.trim() || null,
      });
    } catch (value) {
      setError(value instanceof Error ? value.message : "Không thể hoàn tất trình phê duyệt.");
    } finally {
      setPending(null);
    }
  }

  return <section className="workspace-section case-approval-workspace">
    <h4>Trình phê duyệt PCT / CT</h4>
    <div className="panel-actions">
      <input aria-label="Tham chiếu trình" value={reference} onChange={(event) => setReference(event.target.value)} />
      <input aria-label="Ngày trình" type="date" value={submittedOn} onChange={(event) => setSubmittedOn(event.target.value)} />
      <input aria-label="Giờ trình" type="time" value={submittedTime} onChange={(event) => setSubmittedTime(event.target.value)} />
      <input aria-label="Lý do tạo trình" value={createReason} onChange={(event) => setCreateReason(event.target.value)} />
      <button disabled={!action("create_approval_pct")?.available || pending !== null} onClick={() => void create("PCT")} type="button">Tạo trình PCT</button>
      <select aria-label="PCT hoàn tất cho CT" value={parentId} onChange={(event) => setParentId(event.target.value)}>
        <option value="">Chọn PCT đã hoàn tất</option>
        {completedPct.map((item) => <option key={item.approval_submission_id} value={item.approval_submission_id}>PCT lần {item.round_no}</option>)}
      </select>
      <button disabled={!action("create_approval_ct")?.available || !parentId || pending !== null} onClick={() => void create("CT")} type="button">Tạo trình CT</button>
    </div>
    <div className="panel-actions">
      <input aria-label="Ngày hoàn tất trình" type="date" value={completedOn} onChange={(event) => setCompletedOn(event.target.value)} />
      <input aria-label="Giờ hoàn tất trình" type="time" value={completedTime} onChange={(event) => setCompletedTime(event.target.value)} />
      <input aria-label="Lý do hoàn tất trình" value={completeReason} onChange={(event) => setCompleteReason(event.target.value)} />
    </div>
    {submissions.map((item) => {
      const readiness = action(`complete_approval:${item.approval_submission_id}`);
      return <div className="inspection-team-member" key={item.approval_submission_id}>
        <strong>{item.stage} lần {item.round_no}</strong>
        <span>{item.reference ?? "Chưa có tham chiếu"}</span>
        <span>Trình: {formatCompactDate(item.submitted_on)}</span>
        <span>Hoàn tất: {formatCompactDate(item.completed_on)}</span>
        {item.stage === "CT" ? <span>PCT: {item.pct_submission_id ?? "Chưa có"}</span> : null}
        {readiness?.available ? <button disabled={!completedOn || pending !== null} onClick={() => void complete(item)} type="button">Hoàn tất {item.stage}</button> : readiness?.reason_code ? <span className="workspace-note">{readiness.reason_code}</span> : null}
      </div>;
    })}
    {error ? <p className="form-error" role="alert">{error}</p> : null}
  </section>;
}
