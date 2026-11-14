import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getSite: vi.fn(), getCompany: vi.fn(), createProductionLine: vi.fn(),
  getProductionLine: vi.fn(), listSiteProductionLines: vi.fn(),
}));
vi.mock("../../lib/api", () => api);

import { CatalogCreateSessionRoot } from "./CatalogCreateSession";
import { PhysicalLineCreationDialog } from "./PhysicalLineCreationDialog";

const auth = { username: "operator", role: "admin" as const };
const site = { id: "site-A", company_id: "company-A", site_name: "Nhà máy A", site_address: "Hà Nội", site_name_en: null, site_address_en: null, province_name: null, short_name: null, legacy_site_id: null };
const company = { id: "company-A", legal_name: "Công ty A", legacy_company_id: null, short_name: null, legal_address: "Hà Nội", english_name: null, legal_address_en: null, is_inactive: false };
const record = { id: "intent-uuid", site_id: "site-A", code: "A", effective_from: "2026-11-14", effective_to: null, row_version: 1 };
const available = { action_key: "create_production_line", label: "Dây chuyền mới", readiness_status: "available", detail: "ready", required_permissions: ["case.edit"] };

const props = { siteId: "site-A", open: true, action: available, auth, useStubAuth: true, accessGeneration: 1, onClose: vi.fn() };
function view(overrides: Partial<typeof props> = {}) {
  return render(<CatalogCreateSessionRoot><PhysicalLineCreationDialog {...props} {...overrides} /></CatalogCreateSessionRoot>);
}
async function fill() {
  await screen.findByText(/Site: /);
  fireEvent.change(screen.getByLabelText("Mã dây chuyền vật lý"), { target: { value: "A" } });
  fireEvent.change(screen.getByLabelText("Hiệu lực từ"), { target: { value: "2026-11-14" } });
  fireEvent.change(screen.getByLabelText("Bằng chứng định danh vật lý"), { target: { value: "SOURCE-A" } });
  fireEvent.change(screen.getByLabelText("Lý do khai báo dây chuyền"), { target: { value: "Đối chiếu hồ sơ vật lý" } });
  fireEvent.click(screen.getByLabelText("Xác nhận định danh vật lý độc lập"));
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "intent-uuid") });
  api.getSite.mockResolvedValue(site);
  api.getCompany.mockResolvedValue(company);
  api.getProductionLine.mockResolvedValue(record);
  api.createProductionLine.mockResolvedValue(record);
  api.listSiteProductionLines.mockResolvedValue([]);
});

describe("PhysicalLineCreationDialog owner and recovery", () => {
  it("sends exactly one UUID-bound POST and verifies Site/code/interval with canonical GET", async () => {
    view();
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Tạo dây chuyền vật lý" }));
    await waitFor(() => expect(api.getProductionLine).toHaveBeenCalledWith("intent-uuid", auth, true, undefined));
    expect(api.createProductionLine).toHaveBeenCalledTimes(1);
    expect(api.createProductionLine).toHaveBeenCalledWith("site-A", {
      production_line_id: "intent-uuid", code: "A", effective_from: "2026-11-14",
      effective_to: null, physical_identity_evidence_reference: "SOURCE-A", reason: "Đối chiếu hồ sơ vật lý",
    }, auth, true, undefined);
    expect(screen.getByText(/Đã xác minh dây chuyền UUID/).textContent).toContain("intent-uuid");
    expect(api.listSiteProductionLines).toHaveBeenCalledWith("site-A", auth, true, undefined);
  });

  it("admits two simultaneous submissions as one POST and one UUID", async () => {
    let release!: (value: typeof record) => void;
    api.createProductionLine.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    view();
    await fill();
    const form = screen.getByLabelText("Mã dây chuyền vật lý").closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(api.createProductionLine).toHaveBeenCalledTimes(1);
    expect(crypto.randomUUID).toHaveBeenCalledTimes(1);
    await act(async () => { release(record); });
    await screen.findByText(/Đã xác minh dây chuyền UUID/);
  });

  it("preserves unknown-outcome UUID and payload, never retries POST", async () => {
    api.createProductionLine.mockRejectedValueOnce(new Error("network timeout"));
    api.getProductionLine.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(record);
    view();
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Tạo dây chuyền vật lý" }));
    await screen.findByRole("alert");
    expect((screen.getByRole("button", { name: "Đã khóa intent" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Đọc lại canonical" }));
    await screen.findByText(/Đã xác minh dây chuyền UUID/);
    expect(api.createProductionLine).toHaveBeenCalledTimes(1);
    expect(api.getProductionLine.mock.calls.every((call: unknown[]) => call[0] === "intent-uuid")).toBe(true);
  });

  it.each([
    ["wrong Site", { ...record, site_id: "site-B" }],
    ["wrong code", { ...record, code: "B" }],
    ["wrong effective date", { ...record, effective_from: "2026-11-15" }],
    ["wrong interval", { ...record, effective_to: "2027-01-01" }],
  ])("rejects canonical GET with %s but same UUID", async (_, persisted) => {
    api.getProductionLine.mockResolvedValue(persisted);
    view();
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Tạo dây chuyền vật lý" }));
    expect((await screen.findByRole("alert")).textContent).toContain("không khớp");
    expect(api.createProductionLine).toHaveBeenCalledTimes(1);
  });

  it("does not admit a line if Company is inactive", async () => {
    api.getCompany.mockResolvedValue({ ...company, is_inactive: true });
    view();
    await fill();
    expect((screen.getByRole("button", { name: "Tạo dây chuyền vật lý" }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.createProductionLine).not.toHaveBeenCalled();
  });

  it("does not admit without canonical Site owner even if readiness says available", async () => {
    api.getSite.mockResolvedValue({ ...site, id: "site-B" });
    view();
    expect((await screen.findByRole("alert")).textContent).toContain("Site UUID");
    expect((screen.getByRole("button", { name: "Tạo dây chuyền vật lý" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("respects forbidden readiness and interval validation", async () => {
    view({ action: { ...available, readiness_status: "forbidden" } });
    await fill();
    fireEvent.change(screen.getByLabelText("Hiệu lực đến"), { target: { value: "2026-11-14" } });
    expect(screen.getByText(/Ngày kết thúc phải sau ngày bắt đầu/)).toBeDefined();
    expect((screen.getByRole("button", { name: "Tạo dây chuyền vật lý" }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.createProductionLine).not.toHaveBeenCalled();
  });

  it("allows successive distinct UUIDs for same-code physical lines", async () => {
    const ids = ["line-first", "line-second"];
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => ids.shift()!) });
    api.getProductionLine.mockImplementation((id: string) => Promise.resolve({ ...record, id }));
    view();
    await fill();
    for (let index = 0; index < 2; index += 1) {
      fireEvent.click(screen.getByRole("button", { name: "Tạo dây chuyền vật lý" }));
      await screen.findByText(/Đã xác minh dây chuyền UUID/);
      if (index === 0) {
        fireEvent.click(screen.getByRole("button", { name: "Tạo dây chuyền khác" }));
        await fill();
      }
    }
    expect(api.createProductionLine.mock.calls.map((call: unknown[]) => (call[1] as { production_line_id: string }).production_line_id))
      .toEqual(["line-first", "line-second"]);
    expect(api.createProductionLine.mock.calls.map((call: unknown[]) => (call[1] as { code: string }).code))
      .toEqual(["A", "A"]);
  });

  it("retains uncertain intent over Site A → B → A without another POST", async () => {
    api.getProductionLine.mockRejectedValue(new Error("offline"));
    const rendered = view();
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Tạo dây chuyền vật lý" }));
    await screen.findByRole("alert");
    rendered.rerender(<CatalogCreateSessionRoot><PhysicalLineCreationDialog {...props} siteId="site-B" /></CatalogCreateSessionRoot>);
    rendered.rerender(<CatalogCreateSessionRoot><PhysicalLineCreationDialog {...props} siteId="site-A" /></CatalogCreateSessionRoot>);
    expect((screen.getByRole("button", { name: "Đã khóa intent" }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.createProductionLine).toHaveBeenCalledTimes(1);
  });
});
