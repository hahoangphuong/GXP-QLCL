import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CaseWorkspaceRemediationCycle } from "../../types";
import { CapaCycleComparison } from "./CapaCycleComparison";

function cycle(id: string, round_no: number, status: string, notes: string): CaseWorkspaceRemediationCycle {
  return {
    capa_cycle_id: id, row_version: round_no, round_no,
    incoming_reference: `CV-${round_no}`, requested_on: "2026-11-01",
    submitted_on: "2026-11-02", assessed_on: "2026-11-03",
    assessor_name: "Người thẩm định", result: status === "accepted" ? "accepted" : "rejected",
    status, notes,
  } as CaseWorkspaceRemediationCycle;
}

describe("canonical CAPA round comparison", () => {
  const rounds = [
    cycle("uuid-A", 1, "rejected", "Thiếu hồ sơ công đoạn"),
    cycle("uuid-B", 2, "rejected", "Cần bổ sung chứng cứ"),
    cycle("uuid-C", 3, "accepted", "Đã khắc phục đạt"),
  ];

  it("compares persisted rejected and accepted rounds by UUID, including textual evidence and differences", () => {
    render(<CapaCycleComparison cycles={rounds} />);
    fireEvent.click(screen.getByText("So sánh hai vòng khắc phục"));
    expect(screen.getByLabelText("Vòng khắc phục thứ nhất")).toHaveValue("uuid-B");
    expect(screen.getByLabelText("Vòng khắc phục thứ hai")).toHaveValue("uuid-C");
    const table = screen.getByRole("table", { name: "Đối chiếu dữ liệu hai vòng CAPA" });
    expect(within(table).getByRole("columnheader", { name: "Vòng 2" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Vòng 3" })).toBeInTheDocument();
    expect(within(table).getByText("Cần bổ sung chứng cứ")).toBeInTheDocument();
    expect(within(table).getByText("Đã khắc phục đạt")).toBeInTheDocument();
    const notesRow = within(table).getByRole("rowheader", { name: "Ghi chú" }).closest("tr")!;
    expect(notesRow).toHaveTextContent("Khác nhau");
    const datesRow = within(table).getByRole("rowheader", { name: "Ngày yêu cầu" }).closest("tr")!;
    expect(datesRow).toHaveTextContent("Không đổi");
  });

  it("maintains selected canonical UUID through reordered server rows, not round number or array index", () => {
    const view = render(<CapaCycleComparison cycles={rounds} />);
    fireEvent.click(screen.getByText("So sánh hai vòng khắc phục"));
    fireEvent.change(screen.getByLabelText("Vòng khắc phục thứ nhất"), { target: { value: "uuid-A" } });
    view.rerender(<CapaCycleComparison cycles={[rounds[2], rounds[0], rounds[1]]} />);
    expect(screen.getByLabelText("Vòng khắc phục thứ nhất")).toHaveValue("uuid-A");
    expect(screen.getByLabelText("Vòng khắc phục thứ hai")).toHaveValue("uuid-C");
    expect(screen.getByRole("table", { name: "Đối chiếu dữ liệu hai vòng CAPA" })).toHaveTextContent("Thiếu hồ sơ công đoạn");
  });

  it("fails closed on same-round selection and missing previous UUID after refresh", () => {
    const view = render(<CapaCycleComparison cycles={rounds} />);
    fireEvent.click(screen.getByText("So sánh hai vòng khắc phục"));
    fireEvent.change(screen.getByLabelText("Vòng khắc phục thứ nhất"), { target: { value: "uuid-C" } });
    expect(screen.getByRole("status")).toHaveTextContent("Chọn hai vòng khắc phục khác nhau");
    expect(screen.queryByRole("table", { name: "Đối chiếu dữ liệu hai vòng CAPA" })).not.toBeInTheDocument();
    view.rerender(<CapaCycleComparison cycles={[rounds[0], rounds[1]]} />);
    expect(screen.getByLabelText("Vòng khắc phục thứ nhất")).toHaveValue("uuid-A");
    expect(screen.getByLabelText("Vòng khắc phục thứ hai")).toHaveValue("uuid-B");
    expect(screen.getByRole("table", { name: "Đối chiếu dữ liệu hai vòng CAPA" })).not.toHaveTextContent("Đã khắc phục đạt");
  });

  it("renders no compare control when zero or one CAPA cycles exist", () => {
    const view = render(<CapaCycleComparison cycles={[]} />);
    expect(screen.queryByText("So sánh hai vòng khắc phục")).not.toBeInTheDocument();
    view.rerender(<CapaCycleComparison cycles={rounds.slice(0, 1)} />);
    expect(screen.queryByText("So sánh hai vòng khắc phục")).not.toBeInTheDocument();
  });
});
