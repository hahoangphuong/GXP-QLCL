import { describe, expect, it } from "vitest";
import type { ContextualDocumentAction, DocumentChecklistItem, DocumentDetail } from "../../types";
import { hasCurrentActiveDocumentVersion, resolveDocumentCreation, safeDocumentDownloadName } from "./documentActions";

const detail = {
  variants: [
    { is_active: false, versions: [{ is_current: true }] },
    { is_active: true, versions: [{ is_current: false }] },
  ],
} as DocumentDetail;
const item = {
  checklist_key: "case:case-1:DOC",
  parent_scope: "case",
  parent_id: "case-1",
  status: "missing",
  document_id: null,
} as DocumentChecklistItem;
function action(overrides: Record<string, unknown> = {}) {
  return {
    checklist_key: item.checklist_key,
    parent_scope: item.parent_scope,
    parent_id: item.parent_id,
    family_code: item.family_code, status: item.status, document_id: item.document_id,
    actions: [{
      action_key: "create", available: true,
      create_input_readiness: "CANONICAL_INPUT_READY",
    }],
    ...overrides,
  } as unknown as ContextualDocumentAction;
}

describe("document register binary and creation contracts", () => {
  it("requires both active variant and current version for file downloads", () => {
    expect(hasCurrentActiveDocumentVersion(detail)).toBe(false);
    expect(hasCurrentActiveDocumentVersion({
      ...detail,
      variants: [...detail.variants, {
        ...detail.variants[0], is_active: true,
        versions: [{ ...detail.variants[0].versions[0], is_current: true }],
      }],
    })).toBe(true);
  });
  it("matches source create actions by exact checklist and parent ownership", () => {
    expect(resolveDocumentCreation([action()], item)?.available).toBe(true);
    expect(resolveDocumentCreation([action({ parent_id: "other-case" })], item)).toBeNull();
    expect(resolveDocumentCreation([action({ checklist_key: "other" })], item)).toBeNull();
    expect(resolveDocumentCreation([], item)).toBeNull();
    expect(resolveDocumentCreation([action()], { ...item, status: "available" })).toBeNull();
  });
  it("keeps blocked source status rather than synthesizing an available action", () => {
    const blocked = action({
      actions: [{ action_key: "create", available: false, disabled_reason: "Thiếu dữ liệu đầu vào" }],
    });
    expect(resolveDocumentCreation([blocked], item)).toMatchObject({
      available: false, disabled_reason: "Thiếu dữ liệu đầu vào",
    });
  });
  it("strips path components and unsafe control/filename characters", () => {
    expect(safeDocumentDownloadName("../../unsafe/report.docx", null)).toBe("report.docx");
    expect(safeDocumentDownloadName("C:\\temp\\GCN:bad?.pdf", null)).toBe("GCN_bad_.pdf");
    expect(safeDocumentDownloadName(null, "bien-ban.docx")).toBe("bien-ban.docx");
    expect(safeDocumentDownloadName(null, null)).toBe("tai-lieu-hien-hanh");
    expect(safeDocumentDownloadName("  \u0000\u001fA.txt", null)).toBe("__A.txt");
  });
});
