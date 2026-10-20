import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { FacilitySearchResult } from "../../types";
import { FacilityTable } from "./FacilityTable";

function row(resultKey: string, facilityName: string): FacilitySearchResult {
  return {
    result_key: resultKey,
    site_id: `site-${resultKey}`,
    legacy_site_id: null,
    facility_code: resultKey,
    context_code: resultKey,
    result_grain: "production_line",
    gxp_type: "GMP",
    line_code: resultKey,
    production_line_id: `line-${resultKey}`,
    production_line_code: resultKey,
    production_line_identity_state: "canonical",
    facility_name: facilityName,
    company_name: facilityName,
    gxp_types: ["GMP"],
    certificate_scope_summary: "Thuốc không vô trùng",
    province_name: "Hà Nội",
    last_inspection_on: "2026-10-18",
    current_state: "planned",
    current_certificate_number: null,
    current_certificate_expiry: null,
  };
}

const rows = [row("1.A", "Cơ sở A"), row("2.A", "Cơ sở B"), row("3.A", "Cơ sở C")];

function focus(element: HTMLElement) {
  act(() => element.focus());
}

function renderTable(overrides: Partial<React.ComponentProps<typeof FacilityTable>> = {}) {
  const onSelect = vi.fn();
  const onGxpTypeChange = vi.fn();
  const rendered = render(<FacilityTable
    filters={{ facilityName: "", certificateScope: "" }}
    hasMore={false}
    hiddenFilters={{
      generalQuery: "",
      province: "",
      changeRequestStates: [],
      certificateState: "",
      certificateExpiringWithinDays: "",
    }}
    loading={false}
    onFilterChange={vi.fn()}
    onGxpTypeChange={onGxpTypeChange}
    onReachEnd={vi.fn()}
    onSelect={onSelect}
    rows={rows}
    selectedGxpType="GMP"
    selectedResultKey="2.A"
    {...overrides}
  />);
  const rerenderTable = (nextOverrides: Partial<React.ComponentProps<typeof FacilityTable>>) => {
    rendered.rerender(<FacilityTable
      filters={{ facilityName: "", certificateScope: "" }}
      hasMore={false}
      hiddenFilters={{
        generalQuery: "",
        province: "",
        changeRequestStates: [],
        certificateState: "",
        certificateExpiringWithinDays: "",
      }}
      loading={false}
      onFilterChange={vi.fn()}
      onGxpTypeChange={onGxpTypeChange}
      onReachEnd={vi.fn()}
      onSelect={onSelect}
      rows={rows}
      selectedGxpType="GMP"
      selectedResultKey="2.A"
      {...overrides}
      {...nextOverrides}
    />);
  };
  return { onSelect, onGxpTypeChange, rerenderTable };
}

describe("FacilityTable master selection keyboard", () => {
  it("moves row focus with Arrow/Home/End without selecting, then activates the exact row", () => {
    const { onSelect } = renderTable();
    const bodyRows = within(screen.getByRole("table")).getAllByRole("row").slice(1);

    expect(bodyRows.map((item) => item.tabIndex)).toEqual([-1, 0, -1]);
    focus(bodyRows[1]);
    fireEvent.keyDown(bodyRows[1], { key: "ArrowDown" });
    expect(bodyRows[2]).toHaveFocus();
    fireEvent.keyDown(bodyRows[2], { key: "Home" });
    expect(bodyRows[0]).toHaveFocus();
    fireEvent.keyDown(bodyRows[0], { key: "End" });
    expect(bodyRows[2]).toHaveFocus();
    fireEvent.keyDown(bodyRows[2], { key: "ArrowUp" });
    expect(bodyRows[1]).toHaveFocus();
    expect(onSelect).not.toHaveBeenCalled();

    fireEvent.keyDown(bodyRows[1], { key: "Enter" });
    fireEvent.keyDown(bodyRows[2], { key: " " });
    expect(onSelect.mock.calls).toEqual([["2.A"], ["3.A"]]);
  });

  it("uses one tab stop in the GxP rail and moves focus without changing the filter", () => {
    const { onGxpTypeChange } = renderTable();
    const tabs = screen.getAllByRole("tab");

    expect(tabs.map((tab) => tab.tabIndex)).toEqual([0, -1, -1]);
    focus(tabs[0]);
    fireEvent.keyDown(tabs[0], { key: "ArrowDown" });
    expect(tabs[1]).toHaveFocus();
    fireEvent.keyDown(tabs[1], { key: "End" });
    expect(tabs[2]).toHaveFocus();
    fireEvent.keyDown(tabs[2], { key: "Home" });
    expect(tabs[0]).toHaveFocus();
    fireEvent.keyDown(tabs[0], { key: "ArrowUp" });
    expect(tabs[2]).toHaveFocus();
    expect(onGxpTypeChange).not.toHaveBeenCalled();

    fireEvent.click(tabs[2]);
    expect(onGxpTypeChange).toHaveBeenCalledWith("GMPbb");
  });

  it("falls back to the first row and first GxP tab when the selected identity is absent", () => {
    renderTable({ selectedResultKey: "missing", selectedGxpType: "GDP" });
    const bodyRows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(bodyRows.map((item) => item.tabIndex)).toEqual([0, -1, -1]);
    expect(screen.getAllByRole("tab").map((tab) => tab.tabIndex)).toEqual([0, -1, -1]);
  });

  it("keeps a surviving focused result as the sole row tab stop through append and reorder", () => {
    const { onSelect, rerenderTable } = renderTable({ selectedResultKey: "1.A" });
    let bodyRows = within(screen.getByRole("table")).getAllByRole("row").slice(1);

    focus(bodyRows[0]);
    fireEvent.keyDown(bodyRows[0], { key: "ArrowDown" });
    expect(bodyRows[1]).toHaveFocus();
    expect(bodyRows.map((item) => item.tabIndex)).toEqual([-1, 0, -1]);

    rerenderTable({
      rows: [row("3.A", "Cơ sở C"), row("2.A", "Cơ sở B"), row("1.A", "Cơ sở A"), row("4.A", "Cơ sở D")],
      selectedResultKey: "1.A",
    });
    bodyRows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(bodyRows[1]).toHaveFocus();
    expect(bodyRows.map((item) => item.tabIndex)).toEqual([-1, 0, -1, -1]);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("moves focus to the nearest surviving result when the focused identity is removed", () => {
    const { onSelect, rerenderTable } = renderTable({ selectedResultKey: "1.A" });
    let bodyRows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    focus(bodyRows[0]);
    fireEvent.keyDown(bodyRows[0], { key: "ArrowDown" });
    expect(bodyRows[1]).toHaveFocus();

    rerenderTable({ rows: [rows[0], rows[2]], selectedResultKey: "1.A" });
    bodyRows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(bodyRows[1]).toHaveFocus();
    expect(bodyRows.map((item) => item.tabIndex)).toEqual([-1, 0]);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("does not steal focus back from a filter when an earlier focused row disappears", () => {
    const { onSelect, rerenderTable } = renderTable({ selectedResultKey: "1.A" });
    const bodyRows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    focus(bodyRows[1]);
    const nameFilter = screen.getByRole("textbox", { name: "Tên cơ sở" });
    focus(nameFilter);

    rerenderTable({ rows: [rows[0], rows[2]], selectedResultKey: "1.A" });
    expect(nameFilter).toHaveFocus();
    expect(within(screen.getByRole("table")).getAllByRole("row").slice(1).map((item) => item.tabIndex)).toEqual([0, -1]);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("retains a surviving focused row when the selected result leaves the list", () => {
    const { onSelect, rerenderTable } = renderTable({ selectedResultKey: "1.A" });
    let bodyRows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    focus(bodyRows[2]);

    rerenderTable({ rows: [rows[1], rows[2]], selectedResultKey: "1.A" });
    bodyRows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(bodyRows[1]).toHaveFocus();
    expect(bodyRows.map((item) => item.tabIndex)).toEqual([-1, 0]);
    expect(bodyRows.every((item) => item.getAttribute("aria-selected") === "false")).toBe(true);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("keeps focus in the master region when a focused result becomes an empty loading state", () => {
    const { onSelect, rerenderTable } = renderTable({ selectedResultKey: "1.A" });
    const bodyRows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    focus(bodyRows[1]);

    rerenderTable({ rows: [], loading: true, selectedResultKey: null });
    expect(screen.getByTestId("facility-table-scroll")).toHaveFocus();
    expect(onSelect).not.toHaveBeenCalled();

    rerenderTable({ rows: [rows[2]], loading: false, selectedResultKey: null });
    expect(screen.getByTestId("facility-table-scroll")).toHaveFocus();
    expect(within(screen.getByRole("table")).getAllByRole("row").slice(1)[0]).toHaveAttribute("tabindex", "0");
  });

  it("keeps the focused GxP control as the sole rail tab stop until activation settles", () => {
    const { onGxpTypeChange, rerenderTable } = renderTable({ selectedGxpType: "GMP" });
    let tabs = screen.getAllByRole("tab");
    focus(tabs[0]);
    fireEvent.keyDown(tabs[0], { key: "ArrowDown" });
    expect(tabs[1]).toHaveFocus();
    expect(tabs.map((tab) => tab.tabIndex)).toEqual([-1, 0, -1]);
    expect(onGxpTypeChange).not.toHaveBeenCalled();

    fireEvent.click(tabs[1]);
    rerenderTable({ selectedGxpType: "GLP" });
    tabs = screen.getAllByRole("tab");
    expect(tabs[1]).toHaveFocus();
    expect(tabs.map((tab) => tab.tabIndex)).toEqual([-1, 0, -1]);
    expect(onGxpTypeChange).toHaveBeenCalledTimes(1);
  });

  it("exposes one polite search status and busy state across loading, ready, empty and error", () => {
    const { rerenderTable } = renderTable({ rows: [], loading: true, selectedResultKey: null });
    const region = screen.getByRole("region", { name: "Danh sách cơ sở" });
    expect(region).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    expect(screen.getByRole("status")).toHaveAttribute("aria-atomic", "true");
    expect(screen.getByRole("status")).toHaveTextContent("Đang tải danh sách cơ sở");

    rerenderTable({ rows, loading: false, selectedResultKey: "1.A" });
    expect(region).toHaveAttribute("aria-busy", "false");
    expect(screen.getByRole("status")).toHaveTextContent("3 kết quả cơ sở");

    rerenderTable({ rows: [], loading: false, selectedResultKey: null });
    expect(screen.getByRole("status")).toHaveTextContent("Không tìm thấy cơ sở phù hợp");

    rerenderTable({ rows: [], loading: false, error: "Không tải được danh sách", selectedResultKey: null });
    expect(screen.getByRole("alert")).toHaveTextContent("Không tải được danh sách");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    rerenderTable({ rows, loading: false, error: "Không tải thêm được danh sách", selectedResultKey: "1.A" });
    expect(screen.getByRole("alert")).toHaveTextContent("Không tải thêm được danh sách");
    expect(screen.getAllByRole("row")).toHaveLength(4);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
