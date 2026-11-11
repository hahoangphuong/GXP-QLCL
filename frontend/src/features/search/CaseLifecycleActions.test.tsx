import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";
import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CaseWorkspace } from "../../types";
import { CaseDraftSession } from "./CaseDraftSession";
import { CaseLifecycleActions } from "./CaseLifecycleActions";

function workspace(actions: CaseWorkspace["transition_actions"]): CaseWorkspace {
  return { case_summary: { id: "case-A" }, transition_actions: actions } as CaseWorkspace;
}

describe("CaseLifecycleActions", () => {
  const action = (version = 18) => ({ action_key: "opaque-transition", label: "Chuyển theo policy", target_state: "planned", available: true, expected_version: version, reason_code: null, required_permissions: ["case.edit"] });

  it("explains the backend CAPA blocker without enabling or submitting the transition", () => {
    const onTransition = vi.fn();
    render(<CaseLifecycleActions caseWorkspace={workspace([{ ...action(), available: false, reason_code: "latest_capa_not_accepted" }])} onTransition={onTransition} />);
    expect(screen.getByText(/Vòng khắc phục gần nhất chưa được chấp nhận/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chuyển theo policy" })).toBeDisabled();
    expect(onTransition).not.toHaveBeenCalled();
  });

  it("blocks another transition when the result cannot be verified", async () => {
    const onTransition = vi.fn().mockRejectedValue(new CaseFieldMutationRecoveryError("unverified"));
    render(<CaseLifecycleActions caseWorkspace={workspace([action()])} onTransition={onTransition} />);
    fireEvent.change(screen.getByLabelText("Lý do chuyển trạng thái"), { target: { value: "Draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Chuyển theo policy" }));
    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: "Chuyển theo policy" })).toBeDisabled();
    expect(screen.getByLabelText("Lý do chuyển trạng thái")).toHaveValue("Draft");
  });

  it("holds the exact reviewed reason read-only and disables cancellation after an unverified transition", async () => {
    const onTransition = vi.fn().mockRejectedValue(new CaseFieldMutationRecoveryError("transition outcome unknown"));
    const editor = (show: boolean) => <CaseDraftSession identity="case-A">
      {show ? <CaseLifecycleActions caseWorkspace={workspace([action()])} onTransition={onTransition} /> : null}
    </CaseDraftSession>;
    const view = render(editor(true));
    const input = screen.getByLabelText("Lý do chuyển trạng thái");
    fireEvent.change(input, { target: { value: "Lý do kết thúc cần đối chiếu" } });
    fireEvent.click(screen.getByRole("button", { name: "Chuyển theo policy" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("transition outcome unknown");
    expect(input).toHaveAttribute("readonly");
    expect(input).toHaveValue("Lý do kết thúc cần đối chiếu");
    expect(screen.getByRole("status")).toHaveTextContent("Lý do đã gửi được giữ nguyên");
    const cancel = screen.getByRole("button", { name: "Hủy nhập lý do chuyển trạng thái" });
    expect(cancel).toBeDisabled();
    fireEvent.change(input, { target: { value: "Attempt to overwrite original request" } });
    fireEvent.click(cancel);
    fireEvent.click(screen.getByRole("button", { name: "Chuyển theo policy" }));
    expect(input).toHaveValue("Lý do kết thúc cần đối chiếu");
    expect(onTransition).toHaveBeenCalledOnce();
    expect(onTransition).toHaveBeenCalledWith({
      expected_version: 18, target_state: "planned", reason: "Lý do kết thúc cần đối chiếu",
    });
    view.rerender(editor(false));
    view.rerender(editor(true));
    expect(screen.getByLabelText("Lý do chuyển trạng thái")).toHaveValue("Lý do kết thúc cần đối chiếu");
    expect(screen.getByLabelText("Lý do chuyển trạng thái")).toHaveAttribute("readonly");
    expect(screen.getByRole("button", { name: "Hủy nhập lý do chuyển trạng thái" })).toBeDisabled();
    expect(onTransition).toHaveBeenCalledOnce();
  });

  it("allows explicit revision and cancel when a transition is definitively rejected", async () => {
    const onTransition = vi.fn().mockRejectedValue(Object.assign(new Error("stale version"), { status: 409 }));
    render(<CaseLifecycleActions caseWorkspace={workspace([action()])} onTransition={onTransition} />);
    fireEvent.change(screen.getByLabelText("Lý do chuyển trạng thái"), { target: { value: "Stale attempt" } });
    fireEvent.click(screen.getByRole("button", { name: "Chuyển theo policy" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("stale version");
    const input = screen.getByLabelText("Lý do chuyển trạng thái");
    expect(input).not.toHaveAttribute("readonly");
    expect(screen.getByRole("button", { name: "Hủy nhập lý do chuyển trạng thái" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Hủy nhập lý do chuyển trạng thái" }));
    expect(input).toHaveValue("");
    expect(onTransition).toHaveBeenCalledOnce();
  });

  it("serializes repeated activation before the pending render", () => {
    const onTransition = vi.fn(() => new Promise<void>(() => {}));
    render(<CaseLifecycleActions caseWorkspace={workspace([action()])} onTransition={onTransition} />);
    const button = screen.getByRole("button", { name: "Chuyển theo policy" });
    act(() => { fireEvent.click(button); fireEvent.click(button); });
    expect(onTransition).toHaveBeenCalledOnce();
  });

  it("retains even an empty-reason transition intent after a rejected request", async () => {
    const onTransition = vi.fn().mockRejectedValue(new Error("Conflict"));
    const view = render(<CaseLifecycleActions caseWorkspace={workspace([action()])} onTransition={onTransition} />);
    fireEvent.click(screen.getByRole("button", { name: "Chuyển theo policy" }));
    await screen.findByRole("alert");
    view.rerender(<CaseLifecycleActions caseWorkspace={workspace([action(19)])} onTransition={onTransition} />);
    fireEvent.click(screen.getByRole("button", { name: "Chuyển theo policy" }));
    await waitFor(() => expect(onTransition).toHaveBeenCalledTimes(2));
    expect(onTransition.mock.calls[1][0].expected_version).toBe(18);
  });

  it("pins transition intent to the reviewed token through refresh and conflict until explicit cancel", async () => {
    const onTransition = vi.fn().mockRejectedValue(Object.assign(new Error("Conflict"), { status: 409 }));
    const view = render(<CaseLifecycleActions caseWorkspace={workspace([action()])} onTransition={onTransition} />);
    fireEvent.change(screen.getByLabelText("Lý do chuyển trạng thái"), { target: { value: "Reviewed at 18" } });
    view.rerender(<CaseLifecycleActions caseWorkspace={workspace([action(19)])} onTransition={onTransition} />);
    fireEvent.click(screen.getByRole("button", { name: "Chuyển theo policy" }));
    await screen.findByRole("alert");
    expect(onTransition).toHaveBeenCalledWith({ target_state: "planned", expected_version: 18, reason: "Reviewed at 18" });
    expect(onTransition).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("Lý do chuyển trạng thái")).toHaveValue("Reviewed at 18");
    fireEvent.click(screen.getByRole("button", { name: "Hủy nhập lý do chuyển trạng thái" }));
    fireEvent.change(screen.getByLabelText("Lý do chuyển trạng thái"), { target: { value: "Reviewed at 19" } });
    fireEvent.click(screen.getByRole("button", { name: "Chuyển theo policy" }));
    await waitFor(() => expect(onTransition).toHaveBeenCalledTimes(2));
    expect(onTransition.mock.calls[1][0].expected_version).toBe(19);
  });

  it("replaces the reason and pending owner when canonical Case changes", () => {
    const onTransition = vi.fn(() => new Promise<void>(() => {}));
    const view = render(<CaseLifecycleActions caseWorkspace={workspace([action()])} onTransition={onTransition} />);
    fireEvent.change(screen.getByLabelText("Lý do chuyển trạng thái"), { target: { value: "A reason" } });
    fireEvent.click(screen.getByRole("button", { name: "Chuyển theo policy" }));
    const next = { ...workspace([action()]), case_summary: { id: "case-B" } } as CaseWorkspace;
    view.rerender(<CaseLifecycleActions caseWorkspace={next} onTransition={onTransition} />);
    expect(screen.getByLabelText("Lý do chuyển trạng thái")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Chuyển theo policy" })).toBeEnabled();
  });

  it.each([null, undefined, NaN, 0, -1])("refuses a nonnumeric or invalid version %s", version => {
    const onTransition = vi.fn();
    render(<CaseLifecycleActions caseWorkspace={workspace([{ ...action(), expected_version: version as number }])} onTransition={onTransition} />);
    fireEvent.click(screen.getByRole("button", { name: "Chuyển theo policy" }));
    expect(onTransition).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Chuyển theo policy" })).toBeDisabled();
  });

  it.each([401, 403, 409, 422, undefined])("retains reason and token on %s without automatic retry", async status => {
    const onTransition = vi.fn().mockRejectedValue(Object.assign(new Error("Rejected transition"), { status }));
    const view = render(<CaseLifecycleActions caseWorkspace={workspace([action()])} onTransition={onTransition} />);
    fireEvent.change(screen.getByLabelText("Lý do chuyển trạng thái"), { target: { value: "Keep this reason" } });
    view.rerender(<CaseLifecycleActions caseWorkspace={workspace([action(19)])} onTransition={onTransition} />);
    fireEvent.click(screen.getByRole("button", { name: "Chuyển theo policy" }));
    await screen.findByRole("alert");
    expect(onTransition).toHaveBeenCalledOnce();
    expect(onTransition.mock.calls[0][0].expected_version).toBe(18);
    expect(screen.getByLabelText("Lý do chuyển trạng thái")).toHaveValue("Keep this reason");
  });

  it("requires explicit review when an action key is reused with another target", () => {
    const onTransition = vi.fn();
    const view = render(<CaseLifecycleActions caseWorkspace={workspace([action()])} onTransition={onTransition} />);
    fireEvent.change(screen.getByLabelText("Lý do chuyển trạng thái"), { target: { value: "Planned intent" } });
    view.rerender(<CaseLifecycleActions caseWorkspace={workspace([{ ...action(19), target_state: "inspection_completed" }])} onTransition={onTransition} />);
    expect(screen.getByRole("button", { name: "Chuyển theo policy" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Hủy nhập lý do chuyển trạng thái" }));
    expect(screen.getByRole("button", { name: "Chuyển theo policy" })).toBeEnabled();
    expect(onTransition).not.toHaveBeenCalled();
  });

  it("uses backend-owned target_state rather than parsing an arbitrary action key", async () => {
    const onTransition = vi.fn().mockResolvedValue(undefined);
    render(<CaseLifecycleActions caseWorkspace={workspace([{
      action_key: "opaque-server-action:99",
      label: "Chuyển theo policy",
      target_state: "planned",
      available: true,
      expected_version: 18,
      reason_code: null,
      required_permissions: ["case.edit"],
    }])} onTransition={onTransition} />);
    fireEvent.change(screen.getByLabelText("Lý do chuyển trạng thái"), { target: { value: "Đủ điều kiện" } });
    fireEvent.click(screen.getByRole("button", { name: "Chuyển theo policy" }));
    await waitFor(() => expect(onTransition).toHaveBeenCalledWith({
      target_state: "planned",
      expected_version: 18,
      reason: "Đủ điều kiện",
    }));
  });

  it("does not mutate for an unavailable backend action", () => {
    const onTransition = vi.fn();
    render(<CaseLifecycleActions caseWorkspace={workspace([{
      action_key: "opaque-server-action:blocked",
      label: "Bị chặn",
      target_state: "planned",
      available: false,
      expected_version: 18,
      reason_code: "missing_permission",
      required_permissions: ["case.edit"],
    }])} onTransition={onTransition} />);
    expect(screen.getByRole("button", { name: "Bị chặn" })).toBeDisabled();
    expect(screen.getByText(/missing_permission/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Bị chặn" }));
    expect(onTransition).not.toHaveBeenCalled();
  });
});


it("keeps reviewed lifecycle intent and the pending guard across same-Case pane unmount", async () => {
  let resolve!: () => void;
  const onTransition = vi.fn(() => new Promise<void>(done => { resolve = done; }));
  const actions = [{ action_key: "transition", label: "Transition", available: true, expected_version: 18, target_state: "planned", reason_code: null, required_permissions: [] }];
  const editor = (show: boolean, version = 18) => <CaseDraftSession identity="case-A">{show ? <CaseLifecycleActions caseWorkspace={workspace(actions.map(a => ({ ...a, expected_version: version })))} onTransition={onTransition} /> : null}</CaseDraftSession>;
  const view = render(editor(true));
  fireEvent.change(screen.getByLabelText("Lý do chuyển trạng thái"), { target: { value: "Reviewed reason" } });
  view.rerender(editor(false));view.rerender(editor(true, 19));
  expect(screen.getByLabelText("Lý do chuyển trạng thái")).toHaveValue("Reviewed reason");
  fireEvent.click(screen.getByRole("button", { name: "Transition" }));
  view.rerender(editor(false));view.rerender(editor(true, 19));
  expect(screen.getByRole("button", { name: "Đang chuyển..." })).toBeDisabled();
  expect(onTransition).toHaveBeenCalledWith({ expected_version: 18, target_state: "planned", reason: "Reviewed reason" });
  await act(async () => resolve());
  expect(screen.getByLabelText("Lý do chuyển trạng thái")).toHaveValue("");
  expect(onTransition).toHaveBeenCalledOnce();
});


describe("Case lifecycle exact command ownership after Case A → B → A", () => {
  const first = { action_key: "policy-A", label: "Chuyển theo policy", target_state: "planned", available: true, expected_version: 18, reason_code: null, required_permissions: ["case.edit"] };
  const second = { ...first, action_key: "policy-B", target_state: "closed", expected_version: 99 };
  function renderCase(id: string, onTransition: (payload: import("../../types").CaseTransitionRequest) => Promise<void>, actions = [first]) {
    return <CaseDraftSession identity={id}>
      <CaseLifecycleActions
        caseWorkspace={{ ...workspace(actions), case_summary: { id } } as CaseWorkspace}
        onTransition={onTransition}
      />
    </CaseDraftSession>;
  }

  it("restores exactly submitted target, token and trimmed reason in pending and unknown states without replay", async () => {
    let fail!: (reason: Error) => void;
    const onTransition = vi.fn(() => new Promise<void>((_, reject) => { fail = reject; }));
    const view = render(renderCase("case-A", onTransition));
    fireEvent.change(screen.getByLabelText("Lý do chuyển trạng thái"), { target: { value: "  Lý do đã gửi  " } });
    fireEvent.click(screen.getByRole("button", { name: "Chuyển theo policy" }));
    expect(onTransition).toHaveBeenCalledWith({ target_state: "planned", expected_version: 18, reason: "Lý do đã gửi" });
    view.rerender(renderCase("case-B", onTransition, [second]));
    expect(screen.getByLabelText("Lý do chuyển trạng thái")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Chuyển theo policy" })).toBeEnabled();
    view.rerender(renderCase("case-A", onTransition, [{ ...first, expected_version: 19, available: false }]));
    const restored = screen.getByLabelText("Lý do chuyển trạng thái");
    expect(restored).toHaveValue("Lý do đã gửi");
    expect(restored).toHaveAttribute("readonly");
    expect(screen.getByRole("status")).toHaveTextContent("expected_version 18");
    expect(screen.getByRole("status")).toHaveTextContent("Đang xác minh kết quả chuyển trạng thái");
    expect(screen.getByRole("button", { name: "Hủy nhập lý do chuyển trạng thái" })).toBeDisabled();
    fireEvent.change(restored, { target: { value: "Không được ghi đè" } });
    expect(restored).toHaveValue("Lý do đã gửi");
    await act(async () => fail(new CaseFieldMutationRecoveryError("canonical readback failed")));
    expect(screen.getByRole("status")).toHaveTextContent("Kết quả chuyển trạng thái chưa xác minh");
    view.rerender(renderCase("case-B", onTransition, [second]));
    view.rerender(renderCase("case-A", onTransition, [{ ...first, expected_version: 19, available: false }]));
    expect(screen.getByLabelText("Lý do chuyển trạng thái")).toHaveValue("Lý do đã gửi");
    expect(screen.getByRole("button", { name: "Hủy nhập lý do chuyển trạng thái" })).toBeDisabled();
    expect(onTransition).toHaveBeenCalledOnce();
  });

  it("does not resurrect an edit for a definite HTTP rejection and keeps Case B isolated", async () => {
    const onTransition = vi.fn().mockRejectedValue(Object.assign(new Error("stale"), { status: 409 }));
    const view = render(renderCase("case-A", onTransition));
    fireEvent.change(screen.getByLabelText("Lý do chuyển trạng thái"), { target: { value: "To be rejected" } });
    fireEvent.click(screen.getByRole("button", { name: "Chuyển theo policy" }));
    await screen.findByText("stale");
    view.rerender(renderCase("case-B", onTransition, [second]));
    expect(screen.getByRole("button", { name: "Chuyển theo policy" })).toBeEnabled();
    view.rerender(renderCase("case-A", onTransition));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Lý do chuyển trạng thái")).toHaveValue("");
    expect(screen.getByLabelText("Lý do chuyển trạng thái")).not.toHaveAttribute("readonly");
    expect(onTransition).toHaveBeenCalledOnce();
  });
});
