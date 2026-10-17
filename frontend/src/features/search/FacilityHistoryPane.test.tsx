import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FacilityHistoryPane } from "./FacilityHistoryPane";
import type { FacilityHistoryItem } from "../../types";

afterEach(cleanup);
const row: FacilityHistoryItem = { id: "case-1", source_type: "case", reference_code: null, event_type: "Định kỳ", gxp_type: "GMP", standard: "WHO-GMP", occurred_on: null, state: "planned" };
const props = { rows: [row], selectedHistoryId: "case-1", onSelect: vi.fn(), loading: false, error: null, hasSelection: true };

describe("FacilityHistoryPane", () => {
  it("hides stale history while the selected context is loading", () => {
    render(<FacilityHistoryPane {...props} loading />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Đang tải lịch sử");
    expect(screen.getByRole("region")).toHaveAttribute("aria-busy", "true");
  });

  it("surfaces API or deep-link errors without rendering old rows or fake empty history", () => {
    render(<FacilityHistoryPane {...props} loading error="Không có quyền truy cập ngữ cảnh" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Không có quyền truy cập ngữ cảnh");
    expect(screen.getByRole("region")).toHaveAttribute("aria-busy", "false");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText(/Chưa có lịch sử/)).not.toBeInTheDocument();
  });

  it("prompts for selection rather than presenting another facility's retained history", () => {
    render(<FacilityHistoryPane {...props} hasSelection={false} />);
    expect(screen.getByRole("status")).toHaveTextContent("Chọn cơ sở hoặc dây chuyền");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders exactly one table including a genuine empty history after loading completes", () => {
    const { rerender } = render(<FacilityHistoryPane {...props} />);
    expect(screen.getAllByRole("table")).toHaveLength(1);
    expect(screen.getByText("WHO-GMP")).toBeInTheDocument();
    rerender(<FacilityHistoryPane {...props} rows={[]} selectedHistoryId={null} />);
    expect(screen.getAllByRole("table")).toHaveLength(1);
    expect(screen.getByText(/Chưa có lịch sử kiểm tra hoặc thay đổi/)).toBeInTheDocument();
  });
});
