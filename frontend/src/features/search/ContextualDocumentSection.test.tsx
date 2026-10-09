import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ContextualDocumentAction, DocumentDetail } from "../../types";
import { ContextualDocumentSection } from "./ContextualDocumentSection";

function item(id: string): ContextualDocumentAction {
  return { checklist_key: `slot-${id}`, label: id, family_code: "KHKT", workflow_step: "Kiểm tra", parent_scope: "case", parent_id: "case-1",
    status: "available", document_id: id, document_type_code: null, title: null, original_filename: "same-prefix.docx", issued_on: null,
    available_variant_types: ["DOCX"], detail_available: true,
    actions: [{ action_key: "history", label: "Lịch sử", available: true, disabled_reason: null, required_permissions: [] }] };
}
function detail(id: string): DocumentDetail {
  return { document_id: id, family_code: "KHKT", document_type_code: "KHKT", title: `Detail ${id}`, legacy_entity_type: "inspection",
    case_id: "case-1", capa_cycle_id: null, certificate_id: null, business_eligibility_certificate_id: null, change_request_id: null,
    variants: [{ id: `rendition-${id}`, variant_type: "DOCX", language_code: "vi", is_active: true,
      versions: [{ id: `version-${id}`, version_no: 1, original_filename: "same-prefix.docx", is_current: true, issued_on: null }] }], generation_runs: [] };
}
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; }
const defaults = { onCreateDocument: vi.fn(), onOpenDocument: vi.fn() };

describe("Document workspace identity and focus", () => {
  it("moves focus without selecting or requesting; Enter selection and F6 move between panes", async () => {
    const load = vi.fn().mockImplementation(async id => detail(id));
    render(<ContextualDocumentSection {...defaults} items={[item("A"), item("B")]} onLoadDocumentDetail={load} />);
    const a = screen.getByRole("button", { name: "Chọn A" }); const b = screen.getByRole("button", { name: "Chọn B" });
    a.focus(); fireEvent.keyDown(a, { key: "End" }); expect(b).toHaveFocus(); expect(load).not.toHaveBeenCalled();
    fireEvent.keyDown(b, { key: "Home" }); expect(a).toHaveFocus();
    fireEvent.keyDown(a, { key: "ArrowDown" }); expect(b).toHaveFocus();
    fireEvent.click(b); await screen.findByText("Detail B");
    fireEvent.keyDown(b, { key: "F6" }); expect(screen.getByRole("heading", { name: "Chi tiết tài liệu" })).toHaveFocus();
    fireEvent.keyDown(document.activeElement!, { key: "F6", shiftKey: true }); expect(b).toHaveFocus();
    fireEvent.keyDown(b, { key: "ArrowUp" }); expect(a).toHaveFocus(); expect(b).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(b); expect(load).toHaveBeenCalledTimes(1);
    expect(screen.getByText("version-B")).toBeInTheDocument(); expect(screen.getByText("rendition-B")).toBeInTheDocument();
  });
  it("ignores late A after B and retains exact selection across a same-context refresh", async () => {
    const a = deferred<DocumentDetail>(); const b = deferred<DocumentDetail>();
    const load = vi.fn().mockImplementation(id => id === "A" ? a.promise : b.promise);
    const props = { ...defaults, contextKey: "case-1/line-uuid", onLoadDocumentDetail: load };
    const view = render(<ContextualDocumentSection {...props} items={[item("A"), item("B")]} />);
    fireEvent.click(screen.getByRole("button", { name: "Chọn A" }));
    fireEvent.click(screen.getByRole("button", { name: "Chọn B" }));
    await act(async () => b.resolve(detail("B"))); await act(async () => a.resolve(detail("A")));
    expect(screen.getByText("Detail B")).toBeInTheDocument(); expect(screen.queryByText("Detail A")).not.toBeInTheDocument();
    view.rerender(<ContextualDocumentSection {...props} items={[item("A"), item("B")]} />);
    expect(screen.getByRole("button", { name: "Chọn B" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("version-B")).toBeInTheDocument(); expect(load).toHaveBeenCalledTimes(2);
  });
  it("fails closed on context changes, A → B → A, removal and mismatched backend identity", async () => {
    const pending = deferred<DocumentDetail>(); const load = vi.fn().mockReturnValue(pending.promise);
    const props = { ...defaults, items: [item("A")], onLoadDocumentDetail: load };
    const view = render(<ContextualDocumentSection {...props} contextKey="event-A" />);
    fireEvent.click(screen.getByRole("button", { name: "Chọn A" }));
    view.rerender(<ContextualDocumentSection {...props} contextKey="event-B" />);
    expect(screen.queryByText("Đang tải lịch sử tài liệu...")).not.toBeInTheDocument();
    view.rerender(<ContextualDocumentSection {...props} contextKey="event-A" />);
    await act(async () => pending.resolve(detail("A"))); expect(screen.queryByText("Detail A")).not.toBeInTheDocument();
    load.mockResolvedValue(detail("wrong-id")); fireEvent.click(screen.getByRole("button", { name: "Lịch sử A" }));
    await screen.findByRole("alert"); expect(screen.queryByText("Detail wrong-id")).not.toBeInTheDocument();
    view.rerender(<ContextualDocumentSection {...props} items={[]} contextKey="event-A" />);
    expect(screen.getByText("Chưa có tài liệu trong ngữ cảnh này.")).toBeInTheDocument(); expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it.each([403, 404, 409])("presents %s without retrying the supported create action", async status => {
    const pending = deferred<void>(); const create = vi.fn().mockReturnValue(pending.promise);
    const row = item("A"); row.actions = [{ action_key: "create", label: "Tạo", available: true, disabled_reason: null, required_permissions: [] }];
    const view = render(<ContextualDocumentSection {...defaults} items={[row]} onLoadDocumentDetail={vi.fn()} onCreateDocument={create} />);
    const button = screen.getByRole("button", { name: "Tạo A" }); fireEvent.click(button); fireEvent.click(button);
    expect(create).toHaveBeenCalledTimes(1); expect(button).toBeDisabled();
    create.mockRejectedValue(Object.assign(new Error("backend conflict"), { status }));
    await act(async () => pending.resolve()); fireEvent.click(button); await screen.findByRole("alert");
    view.rerender(<ContextualDocumentSection {...defaults} items={[{ ...row }]} onLoadDocumentDetail={vi.fn()} onCreateDocument={create} />);
    expect(create).toHaveBeenCalledTimes(2); expect(screen.getByRole("alert")).toHaveTextContent("backend conflict");
  });
  it("clears a superseded metadata loading state when opening the current binary", async () => {
    const pending = deferred<DocumentDetail>(); const row = item("A");
    row.actions.push({ action_key: "open", label: "Mở", available: true, disabled_reason: null, required_permissions: [] });
    const open = vi.fn().mockResolvedValue(undefined);
    render(<ContextualDocumentSection {...defaults} items={[row]} onLoadDocumentDetail={() => pending.promise} onOpenDocument={open} />);
    fireEvent.click(screen.getByRole("button", { name: "Chọn A" }));
    expect(screen.getByText("Đang tải lịch sử tài liệu...")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Mở A" }));
    await act(async () => pending.resolve(detail("A")));
    expect(open).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Đang tải lịch sử tài liệu...")).not.toBeInTheDocument();
    expect(screen.queryByText("Detail A")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Lịch sử A" })).toBeEnabled();
  });
});

