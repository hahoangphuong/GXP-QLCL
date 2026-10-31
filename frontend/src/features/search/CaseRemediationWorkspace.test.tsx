import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { CaseWorkspace, CaseWorkspaceRemediationCycle, LifecycleActionReadiness } from "../../types";
import { CaseDraftSession } from "./CaseDraftSession";
import { CaseRemediationWorkspace } from "./CaseRemediationWorkspace";

function cycle(overrides: Partial<CaseWorkspaceRemediationCycle> = {}): CaseWorkspaceRemediationCycle {
  return {
    capa_cycle_id: "capa-1",
    row_version: 2,
    round_no: 1,
    requested_on: "2026-09-01",
    incoming_reference: "CV-01",
    submitted_on: null,
    assessed_on: null,
    assessor_name: null,
    result: null,
    status: "requested",
    notes: "Ghi chú từ máy chủ",
    ...overrides,
  };
}

function action(actionKey: string, available = true, expectedVersion: number | null = 2): LifecycleActionReadiness {
  return {
    action_key: actionKey,
    label: actionKey,
    available,
    reason_code: available ? null : "missing_permission",
    required_permissions: ["capa.edit"],
    expected_version: expectedVersion,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

function workspace(
  cycles: CaseWorkspaceRemediationCycle[] = [cycle()],
  actions: LifecycleActionReadiness[] = [],
): CaseWorkspace {
  return {
    case_summary: { id: "case-1", row_version: 8, legacy_inspection_id: 1, legacy_inspection_code: "KT-1", site_id: "site-1", legacy_site_id: 1, facility_name: "Cơ sở A", company_name: "Công ty A", gxp_type: "GMP", scope_code: null, production_line_id: null, production_line_code: null, production_line_identity_state: "canonical", applicable_standard: null, inspection_type: "Tái", state: "inspection_completed", opened_year: 2026 },
    remediation: { cycles, actions },
  } as unknown as CaseWorkspace;
}

function renderWorkspace(
  caseWorkspace = workspace(),
  selectedCycleId: string | null = "capa-1",
) {
  const handlers = {
    onSelectedCycleChange: vi.fn(),
    onCreateCycle: vi.fn().mockResolvedValue(undefined),
    onUpdateCycle: vi.fn().mockResolvedValue(undefined),
    onSubmitCycle: vi.fn().mockResolvedValue(undefined),
    onAssessCycle: vi.fn().mockResolvedValue(undefined),
  };
  return {
    ...render(<CaseRemediationWorkspace caseWorkspace={caseWorkspace} selectedCycleId={selectedCycleId} {...handlers} />),
    handlers,
  };
}

describe("CaseRemediationWorkspace backend-owned lifecycle actions", () => {
  it("retains an edited cycle's draft and original token through a newer-version refresh and conflict", async () => {
    const actions = [action("update_capa_cycle:capa-1")];
    const view = renderWorkspace(workspace([cycle()], actions));
    view.handlers.onUpdateCycle.mockRejectedValue(Object.assign(new Error("conflict"), { status: 409 }));
    fireEvent.keyDown(screen.getByRole("button", { name: "Sửa Số tham chiếu đến" }), { key: "F2" });
    fireEvent.change(screen.getByLabelText("Số tham chiếu đến"), { target: { value: "CV draft" } });
    const refreshed = workspace([cycle({ row_version: 3, incoming_reference: "CV remote" })], actions);
    view.rerender(<CaseRemediationWorkspace caseWorkspace={refreshed} selectedCycleId="capa-1" {...view.handlers} />);
    expect(screen.getByLabelText("Số tham chiếu đến")).toHaveValue("CV draft");
    fireEvent.click(screen.getByRole("button", { name: "Lưu Số CV đến" }));
    await screen.findByRole("alert");
    expect(view.handlers.onUpdateCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({ expected_version: 2, incoming_reference: "CV draft" }));
    expect(screen.getByLabelText("Số tham chiếu đến")).toHaveValue("CV draft");
    expect(view.handlers.onUpdateCycle).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Hủy sửa Số CV đến" }));
    expect(view.handlers.onUpdateCycle).toHaveBeenCalledOnce();
    fireEvent.keyDown(screen.getByRole("button", { name: "Sửa Số tham chiếu đến" }), { key: "F2" });
    expect(screen.getByLabelText("Số tham chiếu đến")).toHaveValue("CV remote");
    fireEvent.click(screen.getByRole("button", { name: "Lưu Số CV đến" }));
    await waitFor(() => expect(view.handlers.onUpdateCycle).toHaveBeenCalledTimes(2));
    expect(view.handlers.onUpdateCycle.mock.calls[1][1]).toEqual(expect.objectContaining({ expected_version: 3 }));
  });

  it.each(["submit", "assess"] as const)("keeps %s pending and its token/draft when refresh advances the same cycle", async command => {
    const request = deferred<void>();
    const actions = [action(`${command}_capa_cycle:capa-1`)];
    const view = renderWorkspace(workspace([cycle()], actions));
    const callback = command === "submit" ? view.handlers.onSubmitCycle : view.handlers.onAssessCycle;
    callback.mockImplementation(() => request.promise);
    const dateLabel = command === "submit" ? "Ngày ghi nhận tiếp nhận" : "Ngày đánh giá khắc phục";
    fireEvent.change(screen.getByLabelText(dateLabel), { target: { value: "2026-09-07" } });
    if (command === "assess") fireEvent.change(screen.getByLabelText("Kết quả đánh giá khắc phục"), { target: { value: "accepted" } });
    fireEvent.change(screen.getByLabelText("Ghi chú thao tác khắc phục"), { target: { value: "Pending draft" } });
    fireEvent.click(screen.getByRole("button", { name: command === "submit" ? "Ghi nhận tiếp nhận" : "Đánh giá" }));
    view.rerender(<CaseRemediationWorkspace caseWorkspace={workspace([cycle({ row_version: 3 })], actions)} selectedCycleId="capa-1" {...view.handlers} />);
    expect(screen.getByLabelText(dateLabel)).toBeDisabled();
    expect(screen.getByLabelText(dateLabel)).toHaveValue("2026-09-07");
    fireEvent.click(screen.getByRole("button", { name: command === "submit" ? "Đang ghi nhận..." : "Đang đánh giá..." }));
    expect(callback).toHaveBeenCalledOnce();
    await act(async () => request.reject(Object.assign(new Error("conflict"), { status: 409 })));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByLabelText("Ghi chú thao tác khắc phục")).toHaveValue("Pending draft");
    expect(callback.mock.calls[0][1]).toEqual(expect.objectContaining({ expected_version: 2 }));
    fireEvent.click(screen.getByRole("button", { name: command === "submit" ? "Ghi nhận tiếp nhận" : "Đánh giá" }));
    expect(callback.mock.calls[1][1]).toEqual(expect.objectContaining({ expected_version: 2 }));
    await act(async () => {});
  });

  it("retains a create draft's edit-start case token across refresh", async () => {
    const initial = workspace([], [action("create_capa_cycle", true, 8)]);
    const view = renderWorkspace(initial, null);
    view.handlers.onCreateCycle.mockRejectedValue(Object.assign(new Error("conflict"), { status: 409 }));
    fireEvent.click(screen.getByRole("button", { name: "Thêm vòng khắc phục" }));
    fireEvent.change(screen.getByLabelText("Ghi chú khắc phục"), { target: { value: "Create draft" } });
    view.rerender(<CaseRemediationWorkspace caseWorkspace={{ ...initial, case_summary: { ...initial.case_summary, row_version: 9 } }} selectedCycleId={null} {...view.handlers} />);
    fireEvent.click(screen.getByRole("button", { name: "Tạo vòng khắc phục" }));
    await screen.findByRole("alert");
    expect(view.handlers.onCreateCycle).toHaveBeenCalledWith(expect.objectContaining({ expected_case_version: 8, notes: "Create draft" }));
    expect(screen.getByLabelText("Ghi chú khắc phục")).toHaveValue("Create draft");
    expect(view.handlers.onCreateCycle).toHaveBeenCalledOnce();
  });

  it.each(["resolve", "reject"] as const)("isolates create drafts and late %s across Case A → B → A", async completion => {
    const request = deferred<void>();
    const initial = workspace([], [action("create_capa_cycle", true, 8)]);
    const view = renderWorkspace(initial, null);
    view.handlers.onCreateCycle.mockImplementation(() => request.promise);
    fireEvent.click(screen.getByRole("button", { name: "Thêm vòng khắc phục" }));
    fireEvent.change(screen.getByLabelText("Ghi chú khắc phục"), { target: { value: "Case A old draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo vòng khắc phục" }));
    const other = { ...initial, case_summary: { ...initial.case_summary, id: "case-2", row_version: 9 } };
    view.rerender(<CaseRemediationWorkspace caseWorkspace={other} selectedCycleId={null} {...view.handlers} />);
    expect(screen.queryByLabelText("Ghi chú khắc phục")).not.toBeInTheDocument();
    view.rerender(<CaseRemediationWorkspace caseWorkspace={initial} selectedCycleId={null} {...view.handlers} />);
    fireEvent.click(screen.getByRole("button", { name: "Thêm vòng khắc phục" }));
    fireEvent.change(screen.getByLabelText("Ghi chú khắc phục"), { target: { value: "New A draft" } });
    await act(async () => completion === "resolve" ? request.resolve() : request.reject(Object.assign(new Error("late conflict"), { status: 409 })));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Ghi chú khắc phục")).toHaveValue("New A draft");
    expect(view.handlers.onCreateCycle).toHaveBeenCalledOnce();
  });

  it("discards a new-cycle draft when explicitly returning to the already selected canonical cycle", async () => {
    const view = renderWorkspace(workspace([cycle()], [action("create_capa_cycle", true, 8), action("update_capa_cycle:capa-1")]));
    fireEvent.click(screen.getByRole("button", { name: "Thêm vòng khắc phục" }));
    fireEvent.change(screen.getByLabelText("Ghi chú khắc phục"), { target: { value: "Unsaved new-cycle notes" } });
    fireEvent.keyDown(view.container.querySelector("tbody tr")!, { key: "Enter" });
    fireEvent.keyDown(screen.getByRole("button", { name: "Sửa Ghi chú" }), { key: "F2" });
    expect(screen.getByLabelText("Ghi chú khắc phục")).toHaveValue("Ghi chú từ máy chủ");
    fireEvent.click(screen.getByRole("button", { name: "Lưu Ghi chú" }));
    await waitFor(() => expect(view.handlers.onUpdateCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({ expected_version: 2, notes: "Ghi chú từ máy chủ" })));
    expect(view.handlers.onCreateCycle).not.toHaveBeenCalled();
  });

  it.each(["submit", "assess"] as const)("does not adopt a refreshed token for an unsent %s draft", async command => {
    const actions = [action(`${command}_capa_cycle:capa-1`)];
    const view = renderWorkspace(workspace([cycle()], actions));
    fireEvent.change(screen.getByLabelText(command === "submit" ? "Ngày ghi nhận tiếp nhận" : "Ngày đánh giá khắc phục"), { target: { value: "2026-09-07" } });
    if (command === "assess") fireEvent.change(screen.getByLabelText("Kết quả đánh giá khắc phục"), { target: { value: "accepted" } });
    view.rerender(<CaseRemediationWorkspace caseWorkspace={workspace([cycle({ row_version: 3 })], actions)} selectedCycleId="capa-1" {...view.handlers} />);
    fireEvent.click(screen.getByRole("button", { name: command === "submit" ? "Ghi nhận tiếp nhận" : "Đánh giá" }));
    const callback = command === "submit" ? view.handlers.onSubmitCycle : view.handlers.onAssessCycle;
    await waitFor(() => expect(callback).toHaveBeenCalledWith("capa-1", expect.objectContaining({ expected_version: 2 })));
  });

  it("adopts successful update readback only after the current request completes", async () => {
    const request = deferred<void>();
    const actions = [action("update_capa_cycle:capa-1")];
    const view = renderWorkspace(workspace([cycle()], actions));
    view.handlers.onUpdateCycle.mockImplementation(() => request.promise);
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Ghi chú" }));
    fireEvent.change(screen.getByLabelText("Ghi chú khắc phục"), { target: { value: "Local notes" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Ghi chú" }));
    view.rerender(<CaseRemediationWorkspace caseWorkspace={workspace([cycle({ row_version: 3, notes: "Readback notes" })], actions)} selectedCycleId="capa-1" {...view.handlers} />);
    expect(screen.getByLabelText("Ghi chú khắc phục")).toBeDisabled();
    expect(screen.getByLabelText("Ghi chú khắc phục")).toHaveValue("Local notes");
    await act(async () => request.resolve());
    expect(screen.queryByLabelText("Ghi chú khắc phục")).not.toBeInTheDocument();
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Ghi chú" }));
    expect(screen.getByLabelText("Ghi chú khắc phục")).toHaveValue("Readback notes");
    fireEvent.click(screen.getByRole("button", { name: "Lưu Ghi chú" }));
    await waitFor(() => expect(view.handlers.onUpdateCycle).toHaveBeenCalledTimes(2));
    expect(view.handlers.onUpdateCycle.mock.calls[1][1]).toEqual(expect.objectContaining({ expected_version: 3 }));
  });

  it("does not duplicate create under StrictMode and ignores completion after unmount", async () => {
    const request = deferred<void>();
    const onCreateCycle = vi.fn(() => request.promise);
    const view = render(<StrictMode><CaseRemediationWorkspace caseWorkspace={workspace([], [action("create_capa_cycle", true, 8)])} selectedCycleId={null} onSelectedCycleChange={vi.fn()} onCreateCycle={onCreateCycle} onUpdateCycle={vi.fn()} onSubmitCycle={vi.fn()} onAssessCycle={vi.fn()} /></StrictMode>);
    fireEvent.click(screen.getByRole("button", { name: "Thêm vòng khắc phục" }));
    fireEvent.click(screen.getByRole("button", { name: "Tạo vòng khắc phục" }));
    fireEvent.click(screen.getByRole("button", { name: "Đang tạo..." }));
    expect(onCreateCycle).toHaveBeenCalledOnce();
    view.unmount();
    await act(async () => request.reject(Object.assign(new Error("late"), { status: 409 })));
    expect(onCreateCycle).toHaveBeenCalledOnce();
  });
  it("groups the selected round's reference, receipt, assessment and assessor before canonical extras", () => {
    const view = renderWorkspace(workspace([cycle({ submitted_on: "2026-09-05", assessed_on: "2026-09-06", assessor_name: "Người A", result: "accepted" })]));
    const primary = view.container.querySelector(".remediation-primary-fields");
    expect(primary).not.toBeNull();
    expect(Array.from(primary!.querySelectorAll(".detail-label"), node => node.textContent)).toEqual([
      "Số CV đến", "Ngày nhận", "Ngày thẩm định", "Người thẩm định",
    ]);
    expect(view.container.querySelector(".remediation-result-fields")).toHaveTextContent("accepted");
    expect(view.container.querySelector(".remediation-additional-fields")).toHaveTextContent("Ngày yêu cầu");
    expect(screen.queryByText("Ngày giám sát")).not.toBeInTheDocument();
  });
  it("exposes create, update, submit, and assess only from matching backend readiness", async () => {
    const initial = workspace(
      [cycle()],
      [
        action("create_capa_cycle", true, 8),
        action("update_capa_cycle:capa-1"),
        action("submit_capa_cycle:capa-1"),
        action("assess_capa_cycle:capa-1"),
      ],
    );
    const first = renderWorkspace(initial);

    fireEvent.click(screen.getByRole("button", { name: "Thêm vòng khắc phục" }));
    fireEvent.change(screen.getByLabelText("Ngày yêu cầu"), { target: { value: "2026-09-02" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo vòng khắc phục" }));
    await waitFor(() => expect(first.handlers.onCreateCycle).toHaveBeenCalledWith({ expected_case_version: 8, incoming_reference: null, requested_on: "2026-09-02", notes: null }));

    // Re-render the selected cycle after a successful create so its lifecycle controls are visible.
    // The server-owned actions, not local status text, decide availability.
    first.unmount();
    const ready = renderWorkspace(initial);
    fireEvent.doubleClick(ready.getByRole("button", { name: "Sửa Ghi chú" }));
    fireEvent.change(ready.getByLabelText("Ghi chú khắc phục"), { target: { value: "Đã cập nhật" } });
    fireEvent.click(ready.getByRole("button", { name: "Lưu Ghi chú" }));
    await waitFor(() => expect(ready.handlers.onUpdateCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({ expected_version: 2, notes: "Đã cập nhật" })));
    await waitFor(() => expect(ready.queryByRole("button", { name: "Lưu Ghi chú" })).not.toBeInTheDocument());

    fireEvent.change(ready.getByLabelText("Ngày ghi nhận tiếp nhận"), { target: { value: "2026-09-05" } });
    expect(ready.getByRole("button", { name: "Ghi nhận tiếp nhận" })).toBeEnabled();
    fireEvent.click(ready.getByRole("button", { name: "Ghi nhận tiếp nhận" }));
    await waitFor(() => expect(ready.handlers.onSubmitCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({ expected_version: 2, submitted_on: "2026-09-05" })));

    fireEvent.change(ready.getByLabelText("Ngày đánh giá khắc phục"), { target: { value: "2026-09-06" } });
    fireEvent.change(ready.getByLabelText("Kết quả đánh giá khắc phục"), { target: { value: "Đạt" } });
    fireEvent.click(ready.getByRole("button", { name: "Đánh giá" }));
    await waitFor(() => expect(ready.handlers.onAssessCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({ expected_version: 2, assessed_on: "2026-09-06", result: "Đạt" })));
  });

  it("fails closed when readiness is missing or unavailable and never invokes a lifecycle mutation", () => {
    const { handlers } = renderWorkspace(
      workspace([cycle()], [action("create_capa_cycle", false), action("submit_capa_cycle:capa-1", false), action("assess_capa_cycle:capa-1", false)]),
    );

    expect(screen.queryByRole("button", { name: "Thêm vòng khắc phục" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ghi nhận tiếp nhận" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Đánh giá" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Ngày ghi nhận tiếp nhận")).not.toBeInTheDocument();
    expect(handlers.onCreateCycle).not.toHaveBeenCalled();
    expect(handlers.onSubmitCycle).not.toHaveBeenCalled();
    expect(handlers.onAssessCycle).not.toHaveBeenCalled();
  });

  it("keeps submit and assess drafts across a same-version refetch before invoking the selected cycle actions", async () => {
    const actions = [action("submit_capa_cycle:capa-1"), action("assess_capa_cycle:capa-1")];
    const initial = workspace([cycle({ notes: "Ghi chú ban đầu" })], actions);
    const view = renderWorkspace(initial);

    fireEvent.change(screen.getByLabelText("Ngày ghi nhận tiếp nhận"), { target: { value: "2026-09-05" } });
    fireEvent.change(screen.getByLabelText("Ngày đánh giá khắc phục"), { target: { value: "2026-09-06" } });
    fireEvent.change(screen.getByLabelText("Kết quả đánh giá khắc phục"), { target: { value: "Đạt" } });
    fireEvent.change(screen.getByLabelText("Ghi chú thao tác khắc phục"), { target: { value: "Bản nháp của người dùng" } });

    view.rerender(
      <CaseRemediationWorkspace
        caseWorkspace={workspace([cycle({ notes: "Giá trị refetch cùng version" })], actions)}
        selectedCycleId="capa-1"
        {...view.handlers}
      />,
    );
    expect(screen.getByLabelText("Ngày ghi nhận tiếp nhận")).toHaveValue("2026-09-05");
    expect(screen.getByLabelText("Ngày đánh giá khắc phục")).toHaveValue("2026-09-06");
    expect(screen.getByLabelText("Kết quả đánh giá khắc phục")).toHaveValue("Đạt");
    expect(screen.getByLabelText("Ghi chú thao tác khắc phục")).toHaveValue("Bản nháp của người dùng");
    expect(screen.getByRole("button", { name: "Ghi nhận tiếp nhận" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Đánh giá" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Ghi nhận tiếp nhận" }));
    await waitFor(() => expect(view.handlers.onSubmitCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({ expected_version: 2, submitted_on: "2026-09-05", notes: "Bản nháp của người dùng" })));
    await waitFor(() => expect(screen.getByRole("button", { name: "Đánh giá" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Đánh giá" }));
    await waitFor(() => expect(view.handlers.onAssessCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({ expected_version: 2, assessed_on: "2026-09-06", result: "Đạt", notes: "Bản nháp của người dùng" })));
  });

  it("keeps command input when an unrelated field editor closes without a new cycle version", async () => {
    const actions = [action("update_capa_cycle:capa-1"), action("submit_capa_cycle:capa-1")];
    const view = renderWorkspace(workspace([cycle()], actions));

    fireEvent.change(screen.getByLabelText("Ngày ghi nhận tiếp nhận"), { target: { value: "2026-09-05" } });
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Số tham chiếu đến" }));
    fireEvent.change(screen.getByLabelText("Số tham chiếu đến"), { target: { value: "CV-02" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Số CV đến" }));

    await waitFor(() => expect(view.handlers.onUpdateCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({
      expected_version: 2,
      incoming_reference: "CV-02",
    })));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Lưu Số CV đến" })).not.toBeInTheDocument());
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByLabelText("Ngày ghi nhận tiếp nhận")).toHaveValue("2026-09-05");

    fireEvent.click(screen.getByRole("button", { name: "Ghi nhận tiếp nhận" }));
    await waitFor(() => expect(view.handlers.onSubmitCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({
      expected_version: 2,
      submitted_on: "2026-09-05",
    })));
  });

  it("rehydrates on an intentional selected-cycle change and never carries cycle A input to cycle B", () => {
    const first = cycle({ capa_cycle_id: "capa-1", submitted_on: null });
    const second = cycle({ capa_cycle_id: "capa-2", row_version: 4, round_no: 2, submitted_on: "2026-09-08", notes: "Cycle B" });
    const view = renderWorkspace(
      workspace([first, second], [action("submit_capa_cycle:capa-1"), action("submit_capa_cycle:capa-2", true, 4)]),
      "capa-1",
    );
    fireEvent.change(screen.getByLabelText("Ngày ghi nhận tiếp nhận"), { target: { value: "2026-09-05" } });

    view.rerender(
      <CaseRemediationWorkspace
        caseWorkspace={workspace([first, second], [action("submit_capa_cycle:capa-1"), action("submit_capa_cycle:capa-2", true, 4)])}
        selectedCycleId="capa-2"
        {...view.handlers}
      />,
    );
    expect(screen.getByRole("heading", { name: "Chi tiết vòng khắc phục 2" })).toBeInTheDocument();
    expect(screen.getByLabelText("Ngày ghi nhận tiếp nhận")).toHaveValue("2026-09-08");

    view.rerender(
      <CaseRemediationWorkspace
        caseWorkspace={workspace([first, second], [action("submit_capa_cycle:capa-1"), action("submit_capa_cycle:capa-2", true, 4)])}
        selectedCycleId="capa-1"
        {...view.handlers}
      />,
    );
    expect(screen.getByRole("heading", { name: "Chi tiết vòng khắc phục 1" })).toBeInTheDocument();
    expect(screen.getByLabelText("Ngày ghi nhận tiếp nhận")).toHaveValue("");
  });

  it("ignores a late cycle-A conflict after an external A → B → A selection sequence", async () => {
    const pending = deferred<void>();
    const first = cycle({ capa_cycle_id: "capa-1", submitted_on: null });
    const second = cycle({ capa_cycle_id: "capa-2", row_version: 4, round_no: 2, submitted_on: "2026-09-08", incoming_reference: "CV-B" });
    const actions = [
      action("update_capa_cycle:capa-1"),
      action("submit_capa_cycle:capa-1"),
      action("update_capa_cycle:capa-2", true, 4),
      action("submit_capa_cycle:capa-2", true, 4),
    ];
    const view = renderWorkspace(workspace([first, second], actions), "capa-1");
    view.handlers.onUpdateCycle.mockImplementation(() => pending.promise);

    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Số tham chiếu đến" }));
    fireEvent.change(screen.getByLabelText("Số tham chiếu đến"), { target: { value: "CV-A draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Số CV đến" }));
    expect(view.handlers.onUpdateCycle).toHaveBeenCalledOnce();

    view.rerender(<CaseRemediationWorkspace caseWorkspace={workspace([first, second], actions)} selectedCycleId="capa-2" {...view.handlers} />);
    expect(screen.getByRole("heading", { name: "Chi tiết vòng khắc phục 2" })).toBeInTheDocument();
    view.rerender(<CaseRemediationWorkspace caseWorkspace={workspace([first, second], actions)} selectedCycleId="capa-1" {...view.handlers} />);
    expect(screen.getByRole("heading", { name: "Chi tiết vòng khắc phục 1" })).toBeInTheDocument();

    await act(async () => pending.reject(Object.assign(new Error("late A conflict"), { status: 409 })));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Ngày ghi nhận tiếp nhận")).toHaveValue("");
    expect(view.handlers.onUpdateCycle).toHaveBeenCalledOnce();
  });

  it("does not publish a late submit conflict or old draft after A → B → A", async () => {
    const pending = deferred<void>();
    const first = cycle({ capa_cycle_id: "capa-1", submitted_on: null });
    const second = cycle({ capa_cycle_id: "capa-2", row_version: 4, round_no: 2, submitted_on: null });
    const actions = [action("submit_capa_cycle:capa-1"), action("submit_capa_cycle:capa-2", true, 4)];
    const view = renderWorkspace(workspace([first, second], actions), "capa-1");
    view.handlers.onSubmitCycle.mockImplementation(() => pending.promise);

    fireEvent.change(screen.getByLabelText("Ngày ghi nhận tiếp nhận"), { target: { value: "2026-09-05" } });
    fireEvent.click(screen.getByRole("button", { name: "Ghi nhận tiếp nhận" }));
    expect(view.handlers.onSubmitCycle).toHaveBeenCalledOnce();

    view.rerender(<CaseRemediationWorkspace caseWorkspace={workspace([first, second], actions)} selectedCycleId="capa-2" {...view.handlers} />);
    view.rerender(<CaseRemediationWorkspace caseWorkspace={workspace([first, second], actions)} selectedCycleId="capa-1" {...view.handlers} />);
    await act(async () => pending.reject(Object.assign(new Error("late submit conflict"), { status: 409 })));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Ngày ghi nhận tiếp nhận")).toHaveValue("");
    expect(view.handlers.onSubmitCycle).toHaveBeenCalledOnce();
  });

  it("rehydrates command input after a successful mutation returns a newer server version", async () => {
    const view = renderWorkspace(workspace([cycle()], [action("submit_capa_cycle:capa-1")]));
    fireEvent.change(screen.getByLabelText("Ngày ghi nhận tiếp nhận"), { target: { value: "2026-09-05" } });
    fireEvent.click(screen.getByRole("button", { name: "Ghi nhận tiếp nhận" }));
    await waitFor(() => expect(view.handlers.onSubmitCycle).toHaveBeenCalledOnce());

    view.rerender(
      <CaseRemediationWorkspace
        caseWorkspace={workspace([cycle({ row_version: 3, submitted_on: "2026-09-05", notes: "Đã được server ghi nhận" })], [action("assess_capa_cycle:capa-1", true, 3)])}
        selectedCycleId="capa-1"
        {...view.handlers}
      />,
    );
    expect(screen.getByLabelText("Ngày ghi nhận tiếp nhận")).toHaveValue("2026-09-05");
    expect(screen.getByLabelText("Ghi chú thao tác khắc phục")).toHaveValue("Đã được server ghi nhận");
    expect(screen.queryByRole("button", { name: "Ghi nhận tiếp nhận" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đánh giá" })).toBeInTheDocument();
  });

  it.each([
    { label: "HTTP403", status: 403 },
    { label: "HTTP404", status: 404 },
    { label: "HTTP409", status: 409 },
    { label: "HTTP422", status: 422 },
    { label: "network failure", status: undefined },
  ])("preserves each command draft after $label without retry", async ({ status }) => {
    const actions = [action("create_capa_cycle", true, 8), action("update_capa_cycle:capa-1"), action("submit_capa_cycle:capa-1"), action("assess_capa_cycle:capa-1")];
    for (const command of ["create", "update", "submit", "assess"] as const) {
      const view = renderWorkspace(workspace([cycle()], actions));
      const callback = { create: view.handlers.onCreateCycle, update: view.handlers.onUpdateCycle, submit: view.handlers.onSubmitCycle, assess: view.handlers.onAssessCycle }[command];
      callback.mockRejectedValue(Object.assign(new Error("fixture error"), { status }));
      if (command === "create") {
        fireEvent.click(screen.getByRole("button", { name: "Thêm vòng khắc phục" }));
        fireEvent.change(screen.getByLabelText("Ghi chú khắc phục"), { target: { value: "Draft create" } });
        fireEvent.click(screen.getByRole("button", { name: "Tạo vòng khắc phục" }));
      } else if (command === "update") {
        fireEvent.keyDown(screen.getByRole("button", { name: "Sửa Ghi chú" }), { key: "F2" });
        fireEvent.change(screen.getByLabelText("Ghi chú khắc phục"), { target: { value: "Draft update" } });
        fireEvent.click(screen.getByRole("button", { name: "Lưu Ghi chú" }));
      } else {
        fireEvent.change(screen.getByLabelText("Ghi chú thao tác khắc phục"), { target: { value: `Draft ${command}` } });
        fireEvent.change(screen.getByLabelText(command === "submit" ? "Ngày ghi nhận tiếp nhận" : "Ngày đánh giá khắc phục"), { target: { value: "2026-09-07" } });
        if (command === "assess") fireEvent.change(screen.getByLabelText("Kết quả đánh giá khắc phục"), { target: { value: "accepted" } });
        fireEvent.click(screen.getByRole("button", { name: command === "submit" ? "Ghi nhận tiếp nhận" : "Đánh giá" }));
      }
      await screen.findByRole("alert");
      expect(callback).toHaveBeenCalledOnce();
      expect(screen.getByLabelText(command === "create" || command === "update" ? "Ghi chú khắc phục" : "Ghi chú thao tác khắc phục")).toHaveValue(`Draft ${command}`);
      expect(callback.mock.calls[0][command === "create" ? 0 : 1]).toEqual(expect.objectContaining(command === "create" ? { expected_case_version: 8 } : { expected_version: 2 }));
      view.unmount();
    }
  });

  it("blocks duplicate submit and cycle activation while pending, then retains the rejected draft", async () => {
    let reject!: (error: unknown) => void;
    const view = renderWorkspace(workspace([cycle(), cycle({ capa_cycle_id: "capa-2", round_no: 2 })], [action("submit_capa_cycle:capa-1")]));
    view.handlers.onSubmitCycle.mockImplementation(() => new Promise((_, rejectPromise) => { reject = rejectPromise; }));
    fireEvent.change(screen.getByLabelText("Ngày ghi nhận tiếp nhận"), { target: { value: "2026-09-07" } });
    fireEvent.click(screen.getByRole("button", { name: "Ghi nhận tiếp nhận" }));
    expect(screen.getByRole("button", { name: "Đang ghi nhận..." })).toBeDisabled();
    expect(screen.getByLabelText("Ngày ghi nhận tiếp nhận")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Đang ghi nhận..." }));
    fireEvent.keyDown(view.container.querySelectorAll("tbody tr")[1], { key: "Enter" });
    expect(view.handlers.onSelectedCycleChange).not.toHaveBeenCalled();
    expect(view.handlers.onSubmitCycle).toHaveBeenCalledOnce();
    reject(Object.assign(new Error("conflict"), { status: 409 }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Ngày ghi nhận tiếp nhận")).toHaveValue("2026-09-07");
    expect(screen.getByRole("button", { name: "Ghi nhận tiếp nhận" })).toBeEnabled();
    expect(view.handlers.onSubmitCycle).toHaveBeenCalledOnce();
  });

  it("retains every round beyond legacy's two columns and activates only the canonical keyboard target", () => {
    const cycles = [cycle(), cycle({ capa_cycle_id: "capa-2", round_no: 2 }), cycle({ capa_cycle_id: "capa-3", round_no: 3, notes: "Third cycle" })];
    const view = renderWorkspace(workspace(cycles));
    const rows = view.container.querySelectorAll("tbody tr");
    expect(rows).toHaveLength(3);
    fireEvent.focus(rows[2]);
    expect(view.handlers.onSelectedCycleChange).not.toHaveBeenCalled();
    fireEvent.keyDown(rows[2], { key: " " });
    expect(view.handlers.onSelectedCycleChange).toHaveBeenCalledWith("capa-3");
    view.rerender(<CaseRemediationWorkspace caseWorkspace={workspace(cycles)} selectedCycleId="capa-3" {...view.handlers} />);
    expect(screen.getByRole("heading", { name: "Chi tiết vòng khắc phục 3" })).toBeInTheDocument();
    expect(screen.getByText("Third cycle")).toBeInTheDocument();
    expect(view.handlers.onUpdateCycle).not.toHaveBeenCalled();
  });
});


it("settles the original CAPA operation through tab unmount without losing its draft/token or enabling duplicate writes", async () => {
  let reject!: (error: Error) => void;
  const onUpdateCycle = vi.fn(() => new Promise<void>((_, rejectPromise) => { reject = rejectPromise; }));
  const props = { onUpdateCycle, onSelectedCycleChange: vi.fn(), onCreateCycle: vi.fn(), onSubmitCycle: vi.fn(), onAssessCycle: vi.fn() };
  const editor = (show: boolean) => <CaseDraftSession identity="case-A">{show ? <CaseRemediationWorkspace caseWorkspace={workspace([cycle()], [action("update_capa_cycle:capa-1")])} selectedCycleId="capa-1" {...props} /> : null}</CaseDraftSession>;
  const view = render(editor(true));
  fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Số tham chiếu đến" }));
  fireEvent.change(screen.getByLabelText("Số tham chiếu đến"), { target: { value: "Pending CAPA" } });
  fireEvent.click(screen.getByRole("button", { name: "Lưu Số CV đến" }));
  view.rerender(editor(false));view.rerender(editor(true));
  expect(screen.getByLabelText("Số tham chiếu đến")).toHaveValue("Pending CAPA");
  expect(screen.getByRole("button", { name: "Lưu Số CV đến" })).toBeDisabled();
  await act(async () => reject(Object.assign(new Error("Conflict"), { status: 409 })));
  expect(screen.getByLabelText("Số tham chiếu đến")).toBeEnabled();
  expect(screen.getByLabelText("Số tham chiếu đến")).toHaveValue("Pending CAPA");
  expect(screen.getByRole("alert")).toBeInTheDocument();
  expect(onUpdateCycle).toHaveBeenCalledOnce();
  expect(onUpdateCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({ expected_version: 2 }));
});
