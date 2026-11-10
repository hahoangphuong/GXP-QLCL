import { useCaseDraftState } from "./CaseDraftSession";
import { caseReadinessReason } from "./caseReadinessReason";
import { useContext, useEffect, useMemo, useRef, useState } from "react";

import { formatCompactDate } from "../../lib/presentation";
import { ApprovalMutationContext } from "./approvalMutationRecovery";
import type {
  CaseWorkspace,
  InspectionApprovalSubmissionCompleteRequest,
  InspectionApprovalSubmissionCreateRequest,
  InspectionApprovalSubmissionMutationResponse,
  LifecycleActionReadiness,
} from "../../types";

type Submission = CaseWorkspace["inspection"]["approval_submissions"][number];

function ApprovalCompletionEditor({ item, readiness, pending, requiresReview, onComplete }: {
  item: Submission;
  readiness: LifecycleActionReadiness | undefined;
  pending: boolean;
  requiresReview: boolean;
  onComplete: (id: string, payload: InspectionApprovalSubmissionCompleteRequest) => Promise<boolean>;
}) {
  const [draft, setDraft] = useCaseDraftState(`approval.complete.${item.approval_submission_id}.draft`, { date: "", time: "", reason: "" });
  const [version, setVersion] = useCaseDraftState<number | null | undefined>(`approval.complete.${item.approval_submission_id}.version`, undefined);
  const [error, setError] = useCaseDraftState<string | null>(`approval.complete.${item.approval_submission_id}.error`, null);
  function change(field: keyof typeof draft, value: string) {
    if (requiresReview) return;
    setVersion((current) => current === undefined ? readiness?.expected_version ?? null : current);
    setDraft((current) => ({ ...current, [field]: value }));
  }
  function reset() {
    if (requiresReview) return;
    setDraft({ date: "", time: "", reason: "" });
    setVersion(undefined);
    setError(null);
  }
  async function complete() {
    if (pending || requiresReview || !readiness?.available || version == null || !draft.date) return;
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
      <input aria-label="Ngày hoàn tất trình" disabled={pending || !readiness?.available} readOnly={requiresReview} type="date" value={draft.date} onChange={(event) => change("date", event.target.value)} />
      <input aria-label="Giờ hoàn tất trình" disabled={pending || !readiness?.available} readOnly={requiresReview} type="time" value={draft.time} onChange={(event) => change("time", event.target.value)} />
      <input aria-label="Lý do hoàn tất trình" disabled={pending || !readiness?.available} readOnly={requiresReview} value={draft.reason} onChange={(event) => change("reason", event.target.value)} />
      <button disabled={pending || requiresReview || !readiness?.available || version == null || !draft.date} onClick={() => void complete()} type="button">Hoàn tất {item.stage}</button>
      {version !== undefined ? <button aria-label={`Hủy nhập hoàn tất ${item.stage} lần ${item.round_no}`} disabled={pending || requiresReview} onClick={reset} type="button">Hủy nhập hoàn tất</button> : null}
    </div>
    {requiresReview && version !== undefined ? <p className="workspace-note" role="status">Thông tin hoàn tất đã nhập được giữ nguyên để đối chiếu kết quả canonical; không sửa hoặc hủy khi kết quả ghi chưa xác minh.</p> : null}
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
  const [reference, setReference] = useCaseDraftState("approval.create.reference", "");
  const [submittedOn, setSubmittedOn] = useCaseDraftState("approval.create.submittedOn", "");
  const [submittedTime, setSubmittedTime] = useCaseDraftState("approval.create.submittedTime", "");
  const [createReason, setCreateReason] = useCaseDraftState("approval.create.createReason", "");
  const [parentId, setParentId] = useCaseDraftState("approval.create.parentId", "");
  const parentSelect = useRef<HTMLSelectElement>(null);
  const approvalRows = useRef(new Map<string, HTMLDivElement>());
  const [stageFilter, setStageFilter] = useCaseDraftState<"all" | "PCT" | "CT">("approval.history.stageFilter", "all");
  const [unfinishedOnly, setUnfinishedOnly] = useCaseDraftState("approval.history.unfinishedOnly", false);
  const navigateToId = useRef<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const inFlight = useRef(false);
  const { pending: ownerPending, requiresReview } = useContext(ApprovalMutationContext);
  const [error, setError] = useCaseDraftState<string | null>("approval.create.error", null);

  const submissions = useMemo(
    () => [...(caseWorkspace.inspection.approval_submissions ?? [])].sort(
      (a, b) => a.stage.localeCompare(b.stage) || a.round_no - b.round_no || a.approval_submission_id.localeCompare(b.approval_submission_id),
    ),
    [caseWorkspace.inspection.approval_submissions],
  );
  const caseId = caseWorkspace.case_summary.id;
  const completedPct = submissions.filter((item) => item.stage === "PCT" && item.case_id === caseId && item.completed_on !== null);
  const pctById = useMemo(() => new Map(submissions.filter(item => item.stage === "PCT" && item.case_id === caseId).map(item => [item.approval_submission_id, item])), [submissions, caseId]);
  const ctByParent = useMemo(() => {
    const result = new Map<string, Submission[]>();
    for (const ct of submissions) {
      if (ct.stage !== "CT" || ct.case_id !== caseId || !ct.pct_submission_id || !pctById.has(ct.pct_submission_id)) continue;
      const children = result.get(ct.pct_submission_id) ?? [];
      children.push(ct);
      result.set(ct.pct_submission_id, children);
    }
    return result;
  }, [submissions, pctById, caseId]);
  const stageSubmissions = stageFilter === "all" ? submissions : submissions.filter(item => item.stage === stageFilter);
  const visibleSubmissions = unfinishedOnly ? stageSubmissions.filter(item => item.completed_on === null) : stageSubmissions;
  const unfinishedCount = submissions.filter(item => item.completed_on === null).length;
  useEffect(() => {
    if ((stageFilter !== "all" || unfinishedOnly) || !navigateToId.current) return;
    approvalRows.current.get(navigateToId.current)?.focus();
    navigateToId.current = null;
  }, [stageFilter, unfinishedOnly]);
  function navigateToApproval(id: string) {
    // Related records may be hidden by either filter. Restore the full
    // canonical history before focusing by UUID; never infer row position.
    if (stageFilter === "all" && !unfinishedOnly) approvalRows.current.get(id)?.focus();
    else {
      navigateToId.current = id;
      setStageFilter("all");
      setUnfinishedOnly(false);
    }
  }
  const hasSelectedParent = completedPct.some((item) => item.approval_submission_id === parentId);
  const submittedTimeRequiresDate = Boolean(submittedTime && !submittedOn);
  const action = (key: string) => (caseWorkspace.inspection.approval_actions ?? []).find((item) => item.action_key === key);

  async function create(stage: "PCT" | "CT") {
    const readiness = action(`create_approval_${stage.toLowerCase()}`);
    if (!readiness?.available || inFlight.current || ownerPending || requiresReview || submittedTimeRequiresDate || (stage === "CT" && !parentId)) return;
    if (stage === "CT" && !hasSelectedParent) return;
    inFlight.current = true;
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
      inFlight.current = false;
      setPending(null);
    }
  }

  async function complete(id: string, payload: InspectionApprovalSubmissionCompleteRequest): Promise<boolean> {
    const readiness = action(`complete_approval:${id}`);
    if (!readiness?.available || inFlight.current || ownerPending || requiresReview) return false;
    inFlight.current = true;
    setPending(readiness.action_key);
    setError(null);
    try {
      await onComplete(id, payload);
      return true;
    } finally {
      inFlight.current = false;
      setPending(null);
    }
  }

  return <section className="workspace-section case-approval-workspace">
    <h4>Trình phê duyệt PCT / CT</h4>
    <div className="panel-actions">
      <input aria-label="Tham chiếu trình" disabled={pending !== null || ownerPending} readOnly={requiresReview} value={reference} onChange={(event) => { if (!requiresReview) setReference(event.target.value); }} />
      <input aria-label="Ngày trình" disabled={pending !== null || ownerPending} readOnly={requiresReview} type="date" value={submittedOn} onChange={(event) => { if (!requiresReview) setSubmittedOn(event.target.value); }} />
      <input aria-label="Giờ trình" disabled={pending !== null || ownerPending} readOnly={requiresReview} type="time" value={submittedTime} onChange={(event) => { if (!requiresReview) setSubmittedTime(event.target.value); }} />
      <input aria-label="Lý do tạo trình" disabled={pending !== null || ownerPending} readOnly={requiresReview} value={createReason} onChange={(event) => { if (!requiresReview) setCreateReason(event.target.value); }} />
      <button disabled={!action("create_approval_pct")?.available || submittedTimeRequiresDate || pending !== null || ownerPending || requiresReview} onClick={() => void create("PCT")} type="button">Tạo trình PCT</button>
      <select ref={parentSelect} aria-label="PCT hoàn tất cho CT" disabled={pending !== null || ownerPending || requiresReview} value={parentId} onChange={(event) => { if (!requiresReview) setParentId(event.target.value); }}>
        <option value="">Chọn PCT đã hoàn tất</option>
        {completedPct.map((item) => <option key={item.approval_submission_id} value={item.approval_submission_id}>PCT lần {item.round_no}{item.reference ? ` — ${item.reference}` : ""} — {formatCompactDate(item.completed_on)}</option>)}
      </select>
      <button disabled={!action("create_approval_ct")?.available || !hasSelectedParent || submittedTimeRequiresDate || pending !== null || ownerPending || requiresReview} onClick={() => void create("CT")} type="button">Tạo trình CT</button>
    </div>
    {submittedTimeRequiresDate ? <p className="workspace-note" role="alert">Cần nhập ngày trình trước khi ghi giờ trình PCT/CT.</p> : null}
    {(["pct", "ct"] as const).map(stage => {
      const readiness = action(`create_approval_${stage}`);
      return readiness && !readiness.available && readiness.reason_code ? <p className="workspace-note" key={stage}>Tạo trình {stage.toUpperCase()}: {caseReadinessReason(readiness.reason_code)}</p> : null;
    })}
    {action("create_approval_ct")?.available && completedPct.length > 0 && !hasSelectedParent ? <p className="workspace-note">Chọn một trình PCT đã hoàn tất để tạo trình CT.</p> : null}
    <div className="panel-actions" role="group" aria-label="Lọc lịch sử trình phê duyệt">
      {(["all", "PCT", "CT"] as const).map(stage => <button key={stage} type="button" className={stageFilter === stage ? "" : "secondary"}
        aria-pressed={stageFilter === stage} onClick={() => setStageFilter(stage)}>
        {stage === "all" ? `Tất cả (${submissions.length})` : `${stage} (${submissions.filter(item => item.stage === stage).length})`}
      </button>)}
    </div>
    <div className="panel-actions" role="group" aria-label="Lọc tiến độ trình phê duyệt">
      <button type="button" className={!unfinishedOnly ? "" : "secondary"} aria-pressed={!unfinishedOnly} onClick={() => setUnfinishedOnly(false)}>Mọi trạng thái ({stageSubmissions.length})</button>
      <button type="button" className={unfinishedOnly ? "" : "secondary"} aria-pressed={unfinishedOnly} onClick={() => setUnfinishedOnly(true)}>Chưa hoàn tất ({stageSubmissions.filter(item => item.completed_on === null).length})</button>
    </div>
    {visibleSubmissions.length === 0 ? <p className="workspace-note">Không có trình phê duyệt phù hợp bộ lọc. Tổng số chưa hoàn tất trong Case: {unfinishedCount}.</p> : null}
    {visibleSubmissions.map((item) => {
      const readiness = action(`complete_approval:${item.approval_submission_id}`);
      const parent = item.stage === "CT" ? pctById.get(item.pct_submission_id ?? "") : undefined;
      const relatedCt = item.stage === "PCT" ? (ctByParent.get(item.approval_submission_id) ?? []) : [];
      return <div className="inspection-team-member" key={item.approval_submission_id} tabIndex={-1}
        ref={node => { if (node) approvalRows.current.set(item.approval_submission_id, node); else approvalRows.current.delete(item.approval_submission_id); }}
        aria-label={`${item.stage} lần ${item.round_no} — ${item.approval_submission_id}`}>
        <strong>{item.stage} lần {item.round_no}</strong>
        <span>{item.reference ?? "Chưa có tham chiếu"}</span>
        <span>Ngày trình: {formatCompactDate(item.submitted_on)}</span>
        <span>Giờ trình: {item.submitted_time ?? "Chưa có"}</span>
        <span>Ngày hoàn tất: {formatCompactDate(item.completed_on)}</span>
        <span>Giờ hoàn tất: {item.completed_time ?? "Chưa có"}</span>
        {item.stage === "CT" ? <span>PCT: {parent ? `lần ${parent.round_no}${parent.reference ? ` — ${parent.reference}` : ""}` : item.pct_submission_id ?? "Chưa có"}</span> : null}
        {parent ? <button type="button" className="secondary" onClick={() => navigateToApproval(parent.approval_submission_id)}>
          Xem PCT lần {parent.round_no} của CT lần {item.round_no}
        </button> : null}
        {item.stage === "PCT" ? <div aria-label={`Các CT của PCT lần ${item.round_no}`}>
          <span>CT liên kết: {relatedCt.length}</span>
          {relatedCt.map(ct => <button className="secondary" key={ct.approval_submission_id} type="button"
            onClick={() => navigateToApproval(ct.approval_submission_id)}>Xem CT lần {ct.round_no} của PCT lần {item.round_no}</button>)}
        </div> : null}
        {item.stage === "PCT" && item.completed_on !== null && action("create_approval_ct")?.available ? (
          <button disabled={pending !== null || ownerPending || requiresReview} onClick={() => { if (requiresReview) return; setParentId(item.approval_submission_id); parentSelect.current?.focus(); }} type="button">
            Dùng PCT lần {item.round_no} để tạo trình CT
          </button>
        ) : null}
        {parent ? <button disabled={pending !== null || ownerPending || requiresReview} onClick={() => { if (requiresReview) return; setParentId(parent.approval_submission_id); parentSelect.current?.focus(); }} type="button">Chọn PCT lần {parent.round_no} cho trình CT</button> : null}
        <ApprovalCompletionEditor item={item} readiness={readiness} pending={pending !== null || ownerPending} requiresReview={requiresReview} onComplete={complete} />
        {!readiness?.available && readiness?.reason_code ? <span className="workspace-note">{caseReadinessReason(readiness.reason_code)}</span> : null}
      </div>;
    })}
    {error ? <p className="form-error" role="alert">{error}</p> : null}
    {requiresReview ? <p className="workspace-note" role="status">Chưa xác minh kết quả ghi. Thông tin trình và PCT cha đã chọn được giữ nguyên để đối chiếu canonical; không sửa, hủy hoặc gửi lại trước khi xác minh.</p> : null}
  </section>;
}

export function CaseApprovalWorkspace(props: Parameters<typeof CaseApprovalEditor>[0]) {
  return <CaseApprovalEditor key={props.caseWorkspace.case_summary.id} {...props} />;
}
