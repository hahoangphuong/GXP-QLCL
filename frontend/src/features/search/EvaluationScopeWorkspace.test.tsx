import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CaseWorkspace } from "../../types";
import { EvaluationScopeWorkspace } from "./EvaluationScopeWorkspace";

function workspace(overrides: Partial<CaseWorkspace["evaluation_scope"]> = {}): CaseWorkspace {
  return {
    evaluation_scope: {
      id: "scope-1",
      row_version: 3,
      source_classification: "STRUCTURED_VALID",
      rendered_prose: null,
      limitation_text: null,
      editable: true,
      read_only_reason: null,
      taxonomy_version_id: "taxonomy-1",
      gxp_type: "GMP",
      blocks: [{
        id: "block-1",
        ordinal: 1,
        name: "Khối một",
        note: null,
        selections: [{ taxonomy_node_id: "child", node_key_snapshot: "1.1", taxonomy_description_snapshot: "Child", custom_description: "Chi tiết riêng" , source_order: 1 }],
        unkeyed_entries: [],
      }],
      taxonomy_nodes: [
        { id: "root", key: "1", parent_id: null, parent_key: null, description: "Root", hint: "Gợi ý", main_topic: null, short_render: null, no_expand: null, source_order: 1 },
        { id: "child", key: "1.1", parent_id: "root", parent_key: "1", description: "Child", hint: null, main_topic: null, short_render: null, no_expand: null, source_order: 2 },
      ],
      ...overrides,
    },
  } as CaseWorkspace;
}

describe("EvaluationScopeWorkspace", () => {
  it("renders inline custom text beneath its selected node, retains tri-state, and supports keyboard edit/save", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<EvaluationScopeWorkspace caseWorkspace={workspace()} onSave={onSave} />);

    expect(screen.getByText("Root")).toBeVisible();
    expect(screen.getByText("Child")).toBeVisible();
    const custom = screen.getByText("Chi tiết riêng");
    expect(custom).toHaveClass("tree-custom-description");
    expect(custom.closest(".evaluation-scope-node")).toHaveTextContent("1.1ChildChi tiết riêng");
    expect(document.querySelector(".evaluation-scope-detail")).toBeNull();
    expect(screen.getByRole("checkbox", { name: "Chọn 1" })).toHaveAttribute("aria-checked", "mixed");

    fireEvent.click(screen.getByRole("button", { name: "Thu gọn 1" }));
    expect(screen.queryByText("Child")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Mở rộng 1" }));
    expect(screen.getByText("Child")).toBeVisible();
    fireEvent.keyDown(screen.getByRole("tree").parentElement!, { key: "F2" });
    expect(screen.getByRole("button", { name: "Lưu" })).toBeVisible();

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(screen.getAllByRole("checkbox")[1]).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("button", { name: "Thêm phạm vi" }));
    expect(screen.getByRole("button", { name: "Bỏ phạm vi" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ expected_version: 3, blocks: expect.any(Array) })));
  });

  it("edits only the selected node custom description inline and cancel restores its canonical value", () => {
    render(<EvaluationScopeWorkspace caseWorkspace={workspace()} onSave={vi.fn()} />);

    fireEvent.doubleClick(screen.getByText("Child"));
    const input = screen.getByRole("textbox", { name: "Mô tả tùy chỉnh 1.1" });
    fireEvent.change(input, { target: { value: "Nội dung sửa" } });
    expect(screen.getByDisplayValue("Nội dung sửa")).toBeVisible();
    expect(screen.queryByRole("textbox", { name: "Mô tả tùy chỉnh 1" })).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("tree").parentElement!, { key: "Escape" });
    fireEvent.keyDown(screen.getByRole("tree").parentElement!, { key: "F2" });
    expect(screen.getByRole("textbox", { name: "Mô tả tùy chỉnh 1.1" })).toHaveValue("Chi tiết riêng");
  });

  it("keeps a blank custom description blank instead of repeating the taxonomy label", () => {
    render(<EvaluationScopeWorkspace caseWorkspace={workspace({ blocks: [{ id: "block-1", ordinal: 1, name: "Khối một", note: null, selections: [{ taxonomy_node_id: "child", node_key_snapshot: "1.1", taxonomy_description_snapshot: "Child", custom_description: "", source_order: 1 }], unkeyed_entries: [] }] })} onSave={vi.fn()} />);

    expect(screen.getByText("Child")).toBeVisible();
    expect(document.querySelector(".tree-custom-description")).toBeNull();
    fireEvent.doubleClick(screen.getByText("Child"));
    expect(screen.getByRole("textbox", { name: "Mô tả tùy chỉnh 1.1" })).toHaveValue("");
  });

  it("renders prose-only scope as historical read-only projection", () => {
    render(<EvaluationScopeWorkspace caseWorkspace={workspace({ source_classification: "PROSE_ONLY", rendered_prose: "Văn bản lưu trữ", editable: false, taxonomy_nodes: [] })} onSave={vi.fn()} />);

    expect(screen.getByText("Văn bản lưu trữ")).toBeVisible();
    expect(screen.queryByRole("tree")).not.toBeInTheDocument();
  });

  it("keeps the editor open and shows a conflict error when aggregate Save is stale", async () => {
    const conflict = Object.assign(new Error("Stale evaluation scope update."), { status: 409 });
    const onSave = vi.fn().mockRejectedValue(conflict);
    render(<EvaluationScopeWorkspace caseWorkspace={workspace()} onSave={onSave} />);

    fireEvent.doubleClick(screen.getByText("Child"));
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Stale evaluation scope update.");
    expect(screen.getByRole("button", { name: "Lưu" })).toBeVisible();
  });
});
