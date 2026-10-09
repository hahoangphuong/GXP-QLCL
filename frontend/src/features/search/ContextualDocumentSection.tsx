import { useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";

import type { ContextualDocumentAction, DocumentDetail } from "../../types";
import { formatCompactDate } from "../../lib/presentation";

type Selection = { context: string; key: string; id: string | null };
type Request = Selection & { generation: number; sequence: number; pending: boolean; detail?: DocumentDetail; error?: string };

function sameSelection(left: Selection | null | undefined, right: Selection) {
  return left?.context === right.context && left.key === right.key && left.id === right.id;
}

function message(error: unknown): string {
  const status = (error as { status?: number } | null)?.status;
  const explanation = status === 403 ? "Bạn không có quyền thao tác tài liệu."
    : status === 404 ? "Tài liệu không còn khả dụng trong ngữ cảnh này."
      : status === 409 ? "Tài liệu đã thay đổi. Kiểm tra lại dữ liệu trước khi thao tác tiếp." : "Không thực hiện được thao tác tài liệu.";
  return `${explanation}${error instanceof Error ? ` ${error.message}` : ""}`;
}

export function ContextualDocumentSection({ items, contextKey, onOpenDocument, onLoadDocumentDetail, onCreateDocument }: {
  items: ContextualDocumentAction[];
  contextKey?: string;
  onOpenDocument: (item: ContextualDocumentAction, isCurrentDocument?: () => boolean) => Promise<void>;
  onLoadDocumentDetail: (documentId: string) => Promise<DocumentDetail>;
  onCreateDocument: (item: ContextualDocumentAction, action: ContextualDocumentAction["actions"][number]) => Promise<void>;
}) {
  const context = contextKey ?? JSON.stringify(items.map(item => [item.parent_scope, item.parent_id, item.workflow_step]));
  const headingId = useId();
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [request, setRequest] = useState<Request | null>(null);
  const [operation, setOperation] = useState<Request | null>(null);
  const [selectionContext, setSelectionContext] = useState(context);
  // Reset before commit, including returning to a previously visited context.
  if (selectionContext !== context) {
    setSelectionContext(context);
    setSelection(null);
    setRequest(null);
    setOperation(null);
    setFocusKey(null);
  }
  const sequence = useRef(0);
  const selectionGeneration = useRef(0);
  const operationSequence = useRef(0);
  const committed = useRef<{ context: string; items: ContextualDocumentAction[] } | null>(null);
  const inFlight = useRef(new Set<string>());
  const pendingHistory = useRef<Request | null>(null);
  const operationFocus = useRef<(Selection & { generation: number; element: HTMLElement }) | null>(null);
  const selectedIdentity = useRef(selection);
  useLayoutEffect(() => { selectedIdentity.current = selection; }, [selection]);
  useLayoutEffect(() => {
    if (committed.current?.context !== context) {
      selectionGeneration.current++;
      sequence.current++;
      operationSequence.current++;
    }
    committed.current = { context, items };
    const selectedTarget = selectedIdentity.current;
    if (selectedTarget && !items.some(item => item.checklist_key === selectedTarget.key && item.document_id === selectedTarget.id)) {
      selectionGeneration.current++;
      sequence.current++;
      selectedIdentity.current = null;
      setSelection(null);
    }
  }, [context, items]);
  useLayoutEffect(() => () => { committed.current = null; selectionGeneration.current++; sequence.current++; operationSequence.current++; }, []);
  useLayoutEffect(() => {
    if (operation?.pending) return;
    const target = operationFocus.current;
    if (target?.generation === selectionGeneration.current && sameSelection(selectedIdentity.current, target) && document.activeElement === document.body
      && target.element.isConnected && !target.element.matches(":disabled") && !target.element.closest("[hidden],[inert]")) target.element.focus();
    operationFocus.current = null;
  }, [context, operation]);

  const selected = selection?.context === context
    ? items.find(item => item.checklist_key === selection.key && item.document_id === selection.id) : undefined;
  const owned = selected && request?.generation === selectionGeneration.current && sameSelection(request, { context, key: selected.checklist_key, id: selected.document_id }) ? request : null;
  const ownedOperation = operation?.context === context && items.some(item => item.checklist_key === operation.key && item.document_id === operation.id) ? operation : null;
  const visibleOperation = selected?.checklist_key === ownedOperation?.key && selected?.document_id === ownedOperation?.id
    && (ownedOperation?.pending || ownedOperation?.generation === selectionGeneration.current) ? ownedOperation : null;
  const effectiveFocus = items.some(item => item.checklist_key === focusKey) ? focusKey : items[0]?.checklist_key;

  function current(target: Selection) {
    return committed.current?.context === target.context && committed.current.items.some(item => item.checklist_key === target.key && item.document_id === target.id);
  }
  function select(target: Selection) {
    if (!sameSelection(selectedIdentity.current, target)) {
      selectionGeneration.current++;
      sequence.current++;
    }
    // Update synchronously too: batched A → B → A must never revive A's epoch.
    selectedIdentity.current = target;
    setSelection(target);
    return selectionGeneration.current;
  }
  function currentSelection(target: Selection, generation: number) {
    return current(target) && selectionGeneration.current === generation && sameSelection(selectedIdentity.current, target);
  }
  async function history(item: ContextualDocumentAction, explicit = false) {
    const target: Selection = { context, key: item.checklist_key, id: item.document_id };
    const generation = select(target);
    if (!item.document_id || !item.actions.some(action => action.action_key === "history" && action.available)) return;
    if (pendingHistory.current?.context === context && pendingHistory.current.key === target.key
      && pendingHistory.current.id === target.id && pendingHistory.current.sequence === sequence.current) return;
    if (!explicit && owned?.generation === generation && sameSelection(owned, target) && (owned.pending || owned.detail)) return;
    const token = ++sequence.current;
    pendingHistory.current = { ...target, generation, sequence: token, pending: true };
    setRequest({ ...target, generation, sequence: token, pending: true });
    try {
      const detail = await onLoadDocumentDetail(item.document_id);
      if (!currentSelection(target, generation) || sequence.current !== token) return;
      if (detail.document_id !== item.document_id || detail.family_code !== item.family_code
        || (item.parent_scope === "case" ? detail.case_id !== item.parent_id : detail.capa_cycle_id !== item.parent_id)) {
        throw new Error("Chi tiết tài liệu không khớp định danh được backend cấp.");
      }
      setRequest({ ...target, generation, sequence: token, pending: false, detail });
    } catch (error) {
      if (currentSelection(target, generation) && sequence.current === token) setRequest({ ...target, generation, sequence: token, pending: false, error: message(error) });
    } finally { if (pendingHistory.current?.sequence === token) pendingHistory.current = null; }
  }
  async function act(item: ContextualDocumentAction, action: ContextualDocumentAction["actions"][number]) {
    if (!action.available) return;
    if (action.action_key === "history") { await history(item, true); return; }
    const target: Selection = { context, key: item.checklist_key, id: item.document_id };
    const key = JSON.stringify([context, item.checklist_key, item.document_id, action.action_key]);
    if (inFlight.current.has(key)) return;
    inFlight.current.add(key);
    const generation = select(target);
    sequence.current++;
    setRequest(previous => previous?.pending ? null : previous);
    if (document.activeElement instanceof HTMLElement) operationFocus.current = { ...target, generation, element: document.activeElement };
    const token = ++operationSequence.current;
    setOperation({ ...target, generation, sequence: token, pending: true });
    try {
      if (action.action_key === "open") await onOpenDocument(item, () => currentSelection(target, generation) && operationSequence.current === token);
      else await onCreateDocument(item, action);
      if (current(target) && operationSequence.current === token) setOperation(null);
    } catch (error) {
      if (current(target) && operationSequence.current === token) setOperation(currentSelection(target, generation)
        ? { ...target, generation, sequence: token, pending: false, error: message(error) } : null);
    } finally { inFlight.current.delete(key); }
  }
  function navigate(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const next = event.key === "ArrowDown" ? Math.min(index + 1, items.length - 1)
      : event.key === "ArrowUp" ? Math.max(index - 1, 0)
        : event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : null;
    if (next !== null) { event.preventDefault(); buttons.current.get(items[next].checklist_key)?.focus(); }
  }
  function returnToList() { buttons.current.get(selected?.checklist_key ?? effectiveFocus ?? "")?.focus(); }

  return (
    <section className="workspace-section document-workspace" aria-labelledby={headingId} onKeyDown={event => {
      if (event.key === "F6") {
        event.preventDefault();
        if (event.shiftKey || detailHeading.current?.parentElement?.contains(event.target as Node)) returnToList();
        else detailHeading.current?.focus();
      }
    }}>
      <h4 id={headingId}>Tài liệu liên quan</h4>
      <p className="workspace-note">↑/↓, Home/End di chuyển; Enter chọn tài liệu; F6 chuyển giữa danh sách và chi tiết.</p>
      {items.length === 0 ? <p role="status">Chưa có tài liệu trong ngữ cảnh này.</p> : null}
      <div className="document-workspace-panes">
        <div className="table-scroll document-list-pane">
          <table className="dense-table event-document-table" aria-label="Danh sách tài liệu liên quan">
            <thead><tr><th scope="col">Tài liệu</th><th scope="col">Trạng thái</th><th scope="col">Thao tác</th></tr></thead>
            <tbody>{items.map((item, index) => <tr key={item.checklist_key}>
              <td><button type="button" className="document-select" aria-label={`Chọn ${item.label}`} aria-pressed={selected?.checklist_key === item.checklist_key}
                tabIndex={effectiveFocus === item.checklist_key ? 0 : -1}
                ref={element => { if (element) buttons.current.set(item.checklist_key, element); else buttons.current.delete(item.checklist_key); }}
                onFocus={() => setFocusKey(item.checklist_key)} onKeyDown={event => navigate(event, index)} onClick={() => void history(item)}>
                <strong>{item.label}</strong><span>{item.original_filename ?? "Chưa có tệp"}</span>
              </button></td>
              <td>{item.status === "available" ? "Đã có tài liệu" : "Chưa có tài liệu"}</td>
              <td><div className="contextual-document-actions">{item.actions.filter(action => action.action_key !== "create" || action.available).map(action => <button
                key={action.action_key} type="button" aria-label={`${action.label} ${item.label}`} title={action.disabled_reason ?? undefined}
                disabled={!action.available || (ownedOperation?.pending && ownedOperation.key === item.checklist_key) || (action.action_key === "history" && owned?.pending && owned.key === item.checklist_key)}
                onClick={() => void act(item, action)}>{action.label}</button>)}</div>
                {item.actions.filter(action => !action.available && action.disabled_reason).map(action => <p key={action.action_key} className="workspace-note">{action.disabled_reason}</p>)}
              </td>
            </tr>)}</tbody>
          </table>
        </div>
        <div className="document-detail-shell document-detail-pane">
          <h5 ref={detailHeading} tabIndex={-1}>Chi tiết tài liệu</h5>
          <button type="button" onClick={returnToList}>Về danh sách tài liệu</button>
          {!selected ? <p role="status">Chọn tài liệu để xem chi tiết.</p> : <>
            <p><strong>{selected.label}</strong> · {selected.document_id ?? "Chưa có document ID"}</p>
            {owned?.pending ? <p role="status">Đang tải lịch sử tài liệu...</p> : null}
            {owned?.error ? <p className="form-error" role="alert">{owned.error}</p> : null}
            {owned?.detail ? <>
              <p>Lịch sử tài liệu</p>
              <p>{owned.detail.title ?? owned.detail.family_code}</p>
              <div className="table-scroll"><table className="dense-table event-document-table" aria-label="Phiên bản và rendition tài liệu">
                <thead><tr><th scope="col">Rendition / ID</th><th scope="col">Phiên bản / ID</th><th scope="col">Tệp / Ngày</th></tr></thead>
                <tbody>{owned.detail.variants.flatMap(variant => variant.versions.map(version => <tr key={JSON.stringify([variant.id, version.id])}>
                  <td>{variant.variant_type} · {variant.language_code}<small>{variant.id}</small></td>
                  <td>v{version.version_no}{version.is_current ? " (hiện hành)" : ""}<small>{version.id}</small></td>
                  <td>{version.original_filename ?? "Chưa có tên tệp"}<small>{formatCompactDate(version.issued_on)}</small></td>
                </tr>))}</tbody>
              </table></div>
              {owned.detail.variants.every(variant => variant.versions.length === 0) ? <p role="status">Chưa có phiên bản tài liệu.</p> : null}
            </> : null}
          </>}
          {visibleOperation?.pending ? <p role="status">Đang thực hiện thao tác tài liệu...</p> : null}
          {visibleOperation?.error ? <p className="form-error" role="alert">{visibleOperation.error}</p> : null}
        </div>
      </div>
    </section>
  );
}
