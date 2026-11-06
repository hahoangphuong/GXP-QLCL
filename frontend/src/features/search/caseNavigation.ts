// A return destination is a presentation hint, never a Case or permission source.
export type CaseWorkflowQueue = "active" | "inspection" | "certificate_decision";
export function caseWorkflowQueue(value: string | null): CaseWorkflowQueue | null {
  return value === "active" || value === "inspection" || value === "certificate_decision" ? value : null;
}
