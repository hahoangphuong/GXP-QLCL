import "@testing-library/jest-dom/vitest";
import { useState, type ComponentProps } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FacilityWorkspaceTabs } from "./FacilityWorkspaceTabs";
import { FACILITY_TABS as labels, FACILITY_TAB_LABELS, resolveFacilityTab, type FacilityTab } from "./facilityTabs";

// Isolate the tab owner. Each stub marks a mounted business workspace; hidden
// ARIA shells must never mount these children.
vi.mock("./FacilitySummary", () => ({ FacilitySummary: () => <form aria-label="General form"><input aria-label="Nested input" /><button type="button">Nested button</button></form> }));
vi.mock("./EventWorkspace", () => ({ EventWorkspace: ({ openableCertificateIds, onOpenLinkedCertificate }: { openableCertificateIds?: string[]; onOpenLinkedCertificate?: (id: string) => void }) => <div data-testid="event-child">Event workspace{openableCertificateIds?.map(id => <button key={id} type="button" onClick={() => onOpenLinkedCertificate?.(id)}>Mở {id}</button>)}</div> }));
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
  it("uses legacy captions without changing deep-link or activation keys", () => {
    const values = props(); render(<FacilityWorkspaceTabs {...values} />);
    expect(tabs().map(tab => tab.textContent)).toEqual(labels.map(tab => FACILITY_TAB_LABELS[tab]));
    fireEvent.click(screen.getByRole("tab", { name: "Giấy chứng nhận GPs" }));
    expect(values.onFacilityTabChange).toHaveBeenCalledWith("Giấy chứng nhận GxP");
    expect(resolveFacilityTab("Giấy chứng nhận đủ điều kiện")).toBe("Giấy chứng nhận đủ điều kiện");
  });
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
    expect(screen.getByRole("tabpanel", { name: FACILITY_TAB_LABELS[labels[1]] })).toBeInTheDocument();
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


it("returns from a verified selected Certificate to its own Case without performing any mutation", () => {
  const base = props("Giấy chứng nhận GxP");
  const onFacilityTabChange = vi.fn();
  const onEventTabChange = vi.fn();
  const selected = {
    ...base,
    selectedHistory: { id: "case-A", source_type: "case" },
    caseWorkspace: { case_summary: { id: "case-A", site_id: "site-1" } },
    caseWorkspaceLoading: false, caseWorkspaceError: null,
    gxpCertificatesLoading: false, gxpCertificatesError: null,
    gxpCertificateDetailLoading: false, gxpCertificateDetailError: null,
    selectedGxpCertificateId: "cert-A",
    gxpCertificates: [{ certificate_id: "cert-A", case_id: "case-A", site_id: "site-1" }],
    gxpCertificateDetail: { certificate_id: "cert-A", case_id: "case-A", site_id: "site-1" },
    onFacilityTabChange, onEventTabChange,
  } as unknown as Props;
  const view = render(<FacilityWorkspaceTabs {...selected} />);
  fireEvent.click(screen.getByRole("button", { name: "Quay lại Case để kiểm tra hoàn tất" }));
  expect(onEventTabChange).toHaveBeenCalledOnce();
  expect(onEventTabChange).toHaveBeenCalledWith("Kiểm tra");
  expect(onFacilityTabChange).toHaveBeenCalledOnce();
  expect(onFacilityTabChange).toHaveBeenCalledWith("Các đợt kiểm tra & thay đổi");
  const mismatches = [
    { selectedHistory: { id: "case-B", source_type: "case" } },
    { selectedHistory: { id: "case-A", source_type: "change_request" } },
    { caseWorkspace: { case_summary: { id: "case-B", site_id: "site-1" } } },
    { caseWorkspace: { case_summary: { id: "case-A", site_id: "other-site" } } },
    { gxpCertificateDetail: { certificate_id: "cert-A", case_id: "case-B", site_id: "site-1" } },
    { gxpCertificateDetail: { certificate_id: "cert-B", case_id: "case-A", site_id: "site-1" } },
    { gxpCertificateDetail: { certificate_id: "cert-A", case_id: "case-A", site_id: "other-site" } },
    { gxpCertificates: [] },
    { gxpCertificates: [{ certificate_id: "cert-A", case_id: "case-B", site_id: "site-1" }] },
    { gxpCertificates: [{ certificate_id: "cert-A", case_id: "case-A", site_id: "other-site" }] },
    { gxpCertificateDetailLoading: true },
    { caseWorkspaceError: "canonical unavailable" },
  ];
  for (const mismatch of mismatches) {
    view.rerender(<FacilityWorkspaceTabs {...({ ...selected, ...mismatch } as unknown as Props)} />);
    expect(screen.queryByRole("button", { name: "Quay lại Case để kiểm tra hoàn tất" })).not.toBeInTheDocument();
  }
});


it("opens only a matching linked Certificate UUID from the selected Case", () => {
  const base = props("Các đợt kiểm tra & thay đổi");
  const onGxpCertificateSelect = vi.fn();
  const onFacilityTabChange = vi.fn();
  const valid = {
    ...base,
    selectedHistory: { id: "case-A", source_type: "case" },
    caseWorkspace: { case_summary: { id: "case-A", site_id: "site-1" },
      linked_gxp_certificates: [
        { certificate_id: "cert-A", case_id: "case-A", site_id: "site-1", certificate_type: "GMP" },
        { certificate_id: "cert-B", case_id: "case-A", site_id: "site-1", certificate_type: "GMP" },
      ] },
    caseWorkspaceLoading: false, caseWorkspaceError: null,
    gxpCertificatesLoading: false, gxpCertificatesError: null,
    gxpCertificates: [{ certificate_id: "cert-B", case_id: "case-A", site_id: "site-1", certificate_type: "GMP" }],
    onGxpCertificateSelect, onFacilityTabChange,
  } as unknown as Props;
  const view = render(<FacilityWorkspaceTabs {...valid} />);
  expect(screen.queryByRole("button", { name: "Mở cert-A" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Mở cert-B" }));
  expect(onGxpCertificateSelect).toHaveBeenCalledOnce();
  expect(onGxpCertificateSelect).toHaveBeenCalledWith("cert-B");
  expect(onFacilityTabChange).toHaveBeenCalledOnce();
  expect(onFacilityTabChange).toHaveBeenCalledWith("Giấy chứng nhận GxP");
  for (const invalid of [
    { selectedHistory: { id: "case-A", source_type: "change_request" } },
    { caseWorkspace: { ...valid.caseWorkspace, case_summary: { id: "case-A", site_id: "other-site" } } },
    { gxpCertificatesLoading: true },
    { gxpCertificatesError: "unverified" },
    { gxpCertificates: [{ certificate_id: "cert-B", case_id: "case-other", site_id: "site-1", certificate_type: "GMP" }] },
    { gxpCertificates: [{ certificate_id: "cert-B", case_id: "case-A", site_id: "site-1", certificate_type: "GLP" }] },
  ]) {
    view.rerender(<FacilityWorkspaceTabs {...({ ...valid, ...invalid } as unknown as Props)} />);
    expect(screen.queryByRole("button", { name: "Mở cert-B" })).not.toBeInTheDocument();
  }
});
