import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EditableDetailValue } from "./EditableDetailValue";

afterEach(cleanup);

function editor(overrides: Partial<Parameters<typeof EditableDetailValue>[0]> = {}) {
  const callbacks = { onCancel: vi.fn(), onEdit: vi.fn(), onSave: vi.fn() };
  render(<EditableDetailValue editButtonLabel="Sửa dữ liệu" isEditing label="Dữ liệu" value="persisted" {...callbacks} {...overrides}>
    {overrides.children ?? <input aria-label="Draft" defaultValue="unsaved" />}
  </EditableDetailValue>);
  return callbacks;
}

describe("inline editor keyboard action ownership", () => {
  it("does not switch to another field while its aggregate mutation is pending", () => {
    const handlers = editor({ isEditing: false, pending: true });
    const trigger = screen.getByRole("button", { name: "Sửa dữ liệu" });
    fireEvent.keyDown(trigger, { key: "F2" });
    fireEvent.keyDown(trigger, { key: "Enter" });
    fireEvent.doubleClick(trigger);
    expect(handlers.onEdit).not.toHaveBeenCalled();
    expect(trigger).toHaveAttribute("aria-disabled", "true");
  });

  it("retains double-click, F2 and Enter activation when editable", () => {
    const handlers = editor({ isEditing: false });
    const trigger = screen.getByRole("button", { name: "Sửa dữ liệu" });
    fireEvent.keyDown(trigger, { key: "Enter", isComposing: true });
    expect(handlers.onEdit).not.toHaveBeenCalled();
    fireEvent.keyDown(trigger, { key: "F2" });
    fireEvent.keyDown(trigger, { key: "Enter" });
    fireEvent.doubleClick(trigger);
    expect(handlers.onEdit).toHaveBeenCalledTimes(3);
  });

  it("leaves Enter on Cancel to its native button without invoking Save", () => {
    const handlers = editor();
    const cancel = screen.getByRole("button", { name: "Hủy sửa Dữ liệu" });
    expect(fireEvent.keyDown(cancel, { key: "Enter" })).toBe(true);
    expect(handlers.onSave).not.toHaveBeenCalled();
    fireEvent.click(cancel);
    expect(handlers.onCancel).toHaveBeenCalledOnce();
  });

  it("leaves Enter on Save to its native click, invoking the handler once", () => {
    const handlers = editor();
    const save = screen.getByRole("button", { name: "Lưu Dữ liệu" });
    expect(fireEvent.keyDown(save, { key: "Enter" })).toBe(true);
    expect(handlers.onSave).not.toHaveBeenCalled();
    fireEvent.click(save);
    expect(handlers.onSave).toHaveBeenCalledOnce();
  });

  it("does not cancel a pending mutation through Escape", () => {
    const handlers = editor({ pending: true });
    fireEvent.keyDown(screen.getByLabelText("Draft"), { key: "Escape" });
    expect(handlers.onCancel).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Draft")).toHaveValue("unsaved");
    expect(screen.getByRole("button", { name: "Hủy sửa Dữ liệu" })).toBeDisabled();
  });

  it("does not submit while an IME is composing", () => {
    const handlers = editor();
    fireEvent.keyDown(screen.getByLabelText("Draft"), { key: "Enter", isComposing: true });
    expect(handlers.onSave).not.toHaveBeenCalled();
  });

  it("does not treat Enter in a select as a save command", () => {
    const handlers = editor({ children: <select aria-label="Choice"><option>Đạt</option></select> });
    expect(fireEvent.keyDown(screen.getByLabelText("Choice"), { key: "Enter" })).toBe(true);
    expect(handlers.onSave).not.toHaveBeenCalled();
  });

  it("retains ordinary text Enter, Escape, multiline and disabled-save contracts", () => {
    const handlers = editor();
    fireEvent.keyDown(screen.getByLabelText("Draft"), { key: "Enter" });
    expect(handlers.onSave).toHaveBeenCalledOnce();
    fireEvent.keyDown(screen.getByLabelText("Draft"), { key: "Escape" });
    expect(handlers.onCancel).toHaveBeenCalledOnce();
  });

  it.each([{ multiline: true }, { saveDisabled: true }, { pending: true }])("does not save with %j", flags => {
    const handlers = editor(flags);
    fireEvent.keyDown(screen.getByLabelText("Draft"), { key: "Enter" });
    expect(handlers.onSave).not.toHaveBeenCalled();
  });
});
