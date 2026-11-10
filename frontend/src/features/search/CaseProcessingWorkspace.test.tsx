import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CaseWorkspace } from "../../types";
import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";
import { CaseCommandRegistryRoot, CaseDraftSession } from "./CaseDraftSession";
import { CaseProcessingWorkspace } from "./CaseProcessingWorkspace";

function workspace(): CaseWorkspace {
  return {
    processing: {
      row_version: 17,
      assessed_on: null,
      assessor_name: "Người cũ",
      assessment_result: "Kết quả cũ",
      notes: "Ghi chú cũ",
      events: [],
    },
  } as unknown as CaseWorkspace;
}

function makeEditor(identity: string, onSave: (payload: any) => Promise<void>) {
  return <CaseCommandRegistryRoot>
    <CaseDraftSession identity={identity}>
      <CaseProcessingWorkspace caseWorkspace={workspace()} onSave={onSave} view="assessment" />
    </CaseDraftSession>
  </CaseCommandRegistryRoot>;
}

describe("Case assessment uncertain canonical mutation", () => {
  it("keeps the exact submitted assessment and version, copyable but immutable, across Case A → B → A", async () => {
    const onSave = vi.fn().mockRejectedValue(new CaseFieldMutationRecoveryError("canonical GET unverified"));
    const view = render(makeEditor("case-A", onSave));
    fireEvent.click(screen.getByRole("button", { name: "Sửa Kết quả thẩm định" }));
    const input = screen.getByRole("textbox", { name: "Kết quả thẩm định" });
    fireEvent.change(input, { target: { value: "Đã đánh giá đủ bằng chứng" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Kết quả thẩm định" }));
    expect(await screen.findByText(/Chưa xác minh kết quả lưu/)).toBeInTheDocument();
    expect(onSave).toHaveBeenCalledExactlyOnceWith({
      expected_version: 17, assessment_result: "Đã đánh giá đủ bằng chứng",
    });
    expect(input).toHaveAttribute("readonly");
    expect(input).toHaveValue("Đã đánh giá đủ bằng chứng");
    expect(screen.getByRole("button", { name: "Hủy sửa Kết quả thẩm định" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Lưu Kết quả thẩm định" })).toBeDisabled();

    fireEvent.change(input, { target: { value: "Không được ghi đè" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input).toHaveValue("Đã đánh giá đủ bằng chứng");
    view.rerender(makeEditor("case-B", onSave));
    expect(screen.queryByDisplayValue("Đã đánh giá đủ bằng chứng")).not.toBeInTheDocument();
    view.rerender(makeEditor("case-A", onSave));
    const restored = await screen.findByRole("textbox", { name: "Kết quả thẩm định" });
    expect(restored).toHaveValue("Đã đánh giá đủ bằng chứng");
    expect(restored).toHaveAttribute("readonly");
    expect(screen.getByRole("button", { name: "Hủy sửa Kết quả thẩm định" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Lưu Kết quả thẩm định" }));
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("restores a late unknown outcome after the operator already switched A → B → A", async () => {
    let rejectWrite!: (error: Error) => void;
    const onSave = vi.fn(() => new Promise<void>((_, reject) => { rejectWrite = reject; }));
    const view = render(makeEditor("case-A", onSave));
    fireEvent.click(screen.getByRole("button", { name: "Sửa Ghi chú thẩm định" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Ghi chú thẩm định" }), { target: { value: "Bản gửi chưa xác minh" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Ghi chú thẩm định" }));
    view.rerender(makeEditor("case-B", onSave));
    view.rerender(makeEditor("case-A", onSave));
    expect(screen.getByRole("button", { name: "Sửa Ghi chú thẩm định" })).toHaveAttribute("aria-disabled", "true");
    await act(async () => { rejectWrite(new CaseFieldMutationRecoveryError("GET failed after POST")); });
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Ghi chú thẩm định" })).toHaveValue("Bản gửi chưa xác minh"));
    expect(screen.getByRole("textbox", { name: "Ghi chú thẩm định" })).toHaveAttribute("readonly");
    expect(onSave).toHaveBeenCalledExactlyOnceWith({ expected_version: 17, notes: "Bản gửi chưa xác minh" });
  });

  it.each([403, 409])("keeps editing possible after a definitive %s rejection", async status => {
    const onSave = vi.fn().mockRejectedValue(Object.assign(new Error("rejected"), { status }));
    render(makeEditor("case-A", onSave));
    fireEvent.click(screen.getByRole("button", { name: "Sửa Người thẩm định" }));
    const input = screen.getByRole("textbox", { name: "Người thẩm định" });
    fireEvent.change(input, { target: { value: "Người mới" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Người thẩm định" }));
    await screen.findByText(/rejected|Không thể lưu/i);
    expect(input).not.toHaveAttribute("readonly");
    expect(screen.getByRole("button", { name: "Hủy sửa Người thẩm định" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Hủy sửa Người thẩm định" }));
    expect(onSave).toHaveBeenCalledExactlyOnceWith({ expected_version: 17, assessor_name: "Người mới" });
  });
});
