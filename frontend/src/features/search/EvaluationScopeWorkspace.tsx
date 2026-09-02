import { useEffect, useState } from "react";

import type { CaseWorkspace, EvaluationScopeUpsertRequest } from "../../types";

type DraftBlock = { name: string; note: string; selected: Record<string, string> };

const emptyEvaluationScope = {
  id: null,
  row_version: null,
  source_classification: null,
  rendered_prose: null,
  limitation_text: null,
  editable: false,
  read_only_reason: "Chưa có phạm vi đánh giá canonical cho hồ sơ này.",
  taxonomy_version_id: null,
  gxp_type: "",
  blocks: [],
  taxonomy_nodes: [],
};

function buildDraft(caseWorkspace: CaseWorkspace): DraftBlock[] {
  return (caseWorkspace.evaluation_scope?.blocks ?? []).map((block) => ({
    name: block.name ?? "",
    note: block.note ?? "",
    selected: Object.fromEntries(block.selections.map((selection) => [selection.taxonomy_node_id, selection.custom_description])),
  }));
}

export function EvaluationScopeWorkspace({
  caseWorkspace,
  onSave,
}: {
  caseWorkspace: CaseWorkspace;
  onSave: (payload: EvaluationScopeUpsertRequest) => Promise<void>;
}) {
  const scope = caseWorkspace.evaluation_scope ?? emptyEvaluationScope;
  const [editing, setEditing] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [activeBlock, setActiveBlock] = useState(0);
  const [draft, setDraft] = useState<DraftBlock[]>(() => buildDraft(caseWorkspace));
  const [limitation, setLimitation] = useState(scope.limitation_text ?? "");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const nodesByParent = new Map<string | null, string[]>();
  for (const node of scope.taxonomy_nodes) {
    const siblings = nodesByParent.get(node.parent_id) ?? [];
    siblings.push(node.id);
    nodesByParent.set(node.parent_id, siblings);
  }
  const descendantsOf = (nodeId: string): string[] => {
    const descendants: string[] = [];
    const visit = (parentId: string) => {
      for (const childId of nodesByParent.get(parentId) ?? []) {
        descendants.push(childId);
        visit(childId);
      }
    };
    visit(nodeId);
    return descendants;
  };
  const ancestorsExpanded = (nodeId: string) => {
    let parentId = scope.taxonomy_nodes.find((node) => node.id === nodeId)?.parent_id ?? null;
    while (parentId) {
      if (!expanded.has(parentId)) return false;
      parentId = scope.taxonomy_nodes.find((node) => node.id === parentId)?.parent_id ?? null;
    }
    return true;
  };

  useEffect(() => {
    if (!editing) {
      setDraft(buildDraft(caseWorkspace));
      setLimitation(scope.limitation_text ?? "");
      setActiveBlock(0);
      setError(null);
    }
  }, [caseWorkspace, editing, scope.limitation_text]);

  if (!scope.id) {
    return <p className="workspace-note">{scope.read_only_reason}</p>;
  }
  if (scope.source_classification === "PROSE_ONLY") {
    return <section className="workspace-section"><h4>Phạm vi đánh giá</h4><pre className="evaluation-scope-prose">{scope.rendered_prose}</pre></section>;
  }
  const block = draft[activeBlock];
  const parentIds = new Set(scope.taxonomy_nodes.map((node) => node.parent_id).filter(Boolean));
  const selectedIds = new Set(Object.keys(block?.selected ?? {}));
  const treeState = (nodeId: string) => {
    const descendants = descendantsOf(nodeId);
    if (selectedIds.has(nodeId)) return "checked";
    return descendants.some((descendantId) => selectedIds.has(descendantId)) ? "mixed" : "unchecked";
  };
  const toggle = (nodeId: string) => {
    if (!editing || !block) return;
    setDraft((current) => current.map((item, index) => {
      if (index !== activeBlock) return item;
      const selected = { ...item.selected };
      const affectedIds = [nodeId, ...descendantsOf(nodeId)];
      const selecting = selected[nodeId] === undefined;
      for (const affectedId of affectedIds) {
        if (selecting) selected[affectedId] ??= "";
        else delete selected[affectedId];
      }
      return { ...item, selected };
    }));
  };
  const updateBlock = (index: number, update: (block: DraftBlock) => DraftBlock) => {
    setDraft((current) => current.map((item, itemIndex) => itemIndex === index ? update(item) : item));
  };
  const addBlock = () => {
    setDraft((current) => [...current, { name: "", note: "", selected: {} }]);
    setActiveBlock(draft.length);
  };
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
      setEditing(false);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Không lưu được phạm vi đánh giá.");
    } finally { setPending(false); }
  }
  return (
    <section className="workspace-section evaluation-scope-workspace">
      <header className="workspace-section-header"><h4>Phạm vi đánh giá</h4>{editing ? <div className="panel-actions"><button disabled={pending} onClick={addBlock} type="button">Thêm phạm vi</button><button disabled={pending || draft.length <= 1} onClick={removeActiveBlock} type="button">Bỏ phạm vi</button><button disabled={pending} onClick={() => void save()} type="button">Lưu</button><button disabled={pending} onClick={() => setEditing(false)} type="button">Hủy</button></div> : null}</header>
      {scope.read_only_reason ? <p className="workspace-note">{scope.read_only_reason}</p> : null}
      <div className="evaluation-scope-block-tabs">{draft.map((item, index) => <button className={activeBlock === index ? "active" : ""} key={`scope-block-${index}`} onClick={() => setActiveBlock(index)} type="button">{item.name || `Phạm vi ${index + 1}`}</button>)}</div>
      {block ? <div className="evaluation-scope-layout" onDoubleClick={() => scope.editable && setEditing(true)} onKeyDown={(event) => { if (!editing && scope.editable && (event.key === "Enter" || event.key === "F2")) { event.preventDefault(); setEditing(true); } }} tabIndex={scope.editable ? 0 : undefined}>
        <div className="evaluation-scope-tree" role="tree" aria-label="Cây phạm vi đánh giá">
          {scope.taxonomy_nodes.map((node) => {
            const hasChildren = parentIds.has(node.id); const visible = ancestorsExpanded(node.id); if (!visible) return null;
            return <div className="evaluation-scope-node" key={node.id} role="treeitem" style={{ paddingLeft: `${node.key.split(".").length * 14}px` }} title={node.hint ?? undefined}>
              {hasChildren ? <button aria-label={`Mở rộng ${node.key}`} onClick={() => setExpanded((current) => { const next = new Set(current); if (next.has(node.id)) next.delete(node.id); else next.add(node.id); return next; })} type="button">{expanded.has(node.id) ? "−" : "+"}</button> : <span className="tree-spacer" />}
              <button aria-checked={treeState(node.id) === "mixed" ? "mixed" : treeState(node.id) === "checked"} className={`tree-check ${treeState(node.id)}`} disabled={!editing} onClick={() => toggle(node.id)} onKeyDown={(event) => { if (editing && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); toggle(node.id); } }} role="checkbox" type="button">{treeState(node.id) === "checked" ? "✓" : treeState(node.id) === "mixed" ? "−" : ""}</button>
              <strong>{node.key}</strong><span>{node.description}</span>
            </div>;
          })}
        </div>
        <div className="evaluation-scope-detail">
          <label>Tên phạm vi<input disabled={!editing} value={block.name} onChange={(event) => updateBlock(activeBlock, (item) => ({ ...item, name: event.target.value }))} /></label>
          <label>Ghi chú<textarea disabled={!editing} value={block.note} onChange={(event) => updateBlock(activeBlock, (item) => ({ ...item, note: event.target.value }))} /></label>
          <label>Giới hạn<textarea disabled={!editing} value={limitation} onChange={(event) => setLimitation(event.target.value)} /></label>
          {Object.entries(block.selected).map(([nodeId, text]) => <label key={nodeId}>Mô tả tùy chỉnh {scope.taxonomy_nodes.find((node) => node.id === nodeId)?.key}<textarea disabled={!editing} value={text} onChange={(event) => updateBlock(activeBlock, (item) => ({ ...item, selected: { ...item.selected, [nodeId]: event.target.value } }))} /></label>)}
          {scope.blocks[activeBlock]?.unkeyed_entries.map((item) => <p className="workspace-note" key={item.source_order}>{item.text}</p>)}
        </div>
      </div> : null}
      {!editing && scope.editable ? <p className="workspace-note">Nhấp đúp vào vùng cây hoặc nhấn Enter/F2 để chỉnh sửa.</p> : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
    </section>
  );
}
