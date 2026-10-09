import "@testing-library/jest-dom/vitest";
import { useState, type ComponentProps } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FacilityWorkspaceTabs } from "./FacilityWorkspaceTabs";
import { FACILITY_TABS as labels, type FacilityTab } from "./facilityTabs";

// Isolate the tab owner. Each stub marks a mounted business workspace; hidden
// ARIA shells must never mount these children.
vi.mock("./FacilitySummary", () => ({ FacilitySummary: () => <form aria-label="General form"><input aria-label="Nested input" /><button type="button">Nested button</button></form> }));
vi.mock("./EventWorkspace", () => ({ EventWorkspace: () => <div data-testid="event-child">Event workspace</div> }));
vi.mock("./GxpCertificateWorkspace", () => ({ GxpCertificateWorkspace: () => <div data-testid="gxp-child">GxP workspace</div> }));
vi.mock("./BusinessEligibilityWorkspace", () => ({ BusinessEligibilityWorkspace: () => <div data-testid="eligibility-child">Eligibility workspace</div> }));

afterEach(cleanup);
type Props = ComponentProps<typeof FacilityWorkspaceTabs>;
function props(selectedFacilityTab: FacilityTab = labels[0]): Props {
  // Unused child callbacks are intentionally omitted by this isolated test.
  return {
    summary: { site_id: "site-1", facility_name: "Facility A", gxp_types: ["GMP"], selected_gxp_type: "GMP", selected_line_code: "A", selected_production_line_id: "uuid-A", current_state: "planned" },
    selectedFacilityTab, onFacilityTabChange: vi.fn(),
  } as unknown as Props;
}
function ControlledTabs() {
  const [tab, setTab] = useState<FacilityTab>(labels[0]);
  return <FacilityWorkspaceTabs {...props(tab)} onFacilityTabChange={setTab} />;
}
function tabs() { return within(screen.getByRole("tablist", { name: "Tab nghiệp vụ cơ sở" })).getAllByRole("tab"); }

describe("FacilityWorkspaceTabs keyboard and ARIA", () => {
  it("moves focus with arrows, wraps at either end and handles Home/End without activation", () => {
    const values = props();
    render(<FacilityWorkspaceTabs {...values} />);
    const items = tabs();
    act(() => items[0].focus());
    for (const [key, index] of [["ArrowLeft", 3], ["ArrowRight", 0], ["End", 3], ["Home", 0], ["ArrowRight", 1]] as const) {
      fireEvent.keyDown(document.activeElement!, { key });
      expect(items[index]).toHaveFocus();
      expect(items.filter((tab) => tab.tabIndex === 0)).toEqual([items[index]]);
    }
    expect(items[0]).toHaveAttribute("aria-selected", "true");
    expect(values.onFacilityTabChange).not.toHaveBeenCalled();
    expect(screen.getByRole("form", { name: "General form" })).toBeInTheDocument();
    expect(screen.queryByTestId("event-child")).not.toBeInTheDocument();
  });

  it("activates with Enter, Space and click, mounting only the selected content", () => {
    render(<ControlledTabs />);
    const items = tabs();
    act(() => items[0].focus());
    fireEvent.keyDown(items[0], { key: "ArrowRight" });
    fireEvent.keyDown(items[1], { key: "Enter" });
    expect(items[1]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("event-child")).toBeInTheDocument();
    fireEvent.keyDown(items[1], { key: "ArrowRight" });
    fireEvent.keyDown(items[2], { key: " " });
    expect(items[2]).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByTestId("event-child")).not.toBeInTheDocument();
    expect(screen.getByTestId("gxp-child")).toBeInTheDocument();
    fireEvent.click(items[3]);
    expect(items[3]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("eligibility-child")).toBeInTheDocument();
    expect(items.filter((tab) => tab.getAttribute("aria-selected") === "true")).toHaveLength(1);
  });

  it("links every tab to an existing panel and keeps IDs stable through rerenders", () => {
    const values = props();
    const { rerender } = render(<FacilityWorkspaceTabs {...values} />);
    const ids = tabs().map((tab) => tab.id);
    for (const tab of tabs()) {
      const panel = document.getElementById(tab.getAttribute("aria-controls")!)!;
      expect(panel).toHaveAttribute("role", "tabpanel");
      expect(panel).toHaveAttribute("aria-labelledby", tab.id);
      expect(panel.hidden).toBe(tab.getAttribute("aria-selected") !== "true");
    }
    expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
    expect(screen.getByRole("tabpanel", { name: labels[0] })).toHaveAttribute("tabindex", "0");
    rerender(<FacilityWorkspaceTabs {...values} selectedFacilityTab={labels[1]} />);
    expect(tabs().map((tab) => tab.id)).toEqual(ids);
    expect(screen.getByRole("tabpanel", { name: labels[1] })).toBeInTheDocument();
  });

  it("resets the roving entry on exit and follows external selection within the tablist", () => {
    const values = props();
    const { rerender } = render(<FacilityWorkspaceTabs {...values} />);
    const items = tabs();
    act(() => items[0].focus());
    fireEvent.keyDown(items[0], { key: "End" });
    act(() => screen.getByRole("textbox", { name: "Nested input" }).focus());
    expect(items[0]).toHaveAttribute("tabindex", "0");
    expect(items[3]).toHaveAttribute("tabindex", "-1");
    act(() => items[0].focus());
    fireEvent.keyDown(items[0], { key: "ArrowRight" });
    rerender(<FacilityWorkspaceTabs {...values} selectedFacilityTab={labels[2]} />);
    expect(items[2]).toHaveFocus();
    expect(items[2]).toHaveAttribute("tabindex", "0");
  });

  it("resets focus on an external line change without stealing focus outside the tablist", () => {
    const values = props();
    const { rerender } = render(<><button>Outside history</button><FacilityWorkspaceTabs {...values} /></>);
    act(() => tabs()[0].focus());
    fireEvent.keyDown(tabs()[0], { key: "End" });
    rerender(<><button>Outside history</button><FacilityWorkspaceTabs {...values} summary={{ ...values.summary, selected_production_line_id: "uuid-B" }} /></>);
    expect(tabs()[0]).toHaveFocus();
    act(() => screen.getByRole("button", { name: "Outside history" }).focus());
    rerender(<><button>Outside history</button><FacilityWorkspaceTabs {...values} selectedFacilityTab={labels[1]} /></>);
    expect(screen.getByRole("button", { name: "Outside history" })).toHaveFocus();
    expect(tabs()[1]).toHaveAttribute("tabindex", "0");
  });

  it("leaves keyboard events on nested forms and controls untouched", () => {
    const values = props();
    render(<FacilityWorkspaceTabs {...values} />);
    for (const element of [screen.getByRole("textbox"), screen.getByRole("button", { name: "Nested button" })]) {
      for (const key of ["ArrowLeft", "ArrowRight", "Home", "End", "Enter", " "]) {
        const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
        fireEvent(element, event);
        expect(event.defaultPrevented).toBe(false);
      }
    }
    expect(values.onFacilityTabChange).not.toHaveBeenCalled();
  });
});
