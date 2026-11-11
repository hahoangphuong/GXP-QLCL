import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CaseWorkspace } from "../../types";
import { CaseProcessingWorkspace } from "./CaseProcessingWorkspace";
import { CaseDraftSession } from "./CaseDraftSession";

const workspace = {
  case_summary: { id: "case-uuid", site_id: "site-uuid", production_line_id: "line-uuid" },
  processing: {
    row_version: 9, assessed_on: "2026-09-01", assessor_name: "Dossier assessor",
    assessment_result: "Dossier result", notes: "Dossier draft owner",
    events: [
      { event_type: "application_submitted", occurred_at: "2026-08-01", payload: "Canonical submission" },
      { event_type: "custom_event", occurred_at: null, payload: "Raw server event" },
      { event_type: "custom_event", occurred_at: null, payload: null },
    ],
  },
} as unknown as CaseWorkspace;

afterEach(cleanup);

describe("Processing timeline presentation and ownership", () => {
  it("marks only the timeline for the legacy left-hand presentation", () => {
    const { container } = render(<CaseProcessingWorkspace caseWorkspace={workspace} onSave={vi.fn()} view="timeline" />);
    expect(container.querySelector(".processing-timeline > .processing-timeline-section")).not.toBeNull();
    expect(screen.getByRole("table", { name: "Các mốc xử lý hành chính" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Cuộn mốc xử lý hành chính" })).toHaveAttribute("tabindex", "0");
  });

  it("retains every server event in order and never converts timeline input into an assessment or outcome edit", () => {
    const save = vi.fn();
    const { container } = render(<CaseProcessingWorkspace caseWorkspace={workspace} onSave={save} view="timeline" />);
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(4);
    expect(within(rows[1]).getByText("Canonical submission")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Raw server event")).toBeInTheDocument();
    expect(rows[3]).toHaveTextContent("custom_event");
    expect(screen.queryByText("Dossier result")).not.toBeInTheDocument();
    expect(screen.queryByText("Đánh giá cuối")).not.toBeInTheDocument();
    expect(screen.queryByText("Hạn kiểm tra tuân thủ")).not.toBeInTheDocument();
    expect(container.querySelectorAll("textarea, .editable-detail-value")).toHaveLength(0);
    expect(screen.getByRole("textbox", { name: "Tìm mốc xử lý" })).toBeInTheDocument();
    expect(container.querySelectorAll("input")).toHaveLength(1);
    for (const key of ["F2", "Enter", "Escape"]) fireEvent.keyDown(rows[1], { key });
    expect(save).not.toHaveBeenCalled();
  });

  it("renders canonical plan/outcome milestones readably while preserving raw evidence", () => {
    const save = vi.fn();
    const plan = JSON.stringify({
      stage: "inspection_plan", plan_start_on: "2026-08-20", plan_end_on: null,
      planning_sheet_name: "KHKT canonical", decision_reference: "QD-21",
      decision_date: "2026-08-19", reason: "Schedule recorded", future_key: "Preserved",
    });
    const outcome = JSON.stringify({
      stage: "inspection_outcome", inspected_on: "2026-08-23",
      inspected_to_on: "2026-08-24", outcome_result: "Cần CAPA",
      minutes_recorded_on: "2026-08-25", minutes_recorded_time: "14:30",
      compliance_due_on: null,
    });
    const decision = JSON.stringify({ stage: "inspection_decision", decision_reference: "QD-21", decision_date: null });
    const value = { ...workspace, processing: { ...workspace.processing, events: [
      { event_type: "plan_created", occurred_at: "2026-08-20", payload: plan },
      { event_type: "outcome_recorded", occurred_at: "2026-08-25", payload: outcome },
      { event_type: "decision_issued", occurred_at: "2026-08-19", payload: decision },
    ] } } as CaseWorkspace;
    render(<CaseProcessingWorkspace caseWorkspace={value} onSave={save} view="timeline" />);
    const rows = screen.getAllByRole("row");
    expect(within(rows[1]).getByText(/Tên kế hoạch: KHKT canonical/)).toHaveTextContent("Từ ngày: 20-08-2026");
    expect(within(rows[1]).getByText(/Tên kế hoạch: KHKT canonical/)).toHaveTextContent("Ngày QĐKT: 19-08-2026");
    expect(within(rows[2]).getByText(/Từ ngày kiểm tra: 23-08-2026/)).toHaveTextContent("Đến ngày kiểm tra: 24-08-2026");
    expect(within(rows[2]).getByText(/Từ ngày kiểm tra: 23-08-2026/)).toHaveTextContent("Ngày biên bản: 25-08-2026");
    expect(within(rows[3]).getByText("Tham chiếu QĐKT: QD-21")).toBeInTheDocument();
    const rawDetails = screen.getAllByText("Dữ liệu sự kiện gốc");
    expect(rawDetails).toHaveLength(3);
    expect(within(rows[1]).getByText(plan)).toBeInTheDocument();
    expect(within(rows[2]).getByText(outcome)).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
  });

  it("keeps unknown, malformed and mismatched timeline payloads literal and safe", () => {
    const raw = '{"stage":"inspection_plan", "unknown": "kept"}';
    const value = { ...workspace, processing: { ...workspace.processing, events: [
      { event_type: "plan_created", occurred_at: null, payload: "not valid JSON {" },
      { event_type: "plan_created", occurred_at: null, payload: raw },
      { event_type: "outcome_recorded", occurred_at: null, payload: '{"stage":"inspection_plan","outcome_result":"Mismatched"}' },
    ] } } as CaseWorkspace;
    const save = vi.fn();
    render(<CaseProcessingWorkspace caseWorkspace={value} onSave={save} view="timeline" />);
    expect(screen.getByText("not valid JSON {")).toBeInTheDocument();
    expect(screen.getByText(raw)).toBeInTheDocument();
    expect(screen.getByText('{"stage":"inspection_plan","outcome_result":"Mismatched"}')).toBeInTheDocument();
    expect(screen.queryByText("Dữ liệu sự kiện gốc")).not.toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
  });

  it("replaces event context and shows the empty state without stale data or a mutation", () => {
    const save = vi.fn();
    const { rerender } = render(<CaseProcessingWorkspace caseWorkspace={workspace} onSave={save} view="timeline" />);
    const next = { ...workspace, case_summary: { ...workspace.case_summary, id: "other-case-uuid" }, processing: { ...workspace.processing, events: [] } };
    rerender(<CaseProcessingWorkspace caseWorkspace={next} onSave={save} view="timeline" />);
    expect(screen.getByText("Chưa có mốc xử lý")).toBeInTheDocument();
    expect(screen.queryByText("Canonical submission")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
  });
});

describe("canonical timeline operator filters", () => {
  const canonical = { ...workspace, processing: { ...workspace.processing, events: [
    { event_type: "plan_created", occurred_at: "2026-08-20", payload: JSON.stringify({ stage: "inspection_plan", planning_sheet_name: "KHKT-ABC", reason: "Lập kế hoạch" }) },
    { event_type: "outcome_recorded", occurred_at: "2026-08-25", payload: JSON.stringify({ stage: "inspection_outcome", outcome_result: "Cần CAPA" }) },
    { event_type: "plan_created", occurred_at: "2026-08-28", payload: "Dữ liệu legacy gốc" },
    { event_type: "unknown_custom", occurred_at: null, payload: "RAW-MARKER-123" },
  ] } } as CaseWorkspace;

  it("filters by actual canonical event type and raw evidence while preserving API order and no mutation", () => {
    const save = vi.fn();
    render(<CaseProcessingWorkspace caseWorkspace={canonical} onSave={save} view="timeline" />);
    expect(screen.getByRole("status")).toHaveTextContent("Hiển thị 4/4");
    fireEvent.change(screen.getByRole("combobox", { name: "Loại mốc xử lý" }), { target: { value: "plan_created" } });
    expect(screen.getByRole("status")).toHaveTextContent("Hiển thị 2/4");
    const rows = within(screen.getByRole("table", { name: "Các mốc xử lý hành chính" })).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(rows[1]).toHaveTextContent("KHKT-ABC");
    expect(rows[2]).toHaveTextContent("Dữ liệu legacy gốc");
    fireEvent.change(screen.getByRole("textbox", { name: "Tìm mốc xử lý" }), { target: { value: "legacy GỐC" } });
    expect(screen.getByRole("status")).toHaveTextContent("Hiển thị 1/4");
    expect(screen.getByText("Dữ liệu legacy gốc")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Xóa bộ lọc mốc" }));
    expect(screen.getByRole("status")).toHaveTextContent("Hiển thị 4/4");
    fireEvent.change(screen.getByRole("textbox", { name: "Tìm mốc xử lý" }), { target: { value: "RAW-MARKER-123" } });
    expect(screen.getByText("RAW-MARKER-123")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Hiển thị 1/4");
    expect(save).not.toHaveBeenCalled();
  });

  it("retains in-session filters across timeline remount but not another Case and never shows old Case events", () => {
    const save = vi.fn();
    const editor = (id: string, show = true) => <CaseDraftSession identity={id}>
      {show ? <CaseProcessingWorkspace caseWorkspace={{ ...canonical, case_summary: { ...canonical.case_summary, id } }} onSave={save} view="timeline" /> : null}
    </CaseDraftSession>;
    const view = render(editor("case-A"));
    fireEvent.change(screen.getByRole("combobox", { name: "Loại mốc xử lý" }), { target: { value: "unknown_custom" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Tìm mốc xử lý" }), { target: { value: "RAW-MARKER" } });
    view.rerender(editor("case-A", false));
    view.rerender(editor("case-A"));
    expect(screen.getByRole("combobox", { name: "Loại mốc xử lý" })).toHaveValue("unknown_custom");
    expect(screen.getByRole("textbox", { name: "Tìm mốc xử lý" })).toHaveValue("RAW-MARKER");
    view.rerender(<CaseDraftSession identity="case-B"><CaseProcessingWorkspace
      caseWorkspace={{ ...canonical, case_summary: { ...canonical.case_summary, id: "case-B" }, processing: { ...canonical.processing, events: [
        { event_type: "other-B", occurred_at: null, payload: "B only" },
      ] } }} onSave={save} view="timeline" /></CaseDraftSession>);
    expect(screen.getByRole("combobox", { name: "Loại mốc xử lý" })).toHaveValue("all");
    expect(screen.getByRole("textbox", { name: "Tìm mốc xử lý" })).toHaveValue("");
    expect(screen.getByText("B only")).toBeInTheDocument();
    expect(screen.queryByText("RAW-MARKER-123")).not.toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
  });

  it("keeps a stale type filter fail-closed after canonical refresh and offers explicit reset", () => {
    const save = vi.fn();
    const view = render(<CaseProcessingWorkspace caseWorkspace={canonical} onSave={save} view="timeline" />);
    fireEvent.change(screen.getByRole("combobox", { name: "Loại mốc xử lý" }), { target: { value: "plan_created" } });
    view.rerender(<CaseProcessingWorkspace caseWorkspace={{ ...canonical, processing: { ...canonical.processing, events: [
      { event_type: "new_event", occurred_at: "2026-11-11", payload: "New canonical event" },
    ] } }} onSave={save} view="timeline" />);
    expect(screen.queryByRole("table", { name: "Các mốc xử lý hành chính" })).not.toBeInTheDocument();
    expect(screen.getByText(/Không có mốc xử lý phù hợp/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Xóa bộ lọc mốc" }));
    expect(screen.getByText("New canonical event")).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();
  });
});
