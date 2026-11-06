import type { CaseWorkspace, ContextualDocumentAction } from "../../types";

// Only backend-provided workflow steps with a mounted contextual document pane.
const DOCUMENT_STEPS = new Set(["Hồ sơ", "Kiểm tra", "Khắc phục", "Xử lý", "Chứng nhận GxP"]);

/** A route key is only a lookup hint; both canonical projections must agree. */
export function resolveDocumentWorkspace(workspace: CaseWorkspace, caseId: string, key: string): ContextualDocumentAction | null {
  if (!key || workspace.case_summary?.id !== caseId || !Array.isArray(workspace.documents?.items)
    || !Array.isArray(workspace.contextual_document_actions)) return null;
  const items = workspace.documents.items.filter(item => item.checklist_key === key);
  const actions = workspace.contextual_document_actions.filter(item => item.checklist_key === key);
  if (items.length !== 1 || actions.length !== 1) return null;
  const item = items[0], action = actions[0];
  if (!item.family_code || item.family_code !== action.family_code || item.status !== action.status
    || item.document_id !== action.document_id || item.parent_scope !== action.parent_scope
    || item.parent_id !== action.parent_id || !DOCUMENT_STEPS.has(action.workflow_step)
    || !Array.isArray(action.actions)) return null;
  if (item.parent_scope === "case") {
    if (item.parent_id !== caseId) return null;
  } else if (item.parent_scope === "capa_cycle") {
    if (action.workflow_step !== "Khắc phục" || !Array.isArray(workspace.remediation?.cycles)
      || workspace.remediation.cycles.filter(cycle => cycle.capa_cycle_id === item.parent_id).length !== 1) return null;
  } else return null;
  if (item.status === "missing") {
    const creates = action.actions.filter(candidate => candidate.action_key === "create");
    if (item.document_id !== null || creates.length !== 1 || creates[0].available !== true
      || creates[0].create_input_readiness === "CANONICAL_INPUT_BLOCKED") return null;
  } else if (item.status === "available") {
    if (!item.document_id || !action.actions.some(candidate => (candidate.action_key === "history" || candidate.action_key === "open") && candidate.available === true)) return null;
  } else return null;
  return action;
}
