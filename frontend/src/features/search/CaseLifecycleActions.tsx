import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";
import { useCaseCommandLock, useCaseDraftState, useCaseDraftRef } from "./CaseDraftSession";
import { formatStatusLabel } from "../../lib/presentation";
import { caseReadinessReason } from "./caseReadinessReason";

import type { CaseTransitionRequest, CaseWorkspace } from "../../types";

type Props = { caseWorkspace: CaseWorkspace; onTransition: (payload: CaseTransitionRequest) => Promise<void> };
type Action = CaseWorkspace["transition_actions"][number];
type SubmittedTransition = {
  kind: "case.transition";
  caseId: string;
  actionKey: string;
  request: CaseTransitionRequest;
};
function numericVersion(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}
function actionLabel(action: Action): string {
  return action.target_state && action.label === action.target_state ? `Chuyển: ${formatStatusLabel(action.target_state)}` : action.label;
}

function CaseLifecycleEditor({ caseWorkspace, onTransition }: Props) {
  const [reason, setReason] = useCaseDraftState("lifecycle.reason", "");
  const [intent, setIntent] = useCaseDraftState<Action[] | null>("lifecycle.intent", null);
  const [pendingKey, setPendingKey] = useCaseDraftState<string | null>("lifecycle.pendingKey", null);
  const inFlight = useCaseDraftRef("lifecycle.inFlight", false);
  const commandLock = useCaseCommandLock("inspection.transition");
  const frozen = commandLock.pending || commandLock.requiresReview;
  // This is an exact submitted request for review, never evidence of a
  // committed transition. Case identity is checked independently of the lock.
  const payload = frozen ? commandLock.commandPayload<SubmittedTransition>() : undefined;
  const submitted = payload?.kind === "case.transition" && payload.caseId === caseWorkspace.case_summary.id ? payload : null;
  const visibleReason = submitted ? submitted.request.reason ?? "" : reason;
  const [error, setError] = useCaseDraftState<string | null>("lifecycle.error", null);
  function reviewedAction(action: Action) {
    return intent === null ? action : intent.find(item => item.action_key === action.action_key && item.target_state === action.target_state);
  }
  async function execute(action: Action) {
    const reviewed = reviewedAction(action);
    if (!action.available || !action.target_state || !numericVersion(action.expected_version) || !numericVersion(reviewed?.expected_version) || inFlight.current) return;
    const request: CaseTransitionRequest = {
      target_state: action.target_state,
      expected_version: reviewed.expected_version,
      reason: reason.trim() || null,
    };
    const command = commandLock.acquire({
      kind: "case.transition",
      caseId: caseWorkspace.case_summary.id,
      actionKey: action.action_key,
      request: { ...request },
    } satisfies SubmittedTransition);
    if (!command) return;
    inFlight.current = true;
    if (intent === null) setIntent((caseWorkspace.transition_actions ?? []).map(item => ({ ...item })));
    setPendingKey(action.action_key); setError(null);
    try {
      await onTransition(request);
      setReason(""); setIntent(null);
    }
    catch (value) { if (value instanceof CaseFieldMutationRecoveryError) commandLock.requireReview(command); setError(value instanceof Error ? value.message : "Không thể chuyển trạng thái hồ sơ."); }
    finally { commandLock.release(command); inFlight.current = false; setPendingKey(null); }
  }
  return <section className="workspace-section case-lifecycle-actions" data-case-lifecycle tabIndex={-1} aria-label="Chuyển trạng thái hồ sơ"><h4>Chuyển trạng thái hồ sơ</h4>
    <input aria-label="Lý do chuyển trạng thái" disabled={pendingKey !== null} readOnly={frozen} onChange={(event) => { if (frozen) return; if (intent === null) setIntent((caseWorkspace.transition_actions ?? []).map(action => ({ ...action }))); setReason(event.target.value); }} value={visibleReason} />
    <div className="panel-actions">{(caseWorkspace.transition_actions ?? []).map((action) => <button disabled={!action.available || !action.target_state || !numericVersion(action.expected_version) || !numericVersion(reviewedAction(action)?.expected_version) || pendingKey !== null || commandLock.pending || commandLock.requiresReview} key={action.action_key} onClick={() => void execute(action)} type="button">{pendingKey === action.action_key ? "Đang chuyển..." : actionLabel(action)}</button>)}
      {(intent !== null || submitted) ? <button disabled={pendingKey !== null || frozen} onClick={() => { if (frozen) return; setReason(""); setIntent(null); setError(null); }} type="button">Hủy nhập lý do chuyển trạng thái</button> : null}
    </div>
    {(caseWorkspace.transition_actions ?? []).filter((action) => !action.available && action.reason_code).map((action) => <p className="workspace-note" key={action.action_key}>{actionLabel(action)}: {caseReadinessReason(action.reason_code!)}</p>)}
    {error || commandLock.requiresReview ? <p className="form-error" role="alert">{error ?? "Chưa xác minh kết quả chuyển trạng thái. Không gửi lại; tải lại hồ sơ để kiểm tra."}</p> : null}
    {submitted ? <p className="workspace-note" role="status">
      {commandLock.pending ? "Đang xác minh kết quả chuyển trạng thái." : "Kết quả chuyển trạng thái chưa xác minh."}
      {" "}Đã gửi tới trạng thái {formatStatusLabel(submitted.request.target_state)} với expected_version {submitted.request.expected_version}.
      {" "}Lý do đã gửi được giữ nguyên để đối chiếu; có thể sao chép nhưng không sửa, hủy hoặc gửi lại khi kết quả chuyển trạng thái chưa xác minh.
    </p> : commandLock.requiresReview ? <p className="workspace-note" role="status">Kết quả chuyển trạng thái chưa xác minh. Không gửi lại khi chưa kiểm tra Case canonical.</p> : null}
  </section>;
}

export function CaseLifecycleActions(props: Props) {
  return <CaseLifecycleEditor key={props.caseWorkspace.case_summary.id} {...props} />;
}
