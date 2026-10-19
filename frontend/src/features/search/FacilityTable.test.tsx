import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
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

function renderTable(overrides: Partial<React.ComponentProps<typeof FacilityTable>> = {}) {
  const onSelect = vi.fn();
  const onGxpTypeChange = vi.fn();
  render(<FacilityTable
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
  return { onSelect, onGxpTypeChange };
}

describe("FacilityTable master selection keyboard", () => {
  it("moves row focus with Arrow/Home/End without selecting, then activates the exact row", () => {
    const { onSelect } = renderTable();
    const bodyRows = within(screen.getByRole("table")).getAllByRole("row").slice(1);

    expect(bodyRows.map((item) => item.tabIndex)).toEqual([-1, 0, -1]);
    bodyRows[1].focus();
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
    tabs[0].focus();
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
});
