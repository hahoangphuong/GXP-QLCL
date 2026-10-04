import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CaseWorkspace, CaseWorkspaceRemediationCycle, LifecycleActionReadiness } from "../../types";
import { CaseRemediationWorkspace } from "./CaseRemediationWorkspace";

function cycle(overrides: Partial<CaseWorkspaceRemediationCycle> = {}): CaseWorkspaceRemediationCycle {
  return {
    capa_cycle_id: "capa-1",
    row_version: 2,
    round_no: 1,
    requested_on: "2026-09-01",
    incoming_reference: "CV-01",
    submitted_on: null,
    assessed_on: null,
    assessor_name: null,
    result: null,
    status: "requested",
    notes: "Ghi chú từ máy chủ",
    ...overrides,
  };
}

function action(actionKey: string, available = true, expectedVersion: number | null = 2): LifecycleActionReadiness {
  return {
    action_key: actionKey,
    label: actionKey,
    available,
    reason_code: available ? null : "missing_permission",
    required_permissions: ["capa.edit"],
    expected_version: expectedVersion,
  };
}

function workspace(
  cycles: CaseWorkspaceRemediationCycle[] = [cycle()],
  actions: LifecycleActionReadiness[] = [],
): CaseWorkspace {
  return {
    case_summary: { id: "case-1", row_version: 8, legacy_inspection_id: 1, legacy_inspection_code: "KT-1", site_id: "site-1", legacy_site_id: 1, facility_name: "Cơ sở A", company_name: "Công ty A", gxp_type: "GMP", scope_code: null, production_line_id: null, production_line_code: null, production_line_identity_state: "canonical", applicable_standard: null, inspection_type: "Tái", state: "inspection_completed", opened_year: 2026 },
    remediation: { cycles, actions },
  } as unknown as CaseWorkspace;
}

function renderWorkspace(
  caseWorkspace = workspace(),
  selectedCycleId: string | null = "capa-1",
) {
  const handlers = {
    onSelectedCycleChange: vi.fn(),
    onCreateCycle: vi.fn().mockResolvedValue(undefined),
    onUpdateCycle: vi.fn().mockResolvedValue(undefined),
    onSubmitCycle: vi.fn().mockResolvedValue(undefined),
    onAssessCycle: vi.fn().mockResolvedValue(undefined),
  };
  return {
    ...render(<CaseRemediationWorkspace caseWorkspace={caseWorkspace} selectedCycleId={selectedCycleId} {...handlers} />),
    handlers,
  };
}

describe("CaseRemediationWorkspace backend-owned lifecycle actions", () => {
  it("exposes create, update, submit, and assess only from matching backend readiness", async () => {
    const initial = workspace(
      [cycle()],
      [
        action("create_capa_cycle", true, 8),
        action("update_capa_cycle:capa-1"),
        action("submit_capa_cycle:capa-1"),
        action("assess_capa_cycle:capa-1"),
      ],
    );
    const first = renderWorkspace(initial);

    fireEvent.click(screen.getByRole("button", { name: "Thêm vòng khắc phục" }));
    fireEvent.change(screen.getByLabelText("Ngày yêu cầu"), { target: { value: "2026-09-02" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo vòng khắc phục" }));
    await waitFor(() => expect(first.handlers.onCreateCycle).toHaveBeenCalledWith({ expected_case_version: 8, incoming_reference: null, requested_on: "2026-09-02", notes: null }));

    // Re-render the selected cycle after a successful create so its lifecycle controls are visible.
    // The server-owned actions, not local status text, decide availability.
    first.unmount();
    const ready = renderWorkspace(initial);
    fireEvent.doubleClick(ready.getByRole("button", { name: "Sửa Ghi chú" }));
    fireEvent.change(ready.getByLabelText("Ghi chú khắc phục"), { target: { value: "Đã cập nhật" } });
    fireEvent.click(ready.getByRole("button", { name: "Lưu Ghi chú" }));
    await waitFor(() => expect(ready.handlers.onUpdateCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({ expected_version: 2, notes: "Đã cập nhật" })));
    await waitFor(() => expect(ready.queryByRole("button", { name: "Lưu Ghi chú" })).not.toBeInTheDocument());

    fireEvent.change(ready.getByLabelText("Ngày ghi nhận tiếp nhận"), { target: { value: "2026-09-05" } });
    expect(ready.getByRole("button", { name: "Ghi nhận tiếp nhận" })).toBeEnabled();
    fireEvent.click(ready.getByRole("button", { name: "Ghi nhận tiếp nhận" }));
    await waitFor(() => expect(ready.handlers.onSubmitCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({ expected_version: 2, submitted_on: "2026-09-05" })));

    fireEvent.change(ready.getByLabelText("Ngày đánh giá khắc phục"), { target: { value: "2026-09-06" } });
    fireEvent.change(ready.getByLabelText("Kết quả đánh giá khắc phục"), { target: { value: "Đạt" } });
    fireEvent.click(ready.getByRole("button", { name: "Đánh giá" }));
    await waitFor(() => expect(ready.handlers.onAssessCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({ expected_version: 2, assessed_on: "2026-09-06", result: "Đạt" })));
  });

  it("fails closed when readiness is missing or unavailable and never invokes a lifecycle mutation", () => {
    const { handlers } = renderWorkspace(
      workspace([cycle()], [action("create_capa_cycle", false), action("submit_capa_cycle:capa-1", false), action("assess_capa_cycle:capa-1", false)]),
    );

    expect(screen.queryByRole("button", { name: "Thêm vòng khắc phục" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ghi nhận tiếp nhận" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Đánh giá" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Ngày ghi nhận tiếp nhận")).not.toBeInTheDocument();
    expect(handlers.onCreateCycle).not.toHaveBeenCalled();
    expect(handlers.onSubmitCycle).not.toHaveBeenCalled();
    expect(handlers.onAssessCycle).not.toHaveBeenCalled();
  });

  it("keeps submit and assess drafts across a same-version refetch before invoking the selected cycle actions", async () => {
    const actions = [action("submit_capa_cycle:capa-1"), action("assess_capa_cycle:capa-1")];
    const initial = workspace([cycle({ notes: "Ghi chú ban đầu" })], actions);
    const view = renderWorkspace(initial);

    fireEvent.change(screen.getByLabelText("Ngày ghi nhận tiếp nhận"), { target: { value: "2026-09-05" } });
    fireEvent.change(screen.getByLabelText("Ngày đánh giá khắc phục"), { target: { value: "2026-09-06" } });
    fireEvent.change(screen.getByLabelText("Kết quả đánh giá khắc phục"), { target: { value: "Đạt" } });
    fireEvent.change(screen.getByLabelText("Ghi chú thao tác khắc phục"), { target: { value: "Bản nháp của người dùng" } });

    view.rerender(
      <CaseRemediationWorkspace
        caseWorkspace={workspace([cycle({ notes: "Giá trị refetch cùng version" })], actions)}
        selectedCycleId="capa-1"
        {...view.handlers}
      />,
    );
    expect(screen.getByLabelText("Ngày ghi nhận tiếp nhận")).toHaveValue("2026-09-05");
    expect(screen.getByLabelText("Ngày đánh giá khắc phục")).toHaveValue("2026-09-06");
    expect(screen.getByLabelText("Kết quả đánh giá khắc phục")).toHaveValue("Đạt");
    expect(screen.getByLabelText("Ghi chú thao tác khắc phục")).toHaveValue("Bản nháp của người dùng");
    expect(screen.getByRole("button", { name: "Ghi nhận tiếp nhận" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Đánh giá" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Ghi nhận tiếp nhận" }));
    await waitFor(() => expect(view.handlers.onSubmitCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({ expected_version: 2, submitted_on: "2026-09-05", notes: "Bản nháp của người dùng" })));
    await waitFor(() => expect(screen.getByRole("button", { name: "Đánh giá" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Đánh giá" }));
    await waitFor(() => expect(view.handlers.onAssessCycle).toHaveBeenCalledWith("capa-1", expect.objectContaining({ expected_version: 2, assessed_on: "2026-09-06", result: "Đạt", notes: "Bản nháp của người dùng" })));
  });

  it("rehydrates on an intentional selected-cycle change and never carries cycle A input to cycle B", () => {
    const first = cycle({ capa_cycle_id: "capa-1", submitted_on: null });
    const second = cycle({ capa_cycle_id: "capa-2", row_version: 4, round_no: 2, submitted_on: "2026-09-08", notes: "Cycle B" });
    const view = renderWorkspace(
      workspace([first, second], [action("submit_capa_cycle:capa-1"), action("submit_capa_cycle:capa-2", true, 4)]),
      "capa-1",
    );
    fireEvent.change(screen.getByLabelText("Ngày ghi nhận tiếp nhận"), { target: { value: "2026-09-05" } });

    view.rerender(
      <CaseRemediationWorkspace
        caseWorkspace={workspace([first, second], [action("submit_capa_cycle:capa-1"), action("submit_capa_cycle:capa-2", true, 4)])}
        selectedCycleId="capa-2"
        {...view.handlers}
      />,
    );
    expect(screen.getByRole("heading", { name: "Chi tiết vòng khắc phục 2" })).toBeInTheDocument();
    expect(screen.getByLabelText("Ngày ghi nhận tiếp nhận")).toHaveValue("2026-09-08");
  });

  it("rehydrates command input after a successful mutation returns a newer server version", async () => {
    const view = renderWorkspace(workspace([cycle()], [action("submit_capa_cycle:capa-1")]));
    fireEvent.change(screen.getByLabelText("Ngày ghi nhận tiếp nhận"), { target: { value: "2026-09-05" } });
    fireEvent.click(screen.getByRole("button", { name: "Ghi nhận tiếp nhận" }));
    await waitFor(() => expect(view.handlers.onSubmitCycle).toHaveBeenCalledOnce());

    view.rerender(
      <CaseRemediationWorkspace
        caseWorkspace={workspace([cycle({ row_version: 3, submitted_on: "2026-09-05", notes: "Đã được server ghi nhận" })], [action("assess_capa_cycle:capa-1", true, 3)])}
        selectedCycleId="capa-1"
        {...view.handlers}
      />,
    );
    expect(screen.getByLabelText("Ngày ghi nhận tiếp nhận")).toHaveValue("2026-09-05");
    expect(screen.getByLabelText("Ghi chú thao tác khắc phục")).toHaveValue("Đã được server ghi nhận");
    expect(screen.queryByRole("button", { name: "Ghi nhận tiếp nhận" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đánh giá" })).toBeInTheDocument();
  });
});
