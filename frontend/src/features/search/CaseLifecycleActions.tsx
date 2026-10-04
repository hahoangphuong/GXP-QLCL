import { useState } from "react";

import type { CaseTransitionRequest, CaseWorkspace } from "../../types";

export function CaseLifecycleActions({ caseWorkspace, onTransition }: { caseWorkspace: CaseWorkspace; onTransition: (payload: CaseTransitionRequest) => Promise<void> }) {
  const [reason, setReason] = useState("");
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function execute(action: CaseWorkspace["transition_actions"][number]) {
    if (!action.available || !action.target_state || action.expected_version === null || pendingKey) return;
    setPendingKey(action.action_key); setError(null);
    try { await onTransition({ target_state: action.target_state, expected_version: action.expected_version, reason: reason.trim() || null }); }
    catch (value) { setError(value instanceof Error ? value.message : "Không thể chuyển trạng thái hồ sơ."); }
    finally { setPendingKey(null); }
  }
  return <section className="workspace-section case-lifecycle-actions"><h4>Chuyển trạng thái hồ sơ</h4>
    <input aria-label="Lý do chuyển trạng thái" disabled={pendingKey !== null} onChange={(event) => setReason(event.target.value)} value={reason} />
    <div className="panel-actions">{(caseWorkspace.transition_actions ?? []).map((action) => <button disabled={!action.available || !action.target_state || action.expected_version === null || pendingKey !== null} key={action.action_key} onClick={() => void execute(action)} type="button">{pendingKey === action.action_key ? "Đang chuyển..." : action.label}</button>)}</div>
    {(caseWorkspace.transition_actions ?? []).filter((action) => !action.available && action.reason_code).map((action) => <p className="workspace-note" key={action.action_key}>{action.label}: {action.reason_code}</p>)}
    {error ? <p className="form-error" role="alert">{error}</p> : null}
  </section>;
}
