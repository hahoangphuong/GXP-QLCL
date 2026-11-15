import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ createProductionLine: vi.fn(), getCompany: vi.fn(), getProductionLine: vi.fn(), getSite: vi.fn() }));
vi.mock("../../lib/api", () => api);

import { CatalogCreateSessionRoot } from "./CatalogCreateSession";
import { ProductionLineCreationDialog } from "./ProductionLineCreationDialog";

const auth = { username: "operator", role: "admin" as const };
const available = { action_key: "create_production_line", label: "Dây chuyền mới", readiness_status: "available", detail: "ready", required_permissions: ["case.edit"] };
const siteA = { id: "site-A", legacy_site_id: null, company_id: "company-A", site_name: "Cơ sở A", site_address: "Hà Nội", site_name_en: null, site_address_en: null, province_name: null, short_name: null };
const companyA = { id: "company-A", legacy_company_id: null, legal_name: "Công ty A", legal_address: "Hà Nội", english_name: null, short_name: null, legal_address_en: null, is_inactive: false };

function line(id = "line-uuid", overrides: Record<string, unknown> = {}) {
  return { id, site_id: "site-A", code: "LINE-A", effective_from: "2026-11-14", effective_to: null, row_version: 1, ...overrides };
}

function view(props: Partial<Parameters<typeof ProductionLineCreationDialog>[0]> = {}) {
  return render(<CatalogCreateSessionRoot><ProductionLineCreationDialog
    action={available} auth={auth} onClose={vi.fn()} onVerified={vi.fn()} open ownerIdentity="access-A/site-A" siteId="site-A" useStubAuth {...props}
  /></CatalogCreateSessionRoot>);
}

async function fillValidForm() {
  await screen.findByText("Công ty A / Cơ sở A");
  fireEvent.change(screen.getByLabelText("Mã dây chuyền"), { target: { value: "LINE-A" } });
  fireEvent.change(screen.getByLabelText("Ngày bắt đầu hiệu lực"), { target: { value: "2026-11-14" } });
  fireEvent.change(screen.getByLabelText("Tham chiếu bằng chứng định danh vật lý"), { target: { value: "REFERENCE-001" } });
  fireEvent.change(screen.getByLabelText("Lý do tạo dây chuyền"), { target: { value: "Khai báo vật lý" } });
  const acknowledgement = screen.getByLabelText("Xác nhận dây chuyền vật lý riêng biệt") as HTMLInputElement;
  if (!acknowledgement.checked) fireEvent.click(acknowledgement);
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "line-uuid") });
  api.getSite.mockResolvedValue(siteA);
  api.getCompany.mockResolvedValue(companyA);
  api.createProductionLine.mockResolvedValue({ ...line(), audit_event_id: "audit-1" });
  api.getProductionLine.mockResolvedValue(line());
});

describe("ProductionLineCreationDialog", () => {
  it("allocates one UUID, posts an explicit physical-line payload once, then verifies canonical GET", async () => {
    view();
    await fillValidForm();
    fireEvent.click(screen.getByRole("button", { name: "Tạo dây chuyền" }));
    await waitFor(() => expect(api.createProductionLine).toHaveBeenCalledWith("site-A", expect.objectContaining({
      production_line_id: "line-uuid", code: "LINE-A", effective_from: "2026-11-14", effective_to: null,
      physical_identity_evidence_reference: "REFERENCE-001", reason: "Khai báo vật lý",
    }), auth, true, undefined));
    await waitFor(() => expect(api.getProductionLine).toHaveBeenCalledWith("line-uuid", auth, true, undefined));
    expect((await screen.findByRole("status")).textContent).toContain("line-uuid");
  });

  it("synchronously admits two immediate submits as one POST", async () => {
    let resolvePost!: () => void;
    api.createProductionLine.mockImplementationOnce(() => new Promise<void>((resolve) => { resolvePost = resolve; }));
    view();
    await fillValidForm();
    const form = screen.getByLabelText("Mã dây chuyền").closest("form")!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(api.createProductionLine).toHaveBeenCalledTimes(1);
    resolvePost();
    await waitFor(() => expect(api.getProductionLine).toHaveBeenCalledTimes(1));
  });

  it("keeps UUID and payload locked when an unknown POST outcome cannot be read back", async () => {
    api.createProductionLine.mockRejectedValueOnce(new Error("network"));
    api.getProductionLine.mockRejectedValue(new Error("offline"));
    view();
    await fillValidForm();
    fireEvent.click(screen.getByRole("button", { name: "Tạo dây chuyền" }));
    expect((await screen.findByRole("button", { name: "Đang xác minh..." }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Đọc lại canonical" }));
    await waitFor(() => expect(api.createProductionLine).toHaveBeenCalledTimes(1));
    expect(api.getProductionLine.mock.calls.every((call: unknown[]) => call[0] === "line-uuid")).toBe(true);
  });

  it("rejects a readback with the right UUID but the wrong Site or interval", async () => {
    api.getProductionLine.mockResolvedValue(line("line-uuid", { site_id: "site-B", effective_to: "2027-01-01" }));
    view();
    await fillValidForm();
    fireEvent.click(screen.getByRole("button", { name: "Tạo dây chuyền" }));
    expect((await screen.findByRole("alert")).textContent).toContain("không khớp UUID, Site UUID hoặc effective interval");
  });

  it("does not POST an invalid exclusive interval or an inactive owning Company", async () => {
    api.getCompany.mockResolvedValue({ ...companyA, is_inactive: true });
    view();
    await screen.findByRole("alert");
    expect((screen.getByRole("button", { name: "Tạo dây chuyền" }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.createProductionLine).not.toHaveBeenCalled();
  });

  it("does not let a late Site A readback verify or navigate after the dialog switches to Site B", async () => {
    let resolveA!: (value: typeof siteA) => void;
    api.getSite.mockImplementation((id: string) => id === "site-A" ? new Promise((resolve) => { resolveA = resolve; }) : Promise.resolve({ ...siteA, id: "site-B", company_id: "company-B", site_name: "Cơ sở B" }));
    api.getCompany.mockImplementation((id: string) => Promise.resolve({ ...companyA, id, legal_name: id === "company-B" ? "Công ty B" : "Công ty A" }));
    const onVerified = vi.fn();
    const rendered = view({ onVerified });
    rendered.rerender(<CatalogCreateSessionRoot><ProductionLineCreationDialog action={available} auth={auth} onClose={vi.fn()} onVerified={onVerified} open ownerIdentity="access-A/site-B" siteId="site-B" useStubAuth /></CatalogCreateSessionRoot>);
    await screen.findByText("Công ty B / Cơ sở B");
    await act(async () => { resolveA(siteA); });
    expect(screen.getByText("Công ty B / Cơ sở B").textContent).toBe("Công ty B / Cơ sở B");
    expect(onVerified).not.toHaveBeenCalled();
  });

  it("permits two same-code physical lines only after the first canonical UUID is verified", async () => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn().mockReturnValueOnce("line-1").mockReturnValueOnce("line-2") });
    api.getProductionLine.mockImplementation((id: string) => Promise.resolve(line(id)));
    view();
    await fillValidForm();
    fireEvent.click(screen.getByRole("button", { name: "Tạo dây chuyền" }));
    await screen.findByRole("status");
    fireEvent.click(screen.getByRole("button", { name: "Tạo dây chuyền khác" }));
    await fillValidForm();
    fireEvent.click(screen.getByRole("button", { name: "Tạo dây chuyền" }));
    await waitFor(() => expect(api.createProductionLine.mock.calls.map((call: unknown[]) => (call[1] as { production_line_id: string }).production_line_id)).toEqual(["line-1", "line-2"]));
  });
});
