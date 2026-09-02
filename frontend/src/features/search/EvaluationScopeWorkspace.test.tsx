import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CaseWorkspace } from "../../types";
import { EvaluationScopeWorkspace } from "./EvaluationScopeWorkspace";

function workspace(overrides: Partial<CaseWorkspace["evaluation_scope"]> = {}): CaseWorkspace {
  return {
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
