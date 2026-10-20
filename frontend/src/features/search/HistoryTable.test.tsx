import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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

function focus(element: HTMLElement) {
  act(() => element.focus());
}

describe("HistoryTable", () => {
  it("shows the original three columns while retaining authoritative states on accessible row labels and titles", () => {
    render(<HistoryTable rows={rows} selectedHistoryId="case-uuid" onSelect={vi.fn()} />);
    expect(screen.getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Loại", "Tiêu chuẩn", "Ngày"]);
    const tableRows = bodyRows();
    expect(tableRows[0]).toHaveAttribute("title", "Chờ cấp chứng nhận");
    expect(within(tableRows[0]).getByText("04-09-2026")).toBeInTheDocument();
    expect(within(tableRows[1]).getByText("Thay đổi")).toHaveAttribute("title", "Thay đổi cơ sở");
    expect(within(tableRows[1]).getByText(rows[1].standard!)).toHaveAttribute("title", rows[1].standard);
    expect(tableRows[1]).toHaveAttribute("aria-label", expect.stringContaining("Đang xem xét"));
    expect(tableRows[2]).toHaveAttribute("title", "future_backend_state");
    expect(within(tableRows[2]).getAllByText("Chưa có")).toHaveLength(2);
    expect(screen.queryByText("KT-01")).not.toBeInTheDocument();
  });

  it("moves focus with arrows and Home/End without changing selection, then activates exact IDs", () => {
    const onSelect = vi.fn();
    render(<HistoryTable rows={rows} selectedHistoryId="case-uuid" onSelect={onSelect} />);
    const [first, second, last] = bodyRows();
    focus(first);
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
    focus(bodyRows()[0]);
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
    expect(emptyCell).toHaveAttribute("colspan", "3");
    expect(emptyCell).toHaveTextContent("Chưa có lịch sử kiểm tra hoặc thay đổi");
    fireEvent.click(emptyCell);
    expect(onSelect).not.toHaveBeenCalled();
    expect(bodyRows()[0]).not.toHaveAttribute("tabindex");
  });

  it("keeps a surviving focused event as the sole Tab stop through append and reorder", () => {
    const onSelect = vi.fn();
    const { rerender } = render(<HistoryTable rows={rows} selectedHistoryId="case-uuid" onSelect={onSelect} />);
    let renderedRows = bodyRows();
    focus(renderedRows[0]);
    fireEvent.keyDown(renderedRows[0], { key: "ArrowDown" });
    expect(renderedRows[1]).toHaveFocus();

    rerender(<HistoryTable rows={[rows[2], rows[1], rows[0], { ...rows[0], id: "appended-uuid" }]} selectedHistoryId="case-uuid" onSelect={onSelect} />);
    renderedRows = bodyRows();
    expect(renderedRows[1]).toHaveFocus();
    expect(renderedRows.map((row) => row.tabIndex)).toEqual([-1, 0, -1, -1]);
    expect(renderedRows[2]).toHaveAttribute("aria-selected", "true");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("moves focus to the nearest surviving event without selecting it when the focused event disappears", () => {
    const onSelect = vi.fn();
    const { rerender } = render(<HistoryTable rows={rows} selectedHistoryId="case-uuid" onSelect={onSelect} />);
    let renderedRows = bodyRows();
    focus(renderedRows[1]);

    rerender(<HistoryTable rows={[rows[0], rows[2]]} selectedHistoryId="case-uuid" onSelect={onSelect} />);
    renderedRows = bodyRows();
    expect(renderedRows[1]).toHaveFocus();
    expect(renderedRows.map((row) => row.tabIndex)).toEqual([-1, 0]);
    expect(renderedRows[0]).toHaveAttribute("aria-selected", "true");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("does not steal focus from another control when an earlier focused event disappears", () => {
    const onSelect = vi.fn();
    const { rerender } = render(<div><button type="button">Ngoài lịch sử</button><HistoryTable rows={rows} selectedHistoryId="case-uuid" onSelect={onSelect} /></div>);
    focus(bodyRows()[1]);
    const outside = screen.getByRole("button", { name: "Ngoài lịch sử" });
    focus(outside);

    rerender(<div><button type="button">Ngoài lịch sử</button><HistoryTable rows={[rows[0], rows[2]]} selectedHistoryId="case-uuid" onSelect={onSelect} /></div>);
    expect(outside).toHaveFocus();
    expect(bodyRows().map((row) => row.tabIndex)).toEqual([0, -1]);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("keeps focus in the named history region when focused data becomes empty", () => {
    const onSelect = vi.fn();
    const { rerender } = render(<HistoryTable rows={rows} selectedHistoryId="case-uuid" onSelect={onSelect} />);
    focus(bodyRows()[1]);

    rerender(<HistoryTable rows={[]} selectedHistoryId={null} onSelect={onSelect} />);
    expect(screen.getByRole("region", { name: "Danh sách lịch sử kiểm tra và thay đổi" })).toHaveFocus();
    expect(onSelect).not.toHaveBeenCalled();
  });
});
