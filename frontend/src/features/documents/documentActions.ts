import type { ContextualDocumentAction, ContextualDocumentActionAvailability, DocumentChecklistItem, DocumentDetail } from "../../types";

export function hasCurrentActiveDocumentVersion(detail: DocumentDetail): boolean {
  return detail.variants.some(variant => variant.is_active
    && variant.versions.some(version => version.is_current));
}

// Backend owns the create decision. Do not infer permissions from missing checklist items.
export function resolveDocumentCreation(
  actions: ContextualDocumentAction[],
  item: DocumentChecklistItem,
): ContextualDocumentActionAvailability | null {
  if (item.status !== "missing") return null;
  const matching = actions.filter(action =>
    action.checklist_key === item.checklist_key
    && action.parent_scope === item.parent_scope
    && action.parent_id === item.parent_id
    && action.family_code === item.family_code && action.status === item.status
    && action.document_id === item.document_id);
  if (matching.length !== 1 || !Array.isArray(matching[0].actions)) return null;
  const creates = matching[0].actions.filter(action => action.action_key === "create");
  // A source-backed readiness is necessary; button never POSTs from this register.
  return creates.length === 1 ? creates[0] : null;
}

export function safeDocumentDownloadName(
  serverFilename: string | null,
  fallbackFilename: string | null,
): string {
  const raw = serverFilename || fallbackFilename || "tai-lieu-hien-hanh";
  const name = raw.split(/[\\/]/).pop() || "tai-lieu-hien-hanh";
  return Array.from(name, char => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127
    || '< > : " | ? *'.replace(/ /g, "").includes(char) ? "_" : char)
    .join("").trim() || "tai-lieu-hien-hanh";
}
