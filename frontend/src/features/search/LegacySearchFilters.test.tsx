import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LegacySearchFilters } from "./LegacySearchFilters";

const filters = { generalQuery: "", province: "", caseState: "", certificateState: "", certificateExpiringWithinDays: "" };
describe("Legacy search filter ownership", () => {
  it("closes the filter surface with Escape and restores focus without changing the query", () => {
    const change = vi.fn(); const { container } = render(<LegacySearchFilters filters={filters} onChange={change} />);
    const details = container.querySelector("details")!;
    details.open = true;
    fireEvent.keyDown(screen.getByLabelText("Tỉnh/thành"), { key: "Escape" });
    expect(details.open).toBe(false);
    expect(container.querySelector("summary")).toHaveFocus();
    expect(change).not.toHaveBeenCalled();
  });
  it("preserves a URL-owned expiry window outside the offered presets", () => {
    const change = vi.fn(); render(<LegacySearchFilters filters={{ ...filters, certificateExpiringWithinDays: "15" }} onChange={change} />);
    expect(screen.getByLabelText("Sắp hết hạn")).toHaveValue("15");
    expect(screen.getByRole("option", { name: "15 ngày" })).toBeInTheDocument();
    expect(change).not.toHaveBeenCalled();
  });
  it("represents multiple URL states without pretending that all states are included", () => {
    const change = vi.fn(); render(<LegacySearchFilters filters={filters} multipleCaseStates onChange={change} />);
    expect(screen.getByLabelText("Trạng thái hồ sơ")).toHaveValue("__multiple__"); expect(change).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Trạng thái hồ sơ"), { target: { value: "planned" } });
    expect(change).toHaveBeenCalledWith("caseState", "planned");
  });
  it("keeps quick search and supported groups connected to the owner's fields", () => {
    const change = vi.fn(); render(<LegacySearchFilters filters={filters} onChange={change} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Tìm nhanh" }), { target: { value: "cơ sở" } });
    expect(change).toHaveBeenLastCalledWith("generalQuery", "cơ sở");
    fireEvent.change(screen.getByLabelText("Tỉnh/thành"), { target: { value: "Hà Nội" } });
    expect(change).toHaveBeenLastCalledWith("province", "Hà Nội");
    fireEvent.change(screen.getByLabelText("Hiệu lực"), { target: { value: "active" } });
    expect(change).toHaveBeenLastCalledWith("certificateState", "active");
    fireEvent.change(screen.getByLabelText("Sắp hết hạn"), { target: { value: "30" } });
    expect(change).toHaveBeenLastCalledWith("certificateExpiringWithinDays", "30");
  });
  it("opening or closing the filter surface never changes filters", () => {
    const change = vi.fn(); render(<LegacySearchFilters filters={{ ...filters, province: "Hà Nội" }} onChange={change} />);
    fireEvent.click(screen.getByText("Lọc dữ liệu")); fireEvent.click(screen.getByText("Lọc dữ liệu"));
    expect(change).not.toHaveBeenCalled(); expect(screen.getByLabelText("Tỉnh/thành")).toHaveValue("Hà Nội");
  });
  it("reflects external URL-owned values rather than keeping a second filter draft", () => {
    const change = vi.fn(); const view = render(<LegacySearchFilters filters={filters} onChange={change} />);
    view.rerender(<LegacySearchFilters filters={{ ...filters, generalQuery: "external", certificateExpiringWithinDays: "90" }} onChange={change} />);
    expect(screen.getByRole("textbox", { name: "Tìm nhanh" })).toHaveValue("external");
    expect(screen.getByLabelText("Sắp hết hạn")).toHaveValue("90"); expect(change).not.toHaveBeenCalled();
  });
});
