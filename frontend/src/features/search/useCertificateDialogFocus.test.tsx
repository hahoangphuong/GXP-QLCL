import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { useCertificateDialogFocus } from "./useCertificateDialogFocus";

function Dialog({ count, close }: { count: number; close: () => void }) {
  const ref = useCertificateDialogFocus();
  return <div><section ref={ref} role="dialog" aria-modal="true" tabIndex={-1}>
    {[0, 1, 2].map(index => <button key={index} disabled={index >= count}>Control {index}</button>)}
    <span onClick={close}>Close test dialog</span>
  </section></div>;
}
function Harness({ count, trigger = true }: { count: number; trigger?: boolean }) {
  const [open, setOpen] = useState(false);
  return <><header><button>Background</button></header><main>
    {trigger ? <button onClick={() => setOpen(true)}>Open dialog</button> : null}
    {open ? <Dialog count={count} close={() => setOpen(false)} /> : null}
  </main></>;
}
function pressTab(target: Element, shiftKey = false) {
  const event = new KeyboardEvent("keydown", { key: "Tab", shiftKey, bubbles: true, cancelable: true });
  act(() => target.dispatchEvent(event));
  return event.defaultPrevented;
}
function open() {
  const trigger = screen.getByRole("button", { name: "Open dialog" });
  act(() => trigger.focus());
  fireEvent.click(trigger);
  return trigger;
}

describe("certificate modal focus containment", () => {
  it.each([0, 1, 3])("contains Tab and Shift+Tab with %s enabled controls", (count) => {
    render(<Harness count={count} />);
    open();
    const dialog = screen.getByRole("dialog");
    const first = count ? screen.getByRole("button", { name: "Control 0" }) : dialog;
    const last = count ? screen.getByRole("button", { name: `Control ${count - 1}` }) : dialog;
    expect(first).toHaveFocus();
    expect(pressTab(first, true)).toBe(true);
    expect(last).toHaveFocus();
    expect(pressTab(last)).toBe(true);
    expect(first).toHaveFocus();
    if (count > 1) expect(pressTab(first)).toBe(false);
  });
  it("blocks background programmatic focus and makes background inert until close", () => {
    render(<Harness count={3} />);
    const trigger = open();
    const background = screen.getByRole("button", { name: "Background" });
    act(() => background.focus());
    expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement);
    expect(background.closest("header")).toHaveAttribute("inert");
    fireEvent.click(screen.getByText("Close test dialog"));
    expect(trigger).toHaveFocus();
    expect(background.closest("header")).not.toHaveAttribute("inert");
  });
  it("uses container while pending and returns to an enabled control after pending", () => {
    const { rerender } = render(<Harness count={3} />);
    open();
    act(() => screen.getByRole("button", { name: "Control 2" }).focus());
    rerender(<Harness count={0} />);
    expect(screen.getByRole("dialog")).toHaveFocus();
    expect(pressTab(screen.getByRole("dialog"))).toBe(true);
    rerender(<Harness count={1} />);
    expect(screen.getByRole("button", { name: "Control 0" })).toHaveFocus();
  });
  it("closes safely after its trigger unmounts and restores existing inert attributes", () => {
    const { rerender } = render(<Harness count={1} />);
    screen.getByRole("button", { name: "Background" }).closest("header")!.setAttribute("inert", "");
    open();
    rerender(<Harness count={1} trigger={false} />);
    fireEvent.click(screen.getByText("Close test dialog"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Background" }).closest("header")).toHaveAttribute("inert");
  });
});
