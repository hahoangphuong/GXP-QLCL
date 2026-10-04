import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CaseWorkspace } from "../../types";
import { CaseLifecycleActions } from "./CaseLifecycleActions";

function workspace(actions: CaseWorkspace["transition_actions"]): CaseWorkspace {
  return { transition_actions: actions } as CaseWorkspace;
}

describe("CaseLifecycleActions", () => {
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
