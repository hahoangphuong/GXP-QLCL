import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FacilityHistoryItem } from "../../types";
import { HistoryTable } from "./HistoryTable";

afterEach(cleanup);

const rows: FacilityHistoryItem[] = [
  { id: "case-uuid", source_type: "case", reference_code: "KT-01", event_type: "Định kỳ", gxp_type: "GMP", standard: "WHO-GMP", occurred_on: "2026-09-04", state: "awaiting_certificate_decision" },
  { id: "change-uuid", source_type: "change_request", reference_code: "TD-02", event_type: "Thay đổi cơ sở", gxp_type: "GMP", standard: "Tiêu chuẩn với nội dung tiếng Việt rất dài", occurred_on: null, state: "under_review" },
  { id: "another-case-uuid", source_type: "case", reference_code: null, event_type: "Định kỳ", gxp_type: "GMP", standard: null, occurred_on: null, state: "future_backend_state" },
];

function bodyRows() {
  return screen.getAllByRole("row").slice(1);
}

describe("HistoryTable", () => {
  it("shows four business columns and authoritative states, retaining full long text and missing values", () => {
    render(<HistoryTable rows={rows} selectedHistoryId="case-uuid" onSelect={vi.fn()} />);
    expect(screen.getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Loại", "Tiêu chuẩn", "Ngày", "Trạng thái"]);
    const tableRows = bodyRows();
    expect(within(tableRows[0]).getByText("Chờ cấp chứng nhận")).toBeInTheDocument();
    expect(within(tableRows[0]).getByText("04-09-2026")).toBeInTheDocument();
    expect(within(tableRows[1]).getByText("Thay đổi")).toHaveAttribute("title", "Thay đổi cơ sở");
    expect(within(tableRows[1]).getByText(rows[1].standard!)).toHaveAttribute("title", rows[1].standard);
    expect(within(tableRows[1]).getByText("Đang xem xét")).toBeInTheDocument();
    expect(within(tableRows[2]).getByText("future_backend_state")).toBeInTheDocument();
    expect(within(tableRows[2]).getAllByText("Chưa có")).toHaveLength(2);
    expect(screen.queryByText("KT-01")).not.toBeInTheDocument();
  });

  it("moves focus with arrows and Home/End without changing selection, then activates exact IDs", () => {
    const onSelect = vi.fn();
    render(<HistoryTable rows={rows} selectedHistoryId="case-uuid" onSelect={onSelect} />);
    const [first, second, last] = bodyRows();
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowUp" });
    expect(first).toHaveFocus();
    fireEvent.keyDown(first, { key: "ArrowDown" });
    expect(second).toHaveFocus();
    fireEvent.keyDown(second, { key: "End" });
    expect(last).toHaveFocus();
    fireEvent.keyDown(last, { key: "ArrowDown" });
    expect(last).toHaveFocus();
    fireEvent.keyDown(last, { key: "Home" });
    expect(first).toHaveFocus();
    expect(onSelect).not.toHaveBeenCalled();
    fireEvent.keyDown(second, { key: "Enter" });
    fireEvent.keyDown(last, { key: " " });
    fireEvent.click(first);
    expect(onSelect.mock.calls).toEqual([["change-uuid"], ["another-case-uuid"], ["case-uuid"]]);
  });

  it("uses selected identity as the single Tab entry and safely handles changed or stale rows", () => {
    const onSelect = vi.fn();
    const { rerender } = render(<HistoryTable rows={rows} selectedHistoryId="change-uuid" onSelect={onSelect} />);
    expect(bodyRows().map((row) => row.tabIndex)).toEqual([-1, 0, -1]);
    expect(bodyRows()[1]).toHaveAttribute("aria-selected", "true");
    rerender(<HistoryTable rows={[rows[2], rows[0]]} selectedHistoryId="stale-id" onSelect={onSelect} />);
    expect(bodyRows().map((row) => row.tabIndex)).toEqual([0, -1]);
    expect(bodyRows().every((row) => row.getAttribute("aria-selected") === "false")).toBe(true);
    bodyRows()[0].focus();
    fireEvent.keyDown(bodyRows()[0], { key: "ArrowDown" });
    expect(bodyRows()[1]).toHaveFocus();
    fireEvent.keyDown(bodyRows()[1], { key: "Escape" });
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("shows an explicit empty state without a selectable placeholder", () => {
    const onSelect = vi.fn();
    render(<HistoryTable rows={[]} selectedHistoryId="stale-id" onSelect={onSelect} />);
    expect(screen.getByText("0 sự kiện")).toBeInTheDocument();
    const emptyCell = screen.getByRole("cell");
    expect(emptyCell).toHaveAttribute("colspan", "4");
    expect(emptyCell).toHaveTextContent("Chưa có lịch sử kiểm tra hoặc thay đổi");
    fireEvent.click(emptyCell);
    expect(onSelect).not.toHaveBeenCalled();
    expect(bodyRows()[0]).not.toHaveAttribute("tabindex");
  });
});
