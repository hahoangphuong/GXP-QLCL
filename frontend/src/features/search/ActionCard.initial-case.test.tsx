import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ActionCard } from "./ActionCard";
import type { WorkspaceActionReadiness } from "../../types";

const action = (readiness_status: WorkspaceActionReadiness["readiness_status"], action_key = "create_initial_case"): WorkspaceActionReadiness => ({
  action_key, label: "Hồ sơ mới", readiness_status,
  detail: "Chọn loại GxP được hỗ trợ (GMP/GLP/GMPbb).",
  required_permissions: ["case.edit"],
});

describe("Initial Case first-registration entrypoint", () => {
  it("opens context-selection editor when a new Site has no GxP yet", () => {
    const select = vi.fn();
    render(<ActionCard actions={[action("unavailable")]} onActionSelect={select} />);
    const button = screen.getByRole("button", { name: "Hồ sơ mới" });
    expect((button as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(button);
    expect(select).toHaveBeenCalledExactlyOnceWith("create_initial_case");
  });

  it.each(["forbidden", "conflict", "loading"] as const)(
    "does not admit opening initial Case from %s backend action", (status) => {
      const select = vi.fn();
      render(<ActionCard actions={[action(status)]} onActionSelect={select} />);
      const button = screen.getByRole("button", { name: "Hồ sơ mới" }) as HTMLButtonElement;
      expect(button.disabled).toBe(true);
      fireEvent.click(button);
      expect(select).not.toHaveBeenCalled();
    },
  );

  it("does not loosen other mutation actions with unavailable readiness", () => {
    const select = vi.fn();
    render(<ActionCard actions={[action("unavailable", "create_production_line")]} onActionSelect={select} />);
    expect((screen.getByRole("button", { name: "Hồ sơ mới" }) as HTMLButtonElement).disabled).toBe(true);
    expect(select).not.toHaveBeenCalled();
  });
});
