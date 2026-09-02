import { useEffect, useState } from "react";

import type { CaseWorkspace, CaseWorkspaceEvaluationScope, EvaluationScopeUpsertRequest } from "../../types";

type DraftBlock = { name: string; note: string; selected: Record<string, string> };

const emptyEvaluationScope: CaseWorkspaceEvaluationScope = {
  id: null, row_version: null, source_classification: null, rendered_prose: null, summary_text: null,
  summary_source: null, limitation_text: null, editable: false,
  read_only_reason: "Chưa có phạm vi đánh giá canonical cho hồ sơ này.", taxonomy_version_id: null,
  gxp_type: "", blocks: [], taxonomy_nodes: [],
};

function buildDraft(scope: CaseWorkspaceEvaluationScope): DraftBlock[] {
  return scope.blocks.map((block) => ({
    name: block.name ?? "", note: block.note ?? "",
    selected: Object.fromEntries(block.selections.map((selection) => [selection.taxonomy_node_id, selection.custom_description])),
  }));
}

function initialExpandedNodeIds(scope: CaseWorkspaceEvaluationScope): Set<string> {
  const parentById = new Map(scope.taxonomy_nodes.map((node) => [node.id, node.parent_id]));
  const expanded = new Set<string>();
  for (const block of scope.blocks) for (const selection of block.selections) {
    let parentId = parentById.get(selection.taxonomy_node_id) ?? null;
    while (parentId) { expanded.add(parentId); parentId = parentById.get(parentId) ?? null; }
  }
  return expanded;
}

function EvaluationScopeEditorDialog({ scope, onClose, onSave }: {
  scope: CaseWorkspaceEvaluationScope;
  onClose: () => void;
  onSave: (payload: EvaluationScopeUpsertRequest) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(() => initialExpandedNodeIds(scope));
  const [activeBlock, setActiveBlock] = useState(0);
  const [draft, setDraft] = useState(() => buildDraft(scope));
  const [limitation, setLimitation] = useState(scope.limitation_text ?? "");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const nodesById = new Map(scope.taxonomy_nodes.map((node) => [node.id, node]));
  const nodesByParent = new Map<string | null, string[]>();
  for (const node of scope.taxonomy_nodes) nodesByParent.set(node.parent_id, [...(nodesByParent.get(node.parent_id) ?? []), node.id]);
  const block = draft[activeBlock];
  const selectedIds = new Set(Object.keys(block?.selected ?? {}));
  const descendantsOf = (nodeId: string): string[] => {
    const descendants: string[] = [];
    const visit = (parentId: string) => { for (const childId of nodesByParent.get(parentId) ?? []) { descendants.push(childId); visit(childId); } };
    visit(nodeId);
    return descendants;
  };
  const ancestorsExpanded = (nodeId: string) => {
    let parentId = nodesById.get(nodeId)?.parent_id ?? null;
    while (parentId) { if (!expanded.has(parentId)) return false; parentId = nodesById.get(parentId)?.parent_id ?? null; }
    return true;
  };
  const treeState = (nodeId: string) => selectedIds.has(nodeId) ? "checked" : descendantsOf(nodeId).some((id) => selectedIds.has(id)) ? "mixed" : "unchecked";
  const updateBlock = (index: number, update: (current: DraftBlock) => DraftBlock) => setDraft((current) => current.map((item, itemIndex) => itemIndex === index ? update(item) : item));
  const toggle = (nodeId: string) => {
    if (!block) return;
    updateBlock(activeBlock, (current) => {
      const selected = { ...current.selected };
      const selecting = selected[nodeId] === undefined;
      for (const affectedId of [nodeId, ...descendantsOf(nodeId)]) {
        if (selecting) selected[affectedId] ??= ""; else delete selected[affectedId];
      }
      return { ...current, selected };
    });
  };
  const addBlock = () => { setDraft((current) => [...current, { name: "", note: "", selected: {} }]); setActiveBlock(draft.length); };
  const removeActiveBlock = () => {
    if (draft.length <= 1) return;
    setDraft((current) => current.filter((_, index) => index !== activeBlock));
    setActiveBlock((current) => Math.max(0, current - 1));
  };
  async function save() {
    if (!scope.row_version || pending) return;
    setPending(true); setError(null);
    try {
      await onSave({ expected_version: scope.row_version, limitation_text: limitation || null, blocks: draft.map((item) => ({ name: item.name || null, note: item.note || null, selections: Object.entries(item.selected).map(([taxonomy_node_id, custom_description]) => ({ taxonomy_node_id, custom_description })) })) });
      onClose();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Không lưu được phạm vi đánh giá.");
    } finally { setPending(false); }
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape" && !pending) onClose(); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, pending]);

  return <div className="dialog-backdrop" role="presentation">
    <section aria-labelledby="evaluation-scope-dialog-title" aria-modal="true" className="panel evaluation-scope-dialog" role="dialog">
      <header className="panel-header evaluation-scope-dialog-header">
        <div><h2 id="evaluation-scope-dialog-title">Sửa phạm vi đánh giá</h2><p>Chọn taxonomy, cập nhật mô tả tùy chỉnh và lưu một aggregate duy nhất.</p></div>
      </header>
      <div aria-label="Các phạm vi đánh giá" className="evaluation-scope-block-tabs" role="tablist">
        {draft.map((item, index) => <button aria-selected={activeBlock === index} className={activeBlock === index ? "active" : ""} key={`scope-block-${index}`} onClick={() => setActiveBlock(index)} role="tab" type="button">{item.name || `Phạm vi ${index + 1}`}</button>)}
      </div>
      {block ? <div className="evaluation-scope-editor">
        <div className="evaluation-scope-block-header">
          <label>Tên phạm vi<input value={block.name} onChange={(event) => updateBlock(activeBlock, (current) => ({ ...current, name: event.target.value }))} /></label>
          <label>Ghi chú<textarea value={block.note} onChange={(event) => updateBlock(activeBlock, (current) => ({ ...current, note: event.target.value }))} /></label>
        </div>
        <div aria-label="Cây phạm vi đánh giá" className="evaluation-scope-tree" role="tree">
          {scope.taxonomy_nodes.map((node) => {
            const hasChildren = (nodesByParent.get(node.id) ?? []).length > 0;
            if (!ancestorsExpanded(node.id)) return null;
            const state = treeState(node.id);
            const isSelected = selectedIds.has(node.id);
            const customDescription = block.selected[node.id] ?? "";
            const depth = node.key.split(".").length - 1;
            return <div aria-expanded={hasChildren ? expanded.has(node.id) : undefined} className={`evaluation-scope-node depth-${Math.min(depth, 2)} ${isSelected ? "is-selected" : ""}`} key={node.id} role="treeitem" style={{ paddingInlineStart: `${depth * 1.1}rem` }} title={node.hint ?? undefined}>
              {hasChildren ? <button aria-label={`${expanded.has(node.id) ? "Thu gọn" : "Mở rộng"} ${node.key}`} className={`tree-expand ${expanded.has(node.id) ? "is-expanded" : ""}`} onClick={() => setExpanded((current) => { const next = new Set(current); if (next.has(node.id)) next.delete(node.id); else next.add(node.id); return next; })} type="button"><span /></button> : <span className="tree-spacer" />}
              <button aria-checked={state === "mixed" ? "mixed" : state === "checked"} aria-label={`Chọn ${node.key}`} className={`tree-check ${state}`} onClick={() => toggle(node.id)} role="checkbox" type="button"><span /></button>
              <span className="tree-key">{node.key}</span>
              <div className="tree-copy"><span className="tree-taxonomy-description">{node.description}</span>
                {isSelected ? <textarea aria-label={`Mô tả tùy chỉnh ${node.key}`} className="tree-custom-input" onChange={(event) => updateBlock(activeBlock, (current) => ({ ...current, selected: { ...current.selected, [node.id]: event.target.value } }))} placeholder="Mô tả tùy chỉnh (để trống nếu không có)" value={customDescription} /> : null}
              </div>
            </div>;
          })}
        </div>
        <label className="evaluation-scope-limitation">Giới hạn<textarea value={limitation} onChange={(event) => setLimitation(event.target.value)} /></label>
      </div> : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      <div className="panel-actions evaluation-scope-dialog-actions">
        <button disabled={pending} onClick={addBlock} type="button">Thêm phạm vi</button>
        <button disabled={pending || draft.length <= 1} onClick={removeActiveBlock} type="button">Bỏ phạm vi</button>
        <button disabled={pending} onClick={() => void save()} type="button">{pending ? "Đang lưu..." : "Lưu"}</button>
        <button disabled={pending} onClick={onClose} type="button">Hủy</button>
      </div>
    </section>
  </div>;
}

export function EvaluationScopeWorkspace({ caseWorkspace, onSave }: {
  caseWorkspace: CaseWorkspace;
  onSave: (payload: EvaluationScopeUpsertRequest) => Promise<void>;
}) {
  const scope = caseWorkspace.evaluation_scope ?? emptyEvaluationScope;
  const [editorOpen, setEditorOpen] = useState(false);
  useEffect(() => setEditorOpen(false), [scope.id, scope.row_version]);
  if (!scope.id) return <p className="workspace-note">{scope.read_only_reason}</p>;
  const isHistorical = scope.summary_source === "historical_prose";
  return <section className="workspace-section evaluation-scope-workspace">
    <header className="workspace-section-header">
      <h4>{isHistorical ? "Phạm vi đánh giá lịch sử" : "Phạm vi đánh giá"}</h4>
      {scope.editable ? <button className="secondary" onClick={() => setEditorOpen(true)} type="button">Sửa phạm vi</button> : null}
    </header>
    {scope.read_only_reason ? <p className="workspace-note">{scope.read_only_reason}</p> : null}
    <pre className="evaluation-scope-summary">{scope.summary_text || "Chưa có nội dung phạm vi để hiển thị."}</pre>
    {scope.summary_source === "legacy_rendered_prose" ? <p className="workspace-note">Hiển thị theo văn bản legacy đã lưu; sau khi chỉnh sửa, summary sẽ được tạo từ aggregate canonical hiện hành.</p> : null}
    {editorOpen ? <EvaluationScopeEditorDialog scope={scope} onClose={() => setEditorOpen(false)} onSave={onSave} /> : null}
  </section>;
}
