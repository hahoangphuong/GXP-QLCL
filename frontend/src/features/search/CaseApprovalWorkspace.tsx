import { useMemo, useState } from "react";

import { formatCompactDate } from "../../lib/presentation";
import type {
  CaseWorkspace,
  InspectionApprovalSubmissionCompleteRequest,
  InspectionApprovalSubmissionCreateRequest,
  InspectionApprovalSubmissionMutationResponse,
  LifecycleActionReadiness,
} from "../../types";

type Submission = CaseWorkspace["inspection"]["approval_submissions"][number];

function ApprovalCompletionEditor({ item, readiness, pending, onComplete }: {
  item: Submission;
  readiness: LifecycleActionReadiness | undefined;
  pending: boolean;
  onComplete: (id: string, payload: InspectionApprovalSubmissionCompleteRequest) => Promise<boolean>;
}) {
  const [draft, setDraft] = useState({ date: "", time: "", reason: "" });
  const [version, setVersion] = useState<number | null | undefined>();
  const [error, setError] = useState<string | null>(null);
  function change(field: keyof typeof draft, value: string) {
    setVersion((current) => current === undefined ? readiness?.expected_version ?? null : current);
    setDraft((current) => ({ ...current, [field]: value }));
  }
  function reset() {
    setDraft({ date: "", time: "", reason: "" });
    setVersion(undefined);
    setError(null);
  }
  async function complete() {
    if (pending || !readiness?.available || version == null || !draft.date) return;
    setError(null);
    try {
      if (await onComplete(item.approval_submission_id, {
        expected_version: version, completed_on: draft.date, completed_time: draft.time || null, reason: draft.reason.trim() || null,
      })) reset();
    } catch (value) {
      setError(value instanceof Error ? value.message : "Không thể hoàn tất trình phê duyệt.");
    }
  }
  if (!readiness?.available && version === undefined) return null;
  return <div aria-label={`Hoàn tất ${item.stage} lần ${item.round_no}`} role="group">
    <div className="panel-actions">
      <input aria-label="Ngày hoàn tất trình" disabled={pending || !readiness?.available} type="date" value={draft.date} onChange={(event) => change("date", event.target.value)} />
      <input aria-label="Giờ hoàn tất trình" disabled={pending || !readiness?.available} type="time" value={draft.time} onChange={(event) => change("time", event.target.value)} />
      <input aria-label="Lý do hoàn tất trình" disabled={pending || !readiness?.available} value={draft.reason} onChange={(event) => change("reason", event.target.value)} />
      <button disabled={pending || !readiness?.available || version == null || !draft.date} onClick={() => void complete()} type="button">Hoàn tất {item.stage}</button>
      {version !== undefined ? <button aria-label={`Hủy nhập hoàn tất ${item.stage} lần ${item.round_no}`} disabled={pending} onClick={reset} type="button">Hủy nhập hoàn tất</button> : null}
    </div>
    {error ? <p className="form-error" role="alert">{error}</p> : null}
  </div>;
}

function CaseApprovalEditor({
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
  const hasSelectedParent = completedPct.some((item) => item.approval_submission_id === parentId);
  const action = (key: string) => (caseWorkspace.inspection.approval_actions ?? []).find((item) => item.action_key === key);

  async function create(stage: "PCT" | "CT") {
    const readiness = action(`create_approval_${stage.toLowerCase()}`);
    if (!readiness?.available || pending || (stage === "CT" && !parentId)) return;
    if (stage === "CT" && !hasSelectedParent) return;
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
      setReference(""); setSubmittedOn(""); setSubmittedTime(""); setCreateReason(""); setParentId("");
    } catch (value) {
      setError(value instanceof Error ? value.message : "Không thể tạo trình phê duyệt.");
    } finally {
      setPending(null);
    }
  }

  async function complete(id: string, payload: InspectionApprovalSubmissionCompleteRequest): Promise<boolean> {
    const readiness = action(`complete_approval:${id}`);
    if (!readiness?.available || pending) return false;
    setPending(readiness.action_key);
    setError(null);
    try {
      await onComplete(id, payload);
      return true;
    } finally {
      setPending(null);
    }
  }

  return <section className="workspace-section case-approval-workspace">
    <h4>Trình phê duyệt PCT / CT</h4>
    <div className="panel-actions">
      <input aria-label="Tham chiếu trình" disabled={pending !== null} value={reference} onChange={(event) => setReference(event.target.value)} />
      <input aria-label="Ngày trình" disabled={pending !== null} type="date" value={submittedOn} onChange={(event) => setSubmittedOn(event.target.value)} />
      <input aria-label="Giờ trình" disabled={pending !== null} type="time" value={submittedTime} onChange={(event) => setSubmittedTime(event.target.value)} />
      <input aria-label="Lý do tạo trình" disabled={pending !== null} value={createReason} onChange={(event) => setCreateReason(event.target.value)} />
      <button disabled={!action("create_approval_pct")?.available || pending !== null} onClick={() => void create("PCT")} type="button">Tạo trình PCT</button>
      <select aria-label="PCT hoàn tất cho CT" disabled={pending !== null} value={parentId} onChange={(event) => setParentId(event.target.value)}>
        <option value="">Chọn PCT đã hoàn tất</option>
        {completedPct.map((item) => <option key={item.approval_submission_id} value={item.approval_submission_id}>PCT lần {item.round_no}</option>)}
      </select>
      <button disabled={!action("create_approval_ct")?.available || !hasSelectedParent || pending !== null} onClick={() => void create("CT")} type="button">Tạo trình CT</button>
    </div>
    {submissions.map((item) => {
      const readiness = action(`complete_approval:${item.approval_submission_id}`);
      return <div className="inspection-team-member" key={item.approval_submission_id}>
        <strong>{item.stage} lần {item.round_no}</strong>
        <span>{item.reference ?? "Chưa có tham chiếu"}</span>
        <span>Ngày trình: {formatCompactDate(item.submitted_on)}</span>
        <span>Giờ trình: {item.submitted_time ?? "Chưa có"}</span>
        <span>Ngày hoàn tất: {formatCompactDate(item.completed_on)}</span>
        <span>Giờ hoàn tất: {item.completed_time ?? "Chưa có"}</span>
        {item.stage === "CT" ? <span>PCT: {item.pct_submission_id ?? "Chưa có"}</span> : null}
        <ApprovalCompletionEditor item={item} readiness={readiness} pending={pending !== null} onComplete={complete} />
        {!readiness?.available && readiness?.reason_code ? <span className="workspace-note">{readiness.reason_code}</span> : null}
      </div>;
    })}
    {error ? <p className="form-error" role="alert">{error}</p> : null}
  </section>;
}

export function CaseApprovalWorkspace(props: Parameters<typeof CaseApprovalEditor>[0]) {
  return <CaseApprovalEditor key={props.caseWorkspace.case_summary.id} {...props} />;
}
