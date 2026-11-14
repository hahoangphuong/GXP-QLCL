import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getSite: vi.fn(), getCompany: vi.fn(), listSiteProductionLines: vi.fn(),
  getFacilityWorkspace: vi.fn(), createInitialCase: vi.fn(), getCaseDetail: vi.fn(),
}));
vi.mock("../../lib/api", () => api);

import { CatalogCreateSessionRoot } from "./CatalogCreateSession";
import { InitialCaseCreationDialog, exactInitialCaseReadback } from "./InitialCaseCreationDialog";
import type { CaseDetail } from "../../types";

const auth = { username: "inspector", role: "admin" as const };
const site = { id: "site-A", company_id: "company-A", site_name: "Nhà máy A", site_address: "Hà Nội" };
const company = { id: "company-A", legal_name: "Công ty A", is_inactive: false };
const line = { id: "line-A", site_id: "site-A", code: "A", effective_from: "2026-01-01", effective_to: null, row_version: 1 };
const ready = { action_key: "create_initial_case", readiness_status: "available", label: "Hồ sơ mới", detail: "Được tạo Case Draft", required_permissions: ["case.edit"] };
const caseRow: CaseDetail = {
  id: "case-uuid", site_id: "site-A", gxp_type: "GMP",
  production_line_id: null, scope_code: null, applicable_standard: "WHO-GMP", inspection_type: "Mới",
  state: "draft", opened_year: null, legacy_inspection_id: null, legacy_inspection_code: null,
};
const props = { siteId: "site-A", open: true, auth, useStubAuth: true, accessGeneration: 1, onClose: vi.fn(), onVerifiedOpen: vi.fn() };

function view(overrides: Partial<typeof props> = {}) {
  return render(<CatalogCreateSessionRoot><InitialCaseCreationDialog {...props} {...overrides} /></CatalogCreateSessionRoot>);
}
async function fill() {
  fireEvent.change(screen.getByLabelText("Loại GxP cho hồ sơ mới"), { target: { value: "GMP" } });
  await waitFor(() => expect(api.getFacilityWorkspace).toHaveBeenCalled());
  await fillDraft();
}
async function fillDraft() {
  fireEvent.change(screen.getByLabelText("Loại kiểm tra hồ sơ đầu tiên"), { target: { value: "Mới" } });
  fireEvent.change(screen.getByLabelText("Tiêu chuẩn áp dụng"), { target: { value: "WHO-GMP" } });
  fireEvent.change(screen.getByLabelText("Lý do tạo hồ sơ đầu tiên"), { target: { value: "Hồ sơ GMP đầu tiên" } });
  fireEvent.click(screen.getByLabelText("Xác nhận chỉ tạo Case Draft"));
  await waitFor(() => expect((screen.getByRole("button", { name: "Tạo hồ sơ Draft" }) as HTMLButtonElement).disabled).toBe(false));
}

beforeEach(() => {
  // Each Vitest scenario gets an independent tab journal, as a new browser tab would.
  window.sessionStorage.clear();
  vi.restoreAllMocks();
  vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "case-uuid") });
  api.getSite.mockResolvedValue(site);
  api.getCompany.mockResolvedValue(company);
  api.listSiteProductionLines.mockResolvedValue([line]);
  api.getFacilityWorkspace.mockImplementation((siteId: string, _a: unknown, _stub: unknown, gxp: string, _code: unknown, _bearer: unknown, lineId: string | null) => Promise.resolve({
    summary: { site_id: siteId, selected_gxp_type: gxp, selected_production_line_id: lineId },
    action_readiness: [ready],
    history: [],
  }));
  api.createInitialCase.mockResolvedValue({ case_id: "case-uuid" });
  api.getCaseDetail.mockResolvedValue(caseRow);
});

describe("InitialCaseCreationDialog", () => {
  it("POSTs once with canonical Case UUID and verifies Draft without inferred dossier/GCN", async () => {
    const onVerifiedOpen = vi.fn();
    view({ onVerifiedOpen });
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Tạo hồ sơ Draft" }));
    await screen.findByText(/Case nháp canonical đã xác minh/);
    expect(api.createInitialCase).toHaveBeenCalledTimes(1);
    expect(api.createInitialCase).toHaveBeenCalledWith("site-A", {
      case_id: "case-uuid", gxp_type: "GMP", production_line_id: null,
      inspection_type: "Mới", applicable_standard: "WHO-GMP", reason: "Hồ sơ GMP đầu tiên",
    }, auth, true, undefined);
    expect(api.getCaseDetail).toHaveBeenCalledWith("case-uuid", auth, true, undefined);
    expect(onVerifiedOpen).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Mở Case workspace" }));
    expect(onVerifiedOpen).toHaveBeenCalledWith("case-uuid");
  });

  it("does not reuse readiness from GMP when operator selects GLP before its GET resolves", async () => {
    let releaseGlp!: (value: unknown) => void;
    api.getFacilityWorkspace.mockImplementation((_site: string, _a: unknown, _stub: unknown, gxpType: string) => {
      if (gxpType === "GLP") return new Promise((resolve) => { releaseGlp = resolve; });
      return Promise.resolve({
        summary: { site_id: "site-A", selected_gxp_type: "GMP", selected_production_line_id: null },
        action_readiness: [ready], history: [],
      });
    });
    view();
    await fill();
    fireEvent.change(screen.getByLabelText("Loại GxP cho hồ sơ mới"), { target: { value: "GLP" } });
    const submit = screen.getByRole("button", { name: "Tạo hồ sơ Draft" }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.submit(screen.getByLabelText("Loại kiểm tra hồ sơ đầu tiên").closest("form")!);
    expect(api.createInitialCase).not.toHaveBeenCalled();
    await act(async () => { releaseGlp({
      summary: { site_id: "site-A", selected_gxp_type: "GLP", selected_production_line_id: null },
      action_readiness: [{ ...ready, readiness_status: "conflict" }], history: [],
    }); });
    expect(submit.disabled).toBe(true);
    expect(api.createInitialCase).not.toHaveBeenCalled();
  });

  it("rechecks server readiness before admitting a successor in an occupied Site/GxP context", async () => {
    view(); await fill();
    fireEvent.click(screen.getByRole("button", { name: "Tạo hồ sơ Draft" }));
    await screen.findByText(/Case nháp canonical đã xác minh/);
    api.getFacilityWorkspace.mockResolvedValue({
      summary: { site_id: "site-A", selected_gxp_type: "GMP", selected_production_line_id: null },
      action_readiness: [{ ...ready, readiness_status: "conflict", detail: "Case đã tồn tại" }], history: [],
    });
    fireEvent.click(screen.getByRole("button", { name: "Tạo intent mới" }));
    await screen.findByText(/Case đã tồn tại/);
    expect((screen.getByRole("button", { name: "Tạo hồ sơ Draft" }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.createInitialCase).toHaveBeenCalledTimes(1);
  });

  it("admits synchronous duplicate submit only once", async () => {
    let release!: (value: unknown) => void;
    api.createInitialCase.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    view();
    await fill();
    const form = screen.getByLabelText("Loại kiểm tra hồ sơ đầu tiên").closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(api.createInitialCase).toHaveBeenCalledTimes(1);
    expect(crypto.randomUUID).toHaveBeenCalledTimes(1);
    await act(async () => { release({ case_id: "case-uuid" }); });
    await screen.findByText(/Case nháp canonical đã xác minh/);
  });

  it("never downgrades verified Draft Case after an older concurrent GET fails", async () => {
    let succeed!: (row: CaseDetail) => void;
    let fail!: (error: Error) => void;
    api.getCaseDetail.mockRejectedValueOnce(new Error("initial readback unreachable"))
      .mockImplementationOnce(() => new Promise((resolve) => { succeed = resolve; }))
      .mockImplementationOnce(() => new Promise((_, reject) => { fail = reject; }));
    view(); await fill();
    fireEvent.click(screen.getByRole("button", { name: "Tạo hồ sơ Draft" }));
    await screen.findByText(/Chưa xác minh:/);
    const retry = screen.getByRole("button", { name: "Đọc lại Case canonical" });
    fireEvent.click(retry);
    fireEvent.click(retry);
    await waitFor(() => expect(api.getCaseDetail).toHaveBeenCalledTimes(3));
    await act(async () => { succeed(caseRow); });
    await screen.findByText(/Case nháp canonical đã xác minh/);
    await act(async () => { fail(new Error("late readback failure")); });
    expect(screen.getByText(/Case nháp canonical đã xác minh/).textContent).toContain("case-uuid");
    expect(screen.queryByText(/Chưa xác minh:/)).toBeNull();
    expect(screen.getByRole("button", { name: "Mở Case workspace" })).toBeDefined();
    expect(api.createInitialCase).toHaveBeenCalledTimes(1);
  });

  it("keeps UUID locked after unknown POST and only retries canonical GET", async () => {
    api.createInitialCase.mockRejectedValueOnce(new Error("offline"));
    api.getCaseDetail.mockRejectedValueOnce(new Error("GET timeout")).mockResolvedValueOnce(caseRow);
    view();
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Tạo hồ sơ Draft" }));
    await screen.findByRole("alert");
    expect((screen.getByRole("button", { name: "Đã khóa intent" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Đọc lại Case canonical" }));
    await screen.findByText(/Case nháp canonical đã xác minh/);
    expect(api.createInitialCase).toHaveBeenCalledTimes(1);
    expect(api.getCaseDetail).toHaveBeenCalledTimes(2);
  });

  it("selects physical line only by Site-scoped canonical UUID and checks exact GET", async () => {
    api.getCaseDetail.mockResolvedValue({ ...caseRow, production_line_id: "line-A", scope_code: "A", production_line_identity_state: "canonical" });
    view();
    await fill();
    fireEvent.change(screen.getByLabelText("ProductionLine UUID"), { target: { value: "line-A" } });
    await waitFor(() => expect(api.getFacilityWorkspace).toHaveBeenCalledWith("site-A", auth, true, "GMP", null, undefined, "line-A"));
    // A physical-line UUID is a distinct canonical owner, with its own draft.
    await fillDraft();
    fireEvent.click(screen.getByRole("button", { name: "Tạo hồ sơ Draft" }));
    await screen.findByText(/Case nháp canonical đã xác minh/);
    expect(api.createInitialCase.mock.calls[0][1].production_line_id).toBe("line-A");
  });

  it.each([
    ["wrong UUID", { id: "other-case" }],
    ["wrong Site", { site_id: "site-B" }],
    ["wrong GxP", { gxp_type: "GLP" }],
    ["wrong line", { production_line_id: "line-A" }],
    ["wrong state", { state: "closed" }],
    ["wrong standard", { applicable_standard: "PIC/S" }],
    ["legacy ownership", { legacy_inspection_id: 1 }],
  ])("does not verify %s from canonical GET", async (_name, change) => {
    api.getCaseDetail.mockResolvedValue({ ...caseRow, ...change });
    view(); await fill();
    fireEvent.click(screen.getByRole("button", { name: "Tạo hồ sơ Draft" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Canonical Case GET sai");
    expect(api.createInitialCase).toHaveBeenCalledTimes(1);
  });

  it("rejects blocked backend readiness, inactive Company and Tái without POST", async () => {
    api.getFacilityWorkspace.mockResolvedValue({ summary: { site_id: "site-A", selected_gxp_type: "GMP", selected_production_line_id: null }, history: [], action_readiness: [{ ...ready, readiness_status: "conflict", detail: "Đã có GCN" }] });
    view();
    fireEvent.change(screen.getByLabelText("Loại GxP cho hồ sơ mới"), { target: { value: "GMP" } });
    await screen.findByText(/Đã có GCN/);
    fireEvent.change(screen.getByLabelText("Loại kiểm tra hồ sơ đầu tiên"), { target: { value: "Tái" } });
    expect((screen.getByRole("button", { name: "Tạo hồ sơ Draft" }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.createInitialCase).not.toHaveBeenCalled();
  });

  it("retains an unverified intent on Site A→B→A, without POST replay", async () => {
    api.getCaseDetail.mockRejectedValue(new Error("offline"));
    const rendered = view(); await fill();
    fireEvent.click(screen.getByRole("button", { name: "Tạo hồ sơ Draft" }));
    await screen.findByRole("alert");
    rendered.rerender(<CatalogCreateSessionRoot><InitialCaseCreationDialog {...props} siteId="site-B" /></CatalogCreateSessionRoot>);
    rendered.rerender(<CatalogCreateSessionRoot><InitialCaseCreationDialog {...props} siteId="site-A" /></CatalogCreateSessionRoot>);
    expect((screen.getByRole("button", { name: "Đã khóa intent" }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.createInitialCase).toHaveBeenCalledTimes(1);
  });

  it("restores Site-scoped GxP/line selection after actual dialog unmount within the same App session", async () => {
    const rendered = view();
    await screen.findByText(/Cơ sở:/);
    fireEvent.change(screen.getByLabelText("Loại GxP cho hồ sơ mới"), { target: { value: "GLP" } });
    fireEvent.change(screen.getByLabelText("ProductionLine UUID"), { target: { value: "line-A" } });
    await waitFor(() => expect(api.getFacilityWorkspace).toHaveBeenCalledWith(
      "site-A", auth, true, "GLP", null, undefined, "line-A",
    ));
    rendered.rerender(<CatalogCreateSessionRoot><div>Trang khác</div></CatalogCreateSessionRoot>);
    expect(screen.queryByLabelText("Loại GxP cho hồ sơ mới")).toBeNull();
    rendered.rerender(<CatalogCreateSessionRoot><InitialCaseCreationDialog {...props} /></CatalogCreateSessionRoot>);
    expect((screen.getByLabelText("Loại GxP cho hồ sơ mới") as HTMLSelectElement).value).toBe("GLP");
    await waitFor(() => expect((screen.getByLabelText("ProductionLine UUID") as HTMLSelectElement).value).toBe("line-A"));
    // Selecting a context does not persist a Case or auto-run a mutation.
    expect(api.createInitialCase).not.toHaveBeenCalled();
  });

  it("recovers a previously unverified Case after dialog unmount without allocating a new UUID", async () => {
    api.getCaseDetail.mockRejectedValueOnce(new Error("network")).mockResolvedValueOnce(caseRow);
    const rendered = view(); await fill();
    fireEvent.click(screen.getByRole("button", { name: "Tạo hồ sơ Draft" }));
    await screen.findByText(/Chưa xác minh:/);
    rendered.rerender(<CatalogCreateSessionRoot><div>Đang ở trang khác</div></CatalogCreateSessionRoot>);
    rendered.rerender(<CatalogCreateSessionRoot><InitialCaseCreationDialog {...props} /></CatalogCreateSessionRoot>);
    expect((screen.getByLabelText("Loại GxP cho hồ sơ mới") as HTMLSelectElement).value).toBe("GMP");
    expect((screen.getByRole("button", { name: "Đã khóa intent" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Đọc lại Case canonical" }));
    await screen.findByText(/Case nháp canonical đã xác minh/);
    expect(api.createInitialCase).toHaveBeenCalledTimes(1);
    expect(api.getCaseDetail.mock.calls.every((args: unknown[]) => args[0] === "case-uuid")).toBe(true);
  });

  it("keeps late Site A verification from displaying or opening Case on Site B", async () => {
    let release!: (row: CaseDetail) => void;
    api.getCaseDetail.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    const opened = vi.fn();
    const rendered = view({ onVerifiedOpen: opened }); await fill();
    fireEvent.click(screen.getByRole("button", { name: "Tạo hồ sơ Draft" }));
    await waitFor(() => expect(api.getCaseDetail).toHaveBeenCalledTimes(1));
    rendered.rerender(<CatalogCreateSessionRoot><InitialCaseCreationDialog {...props} onVerifiedOpen={opened} siteId="site-B" /></CatalogCreateSessionRoot>);
    await act(async () => { release(caseRow); });
    expect(screen.queryByText(/Case nháp canonical đã xác minh/)).toBeNull();
    expect(opened).not.toHaveBeenCalled();
  });
});

describe("canonical initial Case verification", () => {
  it("does not treat two lines sharing a code as the same owner", () => {
    const intent = { siteId: "site-A", token: {}, phase: "pending" as const, error: null, persisted: null, payload: {
      case_id: "case-uuid", gxp_type: "GMP" as const, production_line_id: "line-A",
      inspection_type: "Mới", applicable_standard: "WHO-GMP", reason: "first",
    } };
    expect(exactInitialCaseReadback(intent, { ...caseRow, production_line_id: "line-A", scope_code: "A" })).toBe(true);
    expect(exactInitialCaseReadback(intent, { ...caseRow, production_line_id: "line-B", scope_code: "A" })).toBe(false);
  });
});
