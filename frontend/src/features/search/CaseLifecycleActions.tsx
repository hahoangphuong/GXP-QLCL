import { useCaseDraftState, useCaseDraftRef } from "./CaseDraftSession";

import type { CaseTransitionRequest, CaseWorkspace } from "../../types";

type Props = { caseWorkspace: CaseWorkspace; onTransition: (payload: CaseTransitionRequest) => Promise<void> };
type Action = CaseWorkspace["transition_actions"][number];
function numericVersion(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function CaseLifecycleEditor({ caseWorkspace, onTransition }: Props) {
  const [reason, setReason] = useCaseDraftState("lifecycle.reason", "");
  const [intent, setIntent] = useCaseDraftState<Action[] | null>("lifecycle.intent", null);
  const [pendingKey, setPendingKey] = useCaseDraftState<string | null>("lifecycle.pendingKey", null);
  const inFlight = useCaseDraftRef("lifecycle.inFlight", false);
  const [error, setError] = useCaseDraftState<string | null>("lifecycle.error", null);
  function reviewedAction(action: Action) {
    return intent === null ? action : intent.find(item => item.action_key === action.action_key && item.target_state === action.target_state);
  }
  async function execute(action: Action) {
    const reviewed = reviewedAction(action);
    if (!action.available || !action.target_state || !numericVersion(action.expected_version) || !numericVersion(reviewed?.expected_version) || inFlight.current) return;
    inFlight.current = true;
    if (intent === null) setIntent((caseWorkspace.transition_actions ?? []).map(item => ({ ...item })));
    setPendingKey(action.action_key); setError(null);
    try {
      await onTransition({ target_state: action.target_state, expected_version: reviewed.expected_version, reason: reason.trim() || null });
      setReason(""); setIntent(null);
    }
    catch (value) { setError(value instanceof Error ? value.message : "Không thể chuyển trạng thái hồ sơ."); }
    finally { inFlight.current = false; setPendingKey(null); }
  }
  return <section className="workspace-section case-lifecycle-actions"><h4>Chuyển trạng thái hồ sơ</h4>
    <input aria-label="Lý do chuyển trạng thái" disabled={pendingKey !== null} onChange={(event) => { if (intent === null) setIntent((caseWorkspace.transition_actions ?? []).map(action => ({ ...action }))); setReason(event.target.value); }} value={reason} />
    <div className="panel-actions">{(caseWorkspace.transition_actions ?? []).map((action) => <button disabled={!action.available || !action.target_state || !numericVersion(action.expected_version) || !numericVersion(reviewedAction(action)?.expected_version) || pendingKey !== null} key={action.action_key} onClick={() => void execute(action)} type="button">{pendingKey === action.action_key ? "Đang chuyển..." : action.label}</button>)}
      {intent !== null ? <button disabled={pendingKey !== null} onClick={() => { setReason(""); setIntent(null); setError(null); }} type="button">Hủy nhập lý do chuyển trạng thái</button> : null}
    </div>
    {(caseWorkspace.transition_actions ?? []).filter((action) => !action.available && action.reason_code).map((action) => <p className="workspace-note" key={action.action_key}>{action.label}: {action.reason_code}</p>)}
    {error ? <p className="form-error" role="alert">{error}</p> : null}
  </section>;
}

export function CaseLifecycleActions(props: Props) {
  return <CaseLifecycleEditor key={props.caseWorkspace.case_summary.id} {...props} />;
}
