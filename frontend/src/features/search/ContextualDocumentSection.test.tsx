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
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (error: Error) => void; const promise = new Promise<T>((r, j) => { resolve = r; reject = j; }); return { promise, resolve, reject }; }
const defaults = { onCreateDocument: vi.fn(), onOpenDocument: vi.fn() };

describe("Document workspace identity and focus", () => {
  it("selects an approved navigation slot without opening, creating or loading it", async () => {
    const load = vi.fn(async (id: string) => detail(id));
    const open = vi.fn(); const create = vi.fn();
    const props = { contextKey: "event", initialSelectionKey: "slot-B", onLoadDocumentDetail: load, onOpenDocument: open, onCreateDocument: create };
    const view = render(<ContextualDocumentSection {...props} items={[item("A"), item("B")]} />);
    expect(screen.getByRole("button", { name: "Chọn B" })).toHaveAttribute("aria-pressed", "true");
    expect(load).not.toHaveBeenCalled(); expect(open).not.toHaveBeenCalled(); expect(create).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Chọn A" })); await screen.findByText("Detail A");
    view.rerender(<ContextualDocumentSection {...props} items={[item("A"), item("B")]} />);
    expect(screen.getByRole("button", { name: "Chọn A" })).toHaveAttribute("aria-pressed", "true");
  });
  it("R1 rejects an initial binary after same-event A → B → A selection", async () => {
    const pending = deferred<void>(); const opened = vi.fn();
    const a = item("A"); a.actions.push({ action_key: "open", label: "Mở", available: true, disabled_reason: null, required_permissions: [] });
    const open = vi.fn(async (_item, isCurrent) => { await pending.promise; if (isCurrent()) opened(); });
    render(<ContextualDocumentSection {...defaults} contextKey="event" items={[a, item("B")]} onLoadDocumentDetail={async id => detail(id)} onOpenDocument={open} />);
    fireEvent.click(screen.getByRole("button", { name: "Mở A" }));
    fireEvent.click(screen.getByRole("button", { name: "Chọn B" })); await screen.findByText("Detail B");
    fireEvent.click(screen.getByRole("button", { name: "Chọn A" })); await screen.findByText("Detail A");
    await act(async () => pending.resolve());
    expect(opened).not.toHaveBeenCalled();
  });
  it("R2 allows the replacement document in the same slot while the old operation is pending", async () => {
    const pending = deferred<void>(); const create = vi.fn().mockReturnValueOnce(pending.promise).mockResolvedValue(undefined);
    const a = item("A"); a.actions = [{ action_key: "create", label: "Tạo", available: true, disabled_reason: null, required_permissions: [] }];
    const b = { ...a, document_id: "B", label: "B" };
    const props = { ...defaults, contextKey: "event", onLoadDocumentDetail: vi.fn(), onCreateDocument: create };
    const view = render(<ContextualDocumentSection {...props} items={[a]} />);
    fireEvent.click(screen.getByRole("button", { name: "Tạo A" }));
    view.rerender(<ContextualDocumentSection {...props} items={[b]} />);
    fireEvent.click(screen.getByRole("button", { name: "Tạo B" }));
    expect(create).toHaveBeenCalledTimes(2); expect(create.mock.calls[1][0].document_id).toBe("B");
    await act(async () => pending.resolve());
  });
  it("R3 loads owned detail for a second slot sharing the same document ID", async () => {
    const a = item("A"); const b = { ...a, checklist_key: "slot-B", label: "B" };
    const load = vi.fn(async id => detail(id));
    render(<ContextualDocumentSection {...defaults} contextKey="event" items={[a, b]} onLoadDocumentDetail={load} />);
    fireEvent.click(screen.getByRole("button", { name: "Chọn A" })); await screen.findByText("Detail A");
    fireEvent.click(screen.getByRole("button", { name: "Chọn B" }));
    expect(await screen.findByText("Detail A")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chọn B" })).toHaveAttribute("aria-pressed", "true");
    expect(load).toHaveBeenCalledTimes(2);
  });
  it.each([403, 404, 409])("ignores stale metadata %s after same-event A → B → A", async status => {
    const first = deferred<DocumentDetail>();
    const load = vi.fn().mockReturnValueOnce(first.promise).mockImplementation(async id => detail(id));
    render(<ContextualDocumentSection {...defaults} contextKey="event" items={[item("A"), item("B")]} onLoadDocumentDetail={load} />);
    fireEvent.click(screen.getByRole("button", { name: "Chọn A" }));
    fireEvent.click(screen.getByRole("button", { name: "Chọn B" })); await screen.findByText("Detail B");
    fireEvent.click(screen.getByRole("button", { name: "Chọn A" })); await screen.findByText("Detail A");
    await act(async () => first.reject(Object.assign(new Error("old response"), { status })));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(); expect(screen.getByText("Detail A")).toBeInTheDocument();
    expect(load).toHaveBeenCalledTimes(3);
  });
  it.each([403, 404, 409])("ignores stale mutation %s and releases only its own full-identity lock", async status => {
    const first = deferred<void>(); const second = deferred<void>();
    const create = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const a = item("A"); a.actions = [{ action_key: "create", label: "Tạo", available: true, disabled_reason: null, required_permissions: [] }];
    const b = { ...a, document_id: "B", label: "B" };
    const props = { ...defaults, contextKey: "event", onLoadDocumentDetail: vi.fn(), onCreateDocument: create };
    const view = render(<ContextualDocumentSection {...props} items={[a]} />);
    fireEvent.click(screen.getByRole("button", { name: "Tạo A" }));
    view.rerender(<ContextualDocumentSection {...props} items={[b]} />);
    fireEvent.click(screen.getByRole("button", { name: "Tạo B" }));
    await act(async () => first.reject(Object.assign(new Error("old operation"), { status })));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tạo B" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Tạo B" })); expect(create).toHaveBeenCalledTimes(2);
    await act(async () => second.resolve()); expect(screen.getByRole("button", { name: "Tạo B" })).toBeEnabled();
  });
  it("invalidates a binary on same-slot ID replacement and cannot revive it by restoring the old ID", async () => {
    const pending = deferred<void>(); const opened = vi.fn(); const a = item("A");
    a.actions.push({ action_key: "open", label: "Mở", available: true, disabled_reason: null, required_permissions: [] });
    const props = { ...defaults, contextKey: "event", onLoadDocumentDetail: async (id: string) => detail(id), onOpenDocument: async (_item: ContextualDocumentAction, isCurrent?: () => boolean) => { await pending.promise; if (isCurrent?.()) opened(); } };
    const view = render(<ContextualDocumentSection {...props} items={[a]} />);
    fireEvent.click(screen.getByRole("button", { name: "Mở A" }));
    view.rerender(<ContextualDocumentSection {...props} items={[{ ...a, document_id: "B", label: "B" }]} />);
    view.rerender(<ContextualDocumentSection {...props} items={[a]} />);
    fireEvent.click(screen.getByRole("button", { name: "Chọn A" })); await screen.findByText("Detail A");
    await act(async () => pending.resolve()); expect(opened).not.toHaveBeenCalled();
  });
  it("moves focus without selecting or requesting; Enter selection and F6 move between panes", async () => {
    const load = vi.fn().mockImplementation(async id => detail(id));
    render(<ContextualDocumentSection {...defaults} items={[item("A"), item("B")]} onLoadDocumentDetail={load} />);
    const a = screen.getByRole("button", { name: "Chọn A" }); const b = screen.getByRole("button", { name: "Chọn B" });
    fireEvent.focus(a); fireEvent.keyDown(a, { key: "End" }); expect(b).toHaveFocus(); expect(load).not.toHaveBeenCalled();
    fireEvent.keyDown(b, { key: "Home" }); expect(a).toHaveFocus();
    fireEvent.keyDown(a, { key: "ArrowDown" }); expect(b).toHaveFocus();
    fireEvent.click(b); await screen.findByText("Detail B");
    fireEvent.keyDown(b, { key: "F6" }); expect(screen.getByRole("heading", { name: "Chi tiết tài liệu" })).toHaveFocus();
    fireEvent.keyDown(document.activeElement!, { key: "F6", shiftKey: true }); expect(b).toHaveFocus();
    fireEvent.keyDown(b, { key: "ArrowUp" }); expect(a).toHaveFocus(); expect(b).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(b); expect(load).toHaveBeenCalledTimes(1);
    expect(screen.getByText("version-B")).toBeInTheDocument(); expect(screen.getByText("rendition-B")).toBeInTheDocument();
  });
  it("opens the exact UUID on legacy-style double-click without conflating duplicate filenames", async () => {
    const open = vi.fn().mockResolvedValue(undefined); const load = vi.fn().mockImplementation(async id => detail(id));
    const a = item("A"); const b = item("B");
    a.actions.push({ action_key: "open", label: "Mở", available: true, disabled_reason: null, required_permissions: [] });
    b.actions.push({ action_key: "open", label: "Mở", available: true, disabled_reason: null, required_permissions: [] });
    render(<ContextualDocumentSection {...defaults} contextKey="event" items={[a, b]} onLoadDocumentDetail={load} onOpenDocument={open} />);
    const selected = screen.getByRole("button", { name: "Chọn B" });
    await act(async () => { selected.focus(); fireEvent.click(selected); fireEvent.click(selected); fireEvent.doubleClick(selected); });
    expect(open).toHaveBeenCalledTimes(1); expect(open.mock.calls[0][0].document_id).toBe("B");
    expect(open.mock.calls[0][0].original_filename).toBe(a.original_filename);
    expect(load).toHaveBeenCalledTimes(1); expect(load).toHaveBeenCalledWith("B"); expect(selected).toHaveFocus();
  });
  it("does not synthesize a double-click open action when the backend marks it unavailable", () => {
    const open = vi.fn(); const row = item("A");
    row.actions.push({ action_key: "open", label: "Mở", available: false, disabled_reason: "Chưa sẵn sàng", required_permissions: [] });
    render(<ContextualDocumentSection {...defaults} items={[row]} onLoadDocumentDetail={vi.fn()} onOpenDocument={open} />);
    fireEvent.doubleClick(screen.getByRole("button", { name: "Chọn A" }));
    expect(open).not.toHaveBeenCalled();
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
  it.each([401, 403, 404, 409, 422])("presents %s without retrying the supported create action", async status => {
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

describe("contextual document lookup ownership and accessible filtering", () => {
  it("filters canonical name, filename and status accent-insensitively without fetching or mutating", () => {
    const a = item("A");
    a.label = "Kế hoạch kiểm tra";
    a.original_filename = "Kế hoạch đợt tái kiểm.docx";
    const b = item("B");
    b.label = "Báo cáo khắc phục";
    b.status = "missing";
    b.document_id = null;
    b.original_filename = null;
    const c = item("C");
    c.label = "Quyết định";
    c.original_filename = "QD-KT-2026.docx";
    const load = vi.fn(), open = vi.fn(), create = vi.fn();
    render(<ContextualDocumentSection contextKey="case-A" items={[a, b, c]}
      onLoadDocumentDetail={load} onOpenDocument={open} onCreateDocument={create} />);
    expect(screen.getByText("Hiển thị 3/3 tài liệu.")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Tìm tài liệu liên quan" }), { target: { value: "ke hoach dot tai" } });
    expect(screen.getByText("Hiển thị 1/3 tài liệu.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chọn Kế hoạch kiểm tra" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Chọn Báo cáo khắc phục" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Xóa lọc tài liệu" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Lọc trạng thái tài liệu" }), { target: { value: "missing" } });
    expect(screen.getByRole("button", { name: "Chọn Báo cáo khắc phục" })).toBeInTheDocument();
    expect(screen.getByText("Hiển thị 1/3 tài liệu.")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Tìm tài liệu liên quan" }), { target: { value: "khong-co" } });
    expect(screen.getByText("Không có tài liệu khớp bộ lọc.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Xóa lọc tài liệu" }));
    expect(screen.getByText("Hiển thị 3/3 tài liệu.")).toBeInTheDocument();
    expect(load).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
    expect(create).not.toHaveBeenCalled();
  });

  it("navigates only filtered visible document rows with arrow/Home/End and avoids opening any binary", () => {
    const a = item("A"), b = item("B"), c = item("C");
    b.status = "missing";
    const open = vi.fn(), create = vi.fn(), load = vi.fn();
    render(<ContextualDocumentSection contextKey="case-A" items={[a, b, c]}
      onLoadDocumentDetail={load} onOpenDocument={open} onCreateDocument={create} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Lọc trạng thái tài liệu" }), { target: { value: "available" } });
    const first = screen.getByRole("button", { name: "Chọn A" });
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowDown" });
    const last = screen.getByRole("button", { name: "Chọn C" });
    expect(last).toHaveFocus();
    fireEvent.keyDown(last, { key: "Home" });
    expect(first).toHaveFocus();
    fireEvent.keyDown(first, { key: "End" });
    expect(last).toHaveFocus();
    expect(screen.queryByRole("button", { name: "Chọn B" })).not.toBeInTheDocument();
    expect(load).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
    expect(create).not.toHaveBeenCalled();
  });

  it("invalidates late A detail when filtering A out, then opens B only on explicit selection", async () => {
    const first = deferred<DocumentDetail>();
    const load = vi.fn((id: string) => id === "A" ? first.promise : Promise.resolve(detail(id)));
    const open = vi.fn(), create = vi.fn();
    render(<ContextualDocumentSection contextKey="case-A" items={[item("A"), item("B")]}
      onLoadDocumentDetail={load} onOpenDocument={open} onCreateDocument={create} />);
    fireEvent.click(screen.getByRole("button", { name: "Chọn A" }));
    expect(load).toHaveBeenCalledExactlyOnceWith("A");
    fireEvent.change(screen.getByRole("textbox", { name: "Tìm tài liệu liên quan" }), { target: { value: "B" } });
    expect(screen.getByText("Chọn tài liệu để xem chi tiết.")).toBeInTheDocument();
    await act(async () => first.resolve(detail("A")));
    expect(screen.queryByText("Detail A")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Chọn B" }));
    expect(await screen.findByText("Detail B")).toBeInTheDocument();
    expect(load).toHaveBeenCalledTimes(2);
    expect(open).not.toHaveBeenCalled();
    expect(create).not.toHaveBeenCalled();
  });

  it("isolates filters by context and reveals exact navigation slot without loading or creating", () => {
    const load = vi.fn(), open = vi.fn(), create = vi.fn();
    const first = item("A"); first.label = "A-exclusive";
    const second = item("B");
    const props = { onLoadDocumentDetail: load, onOpenDocument: open, onCreateDocument: create };
    const view = render(<ContextualDocumentSection {...props} contextKey="case-A" items={[first, second]} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Tìm tài liệu liên quan" }), { target: { value: "a-exclusive" } });
    expect(screen.queryByRole("button", { name: "Chọn B" })).not.toBeInTheDocument();
    view.rerender(<ContextualDocumentSection {...props} contextKey="case-A" initialSelectionKey="slot-B" items={[first, second]} />);
    expect(screen.getByRole("button", { name: "Chọn B" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("textbox", { name: "Tìm tài liệu liên quan" })).toHaveValue("");
    fireEvent.change(screen.getByRole("textbox", { name: "Tìm tài liệu liên quan" }), { target: { value: "a-exclusive" } });
    view.rerender(<ContextualDocumentSection {...props} contextKey="case-B" items={[first, second]} />);
    expect(screen.getByRole("textbox", { name: "Tìm tài liệu liên quan" })).toHaveValue("");
    expect(screen.getByText("Hiển thị 2/2 tài liệu.")).toBeInTheDocument();
    view.rerender(<ContextualDocumentSection {...props} contextKey="case-A" items={[first, second]} />);
    expect(screen.getByRole("textbox", { name: "Tìm tài liệu liên quan" })).toHaveValue("");
    expect(load).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
    expect(create).not.toHaveBeenCalled();
  });
});
