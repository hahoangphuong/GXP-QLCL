import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CaseWorkspace } from "../../types";
import { EvaluationScopeWorkspace } from "./EvaluationScopeWorkspace";
import { CaseDraftSession } from "./CaseDraftSession";
import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";

function workspace(overrides: Partial<CaseWorkspace["evaluation_scope"]> = {}): CaseWorkspace {
  return {
    case_summary: { id: "case-1" },
    evaluation_scope: {
      id: "scope-1", row_version: 3, source_classification: "STRUCTURED_VALID", rendered_prose: "Legacy scope",
      summary_text: "Phạm vi canonical hiện hành", summary_source: "canonical_projection", limitation_text: null,
      editable: true, read_only_reason: null, taxonomy_version_id: "taxonomy-1", gxp_type: "GMP",
      blocks: [{ id: "block-1", ordinal: 1, name: "Khối một", note: null, selections: [{ taxonomy_node_id: "child", node_key_snapshot: "1.1", taxonomy_description_snapshot: "Child", custom_description: "Chi tiết riêng", source_order: 1 }], unkeyed_entries: [] }],
      taxonomy_nodes: [
        { id: "root", key: "1", parent_id: null, parent_key: null, description: "Root", hint: "Gợi ý", main_topic: null, short_render: null, no_expand: null, source_order: 1 },
        { id: "child", key: "1.1", parent_id: "root", parent_key: "1", description: "Child", hint: null, main_topic: null, short_render: null, no_expand: null, source_order: 2 },
      ],
      ...overrides,
    },
  } as CaseWorkspace;
}

describe("EvaluationScopeWorkspace", () => {
  it("moves keyboard focus independently of the visible scope and performs no mutation on navigation", () => {
    const onSave = vi.fn();
    render(<EvaluationScopeWorkspace caseWorkspace={workspace()} onSave={onSave} />);
    const evaluation = screen.getByRole("tab", { name: "Phạm vi đánh giá" });
    const certificate = screen.getByRole("tab", { name: "Phạm vi chứng nhận GPs" });
    evaluation.focus();
    fireEvent.keyDown(evaluation, { key: "ArrowRight" });
    expect(certificate).toHaveFocus();
    expect(evaluation).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Phạm vi đánh giá" })).toBeVisible();
    fireEvent.click(certificate);
    expect(screen.getByRole("tabpanel", { name: "Phạm vi chứng nhận GPs" })).toBeVisible();
    expect(screen.getByText("Phạm vi canonical hiện hành")).not.toBeVisible();
    fireEvent.keyDown(certificate, { key: "Home" });
    expect(evaluation).toHaveFocus();
    fireEvent.click(evaluation);
    expect(screen.getByText("Phạm vi canonical hiện hành")).toBeVisible();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("renders only compact canonical summary until the editor is explicitly opened", () => {
    render(<EvaluationScopeWorkspace caseWorkspace={workspace()} onSave={vi.fn()} />);
    expect(screen.getByText("Phạm vi canonical hiện hành")).toBeVisible();
    expect(screen.getByRole("button", { name: "Sửa phạm vi" })).toBeVisible();
    expect(screen.queryByRole("tree")).not.toBeInTheDocument();
    expect(screen.queryByText("Child")).not.toBeInTheDocument();
  });

  it("opens a modal tree editor with selected ancestry and inline custom description", () => {
    render(<EvaluationScopeWorkspace caseWorkspace={workspace()} onSave={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Sửa phạm vi" }));
    expect(screen.getByRole("dialog", { name: "Sửa phạm vi đánh giá" })).toBeVisible();
    expect(screen.getByRole("tree")).toBeVisible();
    expect(screen.getByText("Root")).toBeVisible();
    expect(screen.getByText("Child")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Mô tả tùy chỉnh 1.1" })).toHaveValue("Chi tiết riêng");
    expect(screen.getByRole("checkbox", { name: "Chọn 1" })).toHaveAttribute("aria-checked", "mixed");
  });

  it("closes after successful save and submits the existing aggregate payload", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<EvaluationScopeWorkspace caseWorkspace={workspace()} onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Sửa phạm vi" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Mô tả tùy chỉnh 1.1" }), { target: { value: "Nội dung sửa" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ expected_version: 3, blocks: expect.any(Array) })));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Sửa phạm vi đánh giá" })).not.toBeInTheDocument());
  });

  it("keeps the modal and draft visible after a stale conflict", async () => {
    const onSave = vi.fn().mockRejectedValue(new Error("Stale evaluation scope update."));
    render(<EvaluationScopeWorkspace caseWorkspace={workspace()} onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Sửa phạm vi" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Mô tả tùy chỉnh 1.1" }), { target: { value: "Nội dung sửa" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Stale evaluation scope update.");
    expect(screen.getByRole("dialog", { name: "Sửa phạm vi đánh giá" })).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Mô tả tùy chỉnh 1.1" })).toHaveValue("Nội dung sửa");
  });

  it("renders prose-only scope as historical read-only text without a tree", () => {
    render(<EvaluationScopeWorkspace caseWorkspace={workspace({ source_classification: "PROSE_ONLY", rendered_prose: "Văn bản lưu trữ", summary_text: "Văn bản lưu trữ", summary_source: "historical_prose", editable: false, taxonomy_nodes: [] })} onSave={vi.fn()} />);
    expect(screen.getByText("Phạm vi đánh giá lịch sử")).toBeVisible();
    expect(screen.getByText("Văn bản lưu trữ")).toBeVisible();
    expect(screen.queryByRole("tree")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sửa phạm vi" })).not.toBeInTheDocument();
  });
});

describe("evaluation aggregate canonical command ownership", () => {
  function editor(id: string, save: (payload: import("../../types").EvaluationScopeUpsertRequest) => Promise<void>, current = workspace()) {
    return <CaseDraftSession identity={id}>
      <EvaluationScopeWorkspace caseWorkspace={{ ...current, case_summary: { id } } as CaseWorkspace} onSave={save} />
    </CaseDraftSession>;
  }

  it("preserves exact submitted aggregate, taxonomy UUIDs, limit and version across Case A → B → A, pending and unknown", async () => {
    let reject!: (reason: Error) => void;
    const save = vi.fn(() => new Promise<void>((_, no) => { reject = no; }));
    const view = render(editor("case-A", save));
    fireEvent.click(screen.getByRole("button", { name: "Sửa phạm vi" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Mô tả tùy chỉnh 1.1" }), { target: { value: "Mô tả được gửi" } });
    fireEvent.change(screen.getByLabelText("Giới hạn"), { target: { value: "Giới hạn gửi đi" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(save).toHaveBeenCalledOnce();
    expect(save).toHaveBeenCalledWith(expect.objectContaining({
      expected_version: 3, limitation_text: "Giới hạn gửi đi",
      blocks: [expect.objectContaining({ name: "Khối một", selections: [
        { taxonomy_node_id: "child", custom_description: "Mô tả được gửi" },
      ] })],
    }));
    expect(screen.getByRole("region", { name: "Phạm vi đánh giá đã gửi" })).toHaveTextContent("Mô tả được gửi");
    expect(screen.getByRole("button", { name: "Sửa phạm vi" })).toBeDisabled();
    view.rerender(editor("case-B", save));
    expect(screen.queryByRole("dialog", { name: "Sửa phạm vi đánh giá" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Phạm vi đánh giá đã gửi" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sửa phạm vi" })).toBeEnabled();
    view.rerender(editor("case-A", save, workspace({ row_version: 5, editable: false })));
    const evidence = screen.getByRole("region", { name: "Phạm vi đánh giá đã gửi" });
    expect(evidence).toHaveTextContent("Phiên bản đã gửi: 3");
    expect(evidence).toHaveTextContent("Mô tả được gửi");
    expect(evidence).toHaveTextContent("Giới hạn gửi đi");
    expect(evidence).toHaveTextContent("Taxonomy UUID: child");
    await act(async () => reject(new CaseFieldMutationRecoveryError("Không tải được readback canonical")));
    expect(screen.getByRole("status")).toHaveTextContent("Kết quả lưu chưa được xác minh");
    view.rerender(editor("case-B", save));
    view.rerender(editor("case-A", save, workspace({ row_version: 5, editable: false })));
    expect(screen.getByRole("region", { name: "Phạm vi đánh giá đã gửi" })).toHaveTextContent("Mô tả được gửi");
    expect(save).toHaveBeenCalledOnce();
  });

  it("retires submitted evidence after definite rejection and does not inherit lock in another Case", async () => {
    const save = vi.fn().mockRejectedValue(Object.assign(new Error("Stale scope version"), { status: 409 }));
    const view = render(editor("case-A", save));
    fireEvent.click(screen.getByRole("button", { name: "Sửa phạm vi" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Mô tả tùy chỉnh 1.1" }), { target: { value: "Old" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Stale scope version");
    view.rerender(editor("case-B", save));
    view.rerender(editor("case-A", save));
    expect(screen.queryByRole("region", { name: "Phạm vi đánh giá đã gửi" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sửa phạm vi" })).toBeEnabled();
    expect(save).toHaveBeenCalledOnce();
  });
});


describe("evaluation scope late-result editor ownership", () => {
  it("does not close another Case's newer editor when the previous Case's POST resolves late", async () => {
    let resolve!: () => void;
    const save = vi.fn(() => new Promise<void>(yes => { resolve = yes; }));
    const renderCase = (id: string) => <CaseDraftSession identity={id}>
      <EvaluationScopeWorkspace caseWorkspace={{ ...workspace(), case_summary: { id } } as CaseWorkspace} onSave={save} />
    </CaseDraftSession>;
    const view = render(renderCase("case-A"));
    fireEvent.click(screen.getByRole("button", { name: "Sửa phạm vi" }));
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(save).toHaveBeenCalledOnce();
    view.rerender(renderCase("case-B"));
    expect(screen.queryByRole("dialog", { name: "Sửa phạm vi đánh giá" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sửa phạm vi" }));
    expect(screen.getByRole("dialog", { name: "Sửa phạm vi đánh giá" })).toBeVisible();
    await act(async () => resolve());
    expect(screen.getByRole("dialog", { name: "Sửa phạm vi đánh giá" })).toBeVisible();
    expect(save).toHaveBeenCalledOnce();
  });
});
