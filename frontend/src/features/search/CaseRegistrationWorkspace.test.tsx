import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CaseWorkspace } from "../../types";
import { CaseApplicationWorkspace } from "./CaseApplicationWorkspace";
import { CaseProcessingWorkspace } from "./CaseProcessingWorkspace";

const workspace = {
  case_summary: { id: "case-uuid", site_id: "site-uuid", production_line_id: "line-uuid", gxp_type: "GMP", legacy_site_id: null, legacy_inspection_code: null, state: "application_submitted" },
  application: { row_version: 4, submitted_on: "2026-01-15", dossier_code: "HS-001" },
  processing: { row_version: 7, assessed_on: "2026-01-20", assessor_name: "Assessor", assessment_result: "Đạt", notes: null, events: [] },
} as unknown as CaseWorkspace;

afterEach(cleanup);

function registration(value = workspace, applicationSave = vi.fn(), assessmentSave = vi.fn()) {
  return <CaseApplicationWorkspace caseWorkspace={value} onSave={applicationSave} onResolveInspectionFolder={vi.fn()}
    assessment={<CaseProcessingWorkspace caseWorkspace={value} onSave={assessmentSave} view="assessment" />} />;
}

describe("registration presentation preserves existing editor owners", () => {
  it("Enter on the application Cancel button never submits a mutation", async () => {
    const save = vi.fn();
    render(registration(workspace, save));
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Mã hồ sơ" }));
    fireEvent.change(screen.getByLabelText("Mã hồ sơ"), { target: { value: "not submitted" } });
    const cancel = screen.getByRole("button", { name: "Hủy sửa Mã hồ sơ" });
    await act(async () => fireEvent.keyDown(cancel, { key: "Enter" }));
    expect(save).not.toHaveBeenCalled();
    fireEvent.click(cancel);
    expect(screen.getByRole("button", { name: "Sửa Mã hồ sơ" })).toHaveTextContent("HS-001");
    expect(save).not.toHaveBeenCalled();
  });

  it("Escape during pending assessment cannot discard the draft before a 409", async () => {
    let rejectSave!: (error: Error) => void;
    const save = vi.fn(() => new Promise<void>((_resolve, reject) => { rejectSave = reject; }));
    render(registration(workspace, vi.fn(), save));
    fireEvent.keyDown(screen.getByRole("button", { name: "Sửa Người thẩm định" }), { key: "F2" });
    fireEvent.change(screen.getByLabelText("Người thẩm định"), { target: { value: "retained draft" } });
    fireEvent.keyDown(screen.getByLabelText("Người thẩm định"), { key: "Enter" });
    fireEvent.keyDown(screen.getByLabelText("Người thẩm định"), { key: "Escape" });
    await act(async () => rejectSave(Object.assign(new Error("conflict"), { status: 409 })));
    expect(screen.getByLabelText("Người thẩm định")).toHaveValue("retained draft");
    expect(screen.getByRole("alert")).toHaveTextContent("đã bị thay đổi");
    expect(save).toHaveBeenCalledExactlyOnceWith({ expected_version: 7, assessed_on: "2026-01-20T00:00:00Z", assessor_name: "retained draft", assessment_result: "Đạt", notes: null });
    fireEvent.keyDown(screen.getByLabelText("Người thẩm định"), { key: "Escape" });
    expect(screen.getByRole("button", { name: "Sửa Người thẩm định" })).toHaveTextContent("Assessor");
    expect(save).toHaveBeenCalledOnce();
  });

  it("keeps the primary field order and moves only additional metadata into a disclosure", () => {
    const { container } = render(registration());
    expect(screen.getByRole("heading", { name: "Thông tin hồ sơ" })).toHaveClass("sr-only");
    expect(Array.from(container.querySelectorAll(".case-application-primary .detail-label, .case-assessment-metadata .detail-label")).map(node => node.textContent))
      .toEqual(["Ngày nộp", "Mã hồ sơ", "Ngày thẩm định", "Người thẩm định"]);
    expect(container.querySelector(".case-assessment-result")).toContainElement(screen.getByRole("button", { name: "Sửa Kết quả thẩm định" }));
    const disclosure = screen.getByText("Thông tin bổ sung").closest("details");
    expect(disclosure).not.toHaveAttribute("open");
    expect(disclosure).toContainElement(screen.getByText("Trạng thái hồ sơ"));
    expect(screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" })).toBeDisabled();
  });

  it.each([403, 409, 422])("retains application draft on %s without retrying and allows keyboard cancel", async status => {
    const save = vi.fn().mockRejectedValue(Object.assign(new Error("fixture rejection"), { status }));
    render(registration(workspace, save));
    fireEvent.keyDown(screen.getByRole("button", { name: "Sửa Mã hồ sơ" }), { key: "F2" });
    fireEvent.change(screen.getByLabelText("Mã hồ sơ"), { target: { value: "draft" } });
    await act(async () => fireEvent.keyDown(screen.getByLabelText("Mã hồ sơ"), { key: "Enter" }));
    expect(save).toHaveBeenCalledExactlyOnceWith({ expected_version: 4, dossier_code: "draft" });
    expect(screen.getByRole("alert")).toHaveTextContent(status === 403 ? "không có quyền" : status === 409 ? "đã bị thay đổi" : "chưa hợp lệ");
    expect(screen.getByLabelText("Mã hồ sơ")).toHaveValue("draft");
    fireEvent.keyDown(screen.getByLabelText("Mã hồ sơ"), { key: "Escape" });
    expect(screen.queryByLabelText("Mã hồ sơ")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sửa Mã hồ sơ" })).toHaveTextContent("HS-001");
    expect(save).toHaveBeenCalledOnce();
  });

  it("keeps assessment draft and original token through refresh and pending conflict", async () => {
    let rejectSave!: (error: Error) => void;
    const save = vi.fn(() => new Promise<void>((_resolve, reject) => { rejectSave = reject; }));
    const { rerender } = render(registration(workspace, vi.fn(), save));
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Kết quả thẩm định" }));
    fireEvent.change(screen.getByLabelText("Kết quả thẩm định"), { target: { value: "unsaved result" } });
    const refreshed = { ...workspace, processing: { ...workspace.processing, row_version: 8, assessment_result: "remote result" } };
    rerender(registration(refreshed, vi.fn(), save));
    fireEvent.click(screen.getByRole("button", { name: "Lưu Kết quả thẩm định" }));
    expect(screen.getByLabelText("Kết quả thẩm định")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Hủy sửa Kết quả thẩm định" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Lưu Kết quả thẩm định" }));
    expect(save).toHaveBeenCalledExactlyOnceWith({ expected_version: 7, assessed_on: "2026-01-20T00:00:00Z", assessor_name: "Assessor", assessment_result: "unsaved result", notes: null });
    await act(async () => rejectSave(Object.assign(new Error("stale"), { status: 409 })));
    expect(screen.getByLabelText("Kết quả thẩm định")).toHaveValue("unsaved result");
    expect(screen.getByRole("alert")).toHaveTextContent("đã bị thay đổi");
    fireEvent.click(screen.getByRole("button", { name: "Hủy sửa Kết quả thẩm định" }));
    expect(screen.getByRole("button", { name: "Sửa Kết quả thẩm định" })).toHaveTextContent("remote result");
    expect(save).toHaveBeenCalledOnce();
  });
});
