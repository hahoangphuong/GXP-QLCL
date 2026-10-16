import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CaseWorkspace } from "../../types";
import { CaseProcessingWorkspace } from "./CaseProcessingWorkspace";

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
    expect(container.querySelectorAll("input, textarea, .editable-detail-value")).toHaveLength(0);
    for (const key of ["F2", "Enter", "Escape"]) fireEvent.keyDown(rows[1], { key });
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
