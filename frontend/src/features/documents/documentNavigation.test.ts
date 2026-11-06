import { describe, expect, it } from "vitest";
import type { CaseWorkspace, ContextualDocumentAction, DocumentChecklistItem } from "../../types";
import { resolveDocumentWorkspace } from "./documentNavigation";

const item = { checklist_key: "case:A:PLAN", parent_scope: "case", parent_id: "A", family_code: "PLAN", status: "missing", document_id: null } as DocumentChecklistItem;
const action = { ...item, workflow_step: "Kiểm tra", actions: [{ action_key: "create", available: true, create_input_readiness: "CANONICAL_INPUT_READY" }] } as ContextualDocumentAction;
function fixture() { return { case_summary: { id: "A" }, documents: { items: [item] }, contextual_document_actions: [action], remediation: { cycles: [] } } as unknown as CaseWorkspace; }

describe("document workspace navigation ownership", () => {
  it("resolves the backend-owned workflow step for an available create action", () => {
    expect(resolveDocumentWorkspace(fixture(), "A", item.checklist_key)).toMatchObject({ workflow_step: "Kiểm tra", checklist_key: item.checklist_key });
  });
  it("rejects conflicting Case, parent, document, ambiguous or blocked actions", () => {
    const w = fixture();
    expect(resolveDocumentWorkspace(w, "B", item.checklist_key)).toBeNull();
    expect(resolveDocumentWorkspace({ ...w, contextual_document_actions: [{ ...action, parent_id: "B" }] }, "A", item.checklist_key)).toBeNull();
    expect(resolveDocumentWorkspace({ ...w, contextual_document_actions: [{ ...action, document_id: "other" }] }, "A", item.checklist_key)).toBeNull();
    expect(resolveDocumentWorkspace({ ...w, contextual_document_actions: [action, action] }, "A", item.checklist_key)).toBeNull();
    expect(resolveDocumentWorkspace({ ...w, contextual_document_actions: [{ ...action, actions: [{ action_key: "create", available: false } as typeof action.actions[number]] }] }, "A", item.checklist_key)).toBeNull();
  });
  it("requires the exact CAPA cycle, without choosing another", () => {
    const ci = { ...item, checklist_key: "capa:C:PLAN", parent_scope: "capa_cycle", parent_id: "C" } as DocumentChecklistItem;
    const ca = { ...action, ...ci, workflow_step: "Khắc phục" } as ContextualDocumentAction;
    const w = { ...fixture(), documents: { items: [ci] }, contextual_document_actions: [ca], remediation: { cycles: [{ capa_cycle_id: "C" }], actions: [] } } as unknown as CaseWorkspace;
    expect(resolveDocumentWorkspace(w, "A", ci.checklist_key)?.parent_id).toBe("C");
    expect(resolveDocumentWorkspace({ ...w, remediation: { cycles: [], actions: [] } }, "A", ci.checklist_key)).toBeNull();
  });
});
