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
  const matching = actions.find(action =>
    action.checklist_key === item.checklist_key
    && action.parent_scope === item.parent_scope
    && action.parent_id === item.parent_id);
  const create = matching?.actions.find(action => action.action_key === "create");
  // A source-backed readiness is necessary; button never POSTs from this register.
  if (!create) return null;
  return create;
}

export function safeDocumentDownloadName(
  serverFilename: string | null,
  fallbackFilename: string | null,
): string {
  const raw = serverFilename || fallbackFilename || "tai-lieu-hien-hanh";
  const name = raw.split(/[\\/]/).pop() || "tai-lieu-hien-hanh";
  return name.replace(/[\u0000-\u001f\u007f<>:"|?*]/g, "_").trim() || "tai-lieu-hien-hanh";
}
