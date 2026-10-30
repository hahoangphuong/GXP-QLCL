import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import type { CaseWorkspace } from "../../types";
import { CaseApprovalWorkspace } from "./CaseApprovalWorkspace";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const action = (action_key: string, expected_version: number | null = 4) => ({ action_key, expected_version, available: true, reason_code: null, required_permissions: [] });
function workspace(version = 4, ids = ["pct-A"], caseId = "case-A"): CaseWorkspace {
  return { case_summary: { id: caseId }, inspection: {
    approval_actions: [action("create_approval_pct"), action("create_approval_ct"), ...ids.map(id => action(`complete_approval:${id}`, version))],
    approval_submissions: ids.map((id, i) => ({ approval_submission_id: id, case_id: caseId, row_version: version, stage: "PCT", round_no: i + 1, reference: id, submitted_on: null, submitted_time: null, completed_on: null, completed_time: null, pct_submission_id: null })),
  } } as unknown as CaseWorkspace;
}
function setup(value = workspace()) {
  const handlers = { onCreate: vi.fn().mockResolvedValue({}), onComplete: vi.fn().mockResolvedValue({}) };
  const view = render(<StrictMode><CaseApprovalWorkspace caseWorkspace={value} {...handlers} /></StrictMode>);
  return { ...view, handlers, refresh: (next: CaseWorkspace) => view.rerender(<StrictMode><CaseApprovalWorkspace caseWorkspace={next} {...handlers} /></StrictMode>) };
}
describe("Approval canonical editor ownership", () => {
  it.each([403, 404, 409, 422, undefined])("retains create/completion drafts for status %s without retry", async status => {
    const view = setup();
    view.handlers.onCreate.mockRejectedValue(Object.assign(new Error("Rejected create"), { status }));
    fireEvent.change(screen.getByLabelText("Tham chiếu trình"), { target: { value: "Create draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo trình PCT" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Tham chiếu trình")).toHaveValue("Create draft");
    expect(view.handlers.onCreate).toHaveBeenCalledOnce();
    view.unmount();
    const completion = setup();
    completion.handlers.onComplete.mockRejectedValue(Object.assign(new Error("Rejected completion"), { status }));
    fireEvent.change(screen.getByLabelText("Ngày hoàn tất trình"), { target: { value: "2026-10-03" } });
    completion.refresh(workspace(5));
    fireEvent.click(screen.getByRole("button", { name: "Hoàn tất PCT" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Ngày hoàn tất trình")).toHaveValue("2026-10-03");
    expect(completion.handlers.onComplete).toHaveBeenCalledWith("pct-A", expect.objectContaining({ expected_version: 4 }));
    expect(completion.handlers.onComplete).toHaveBeenCalledOnce();
  });

  it("keeps completion pending through refresh; explicit local Cancel adopts the new token", async () => {
    const request = deferred<never>();
    const view = setup();
    view.handlers.onComplete.mockImplementationOnce(() => request.promise);
    fireEvent.change(screen.getByLabelText("Ngày hoàn tất trình"), { target: { value: "2026-10-03" } });
    fireEvent.click(screen.getByRole("button", { name: "Hoàn tất PCT" }));
    view.refresh(workspace(5));
    expect(screen.getByLabelText("Ngày hoàn tất trình")).toBeDisabled();
    expect(screen.getByLabelText("Tham chiếu trình")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Hủy nhập hoàn tất PCT lần 1" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Hoàn tất PCT" }));
    await act(async () => request.reject(Object.assign(new Error("conflict"), { status: 409 })));
    expect(view.handlers.onComplete).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Hủy nhập hoàn tất PCT lần 1" }));
    expect(screen.getByLabelText("Ngày hoàn tất trình")).toHaveValue("");
    expect(view.handlers.onComplete).toHaveBeenCalledOnce();
    fireEvent.change(screen.getByLabelText("Ngày hoàn tất trình"), { target: { value: "2026-10-04" } });
    fireEvent.click(screen.getByRole("button", { name: "Hoàn tất PCT" }));
    await waitFor(() => expect(view.handlers.onComplete).toHaveBeenCalledTimes(2));
    expect(view.handlers.onComplete.mock.calls[1][1]).toEqual(expect.objectContaining({ expected_version: 5 }));
  });
  it("does not complete round B using date input belonging to round A", async () => {
    const view = setup(workspace(4, ["pct-A", "pct-B"]));
    fireEvent.change(screen.getAllByLabelText("Ngày hoàn tất trình")[0], { target: { value: "2026-10-03" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Hoàn tất PCT" })[1]);
    expect(view.handlers.onComplete).not.toHaveBeenCalled();
    const second = within(screen.getByRole("group", { name: "Hoàn tất PCT lần 2" }));
    fireEvent.change(second.getByLabelText("Ngày hoàn tất trình"), { target: { value: "2026-10-04" } });
    fireEvent.click(second.getByRole("button", { name: "Hoàn tất PCT" }));
    await waitFor(() => expect(view.handlers.onComplete).toHaveBeenCalledWith("pct-B", expect.objectContaining({ completed_on: "2026-10-04", expected_version: 4 })));
  });

  it("retains the completion readiness token and draft through refresh and conflict", async () => {
    const view = setup();
    view.handlers.onComplete.mockRejectedValue(Object.assign(new Error("conflict"), { status: 409 }));
    fireEvent.change(screen.getByLabelText("Ngày hoàn tất trình"), { target: { value: "2026-10-03" } });
    view.refresh(workspace(5));
    fireEvent.click(screen.getByRole("button", { name: "Hoàn tất PCT" }));
    await screen.findByRole("alert");
    expect(view.handlers.onComplete).toHaveBeenCalledWith("pct-A", expect.objectContaining({ expected_version: 4 }));
    expect(screen.getByLabelText("Ngày hoàn tất trình")).toHaveValue("2026-10-03");
    expect(view.handlers.onComplete).toHaveBeenCalledOnce();
  });

  it("disables a removed explicit CT parent instead of submitting its stale UUID", async () => {
    const initial = workspace();
    initial.inspection.approval_submissions[0].completed_on = "2026-10-02";
    const view = setup(initial);
    fireEvent.change(screen.getByLabelText("PCT hoàn tất cho CT"), { target: { value: "pct-A" } });
    view.refresh(workspace(5, []));
    expect(screen.getByRole("button", { name: "Tạo trình CT" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Tạo trình CT" }));
    expect(view.handlers.onCreate).not.toHaveBeenCalled();
    await act(async () => {});
  });

  it.each(["resolve", "reject"] as const)("discards Case A create input and ignores its late %s after A → B → A", async completion => {
    const request = deferred<never>();
    const view = setup();
    view.handlers.onCreate.mockImplementation(() => request.promise);
    fireEvent.change(screen.getByLabelText("Tham chiếu trình"), { target: { value: "Old A draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo trình PCT" }));
    view.refresh(workspace(4, ["pct-B"], "case-B"));
    expect(screen.getByLabelText("Tham chiếu trình")).toHaveValue("");
    view.refresh(workspace());
    fireEvent.change(screen.getByLabelText("Tham chiếu trình"), { target: { value: "New A draft" } });
    await act(async () => completion === "resolve" ? request.resolve({} as never) : request.reject(Object.assign(new Error("late"), { status: 409 })));
    expect(screen.getByLabelText("Tham chiếu trình")).toHaveValue("New A draft");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(view.handlers.onCreate).toHaveBeenCalledOnce();
  });
});
