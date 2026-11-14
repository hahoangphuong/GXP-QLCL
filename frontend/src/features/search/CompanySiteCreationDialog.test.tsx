import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ createCompany: vi.fn(), createSite: vi.fn(), getCompany: vi.fn(), getSite: vi.fn(), listCompanies: vi.fn() }));
vi.mock("../../lib/api", () => api);

import { CompanySiteCreationDialog } from "./CompanySiteCreationDialog";

const auth = { username: "operator", role: "admin" as const };
const available = { action_key: "create_company", label: "Công ty mới", readiness_status: "available", detail: "ready", required_permissions: ["case.edit"] };
const siteAvailable = { ...available, action_key: "create_site", label: "Cơ sở mới" };
const company = { id: "company-A", legacy_company_id: null, legal_name: "Công ty A", legal_address: "Hà Nội", english_name: null, short_name: null, legal_address_en: null, is_inactive: false };
const site = { id: "uuid-intent", legacy_site_id: null, company_id: "company-A", site_name: "Cơ sở A", site_address: "Hà Nội", site_name_en: null, site_address_en: null, province_name: null, short_name: null };

function view(openAction: "create_company" | "create_site" = "create_company") {
  return render(<CompanySiteCreationDialog auth={auth} companyAction={available} onClose={vi.fn()} onSiteVerified={vi.fn()} openAction={openAction} siteAction={siteAvailable} useStubAuth />);
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "uuid-intent") });
  api.listCompanies.mockResolvedValue([{ id: "company-A", legacy_company_id: null, legal_name: "Công ty A", short_name: null }]);
  api.getCompany.mockResolvedValue(company);
  api.createCompany.mockResolvedValue(company);
  api.getSite.mockResolvedValue(site);
  api.createSite.mockResolvedValue(site);
});

describe("CompanySiteCreationDialog", () => {
  it("allocates one Company UUID, posts once, then verifies canonical GET", async () => {
    view();
    fireEvent.change(screen.getByLabelText("Tên pháp nhân"), { target: { value: "Công ty A" } });
    fireEvent.change(screen.getByLabelText("Địa chỉ pháp lý"), { target: { value: "Hà Nội" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo Công ty" }));
    await waitFor(() => expect(api.getCompany).toHaveBeenCalledWith("uuid-intent", auth, true, undefined));
    expect(api.createCompany).toHaveBeenCalledTimes(1);
    expect(api.createCompany.mock.calls[0][0]).toMatchObject({ company_id: "uuid-intent", legal_name: "Công ty A", legal_address: "Hà Nội" });
  });

  it("keeps the same intent locked when timeout readback cannot verify it", async () => {
    api.createCompany.mockRejectedValueOnce(new Error("network"));
    api.getCompany.mockRejectedValue(new Error("offline"));
    view();
    fireEvent.change(screen.getByLabelText("Tên pháp nhân"), { target: { value: "Công ty A" } });
    fireEvent.change(screen.getByLabelText("Địa chỉ pháp lý"), { target: { value: "Hà Nội" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo Công ty" }));
    await screen.findByRole("alert");
    expect((screen.getByRole("button", { name: "Đang xác minh..." }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Đọc lại canonical" }));
    await waitFor(() => expect(api.createCompany).toHaveBeenCalledTimes(1));
    expect(api.getCompany.mock.calls.every((call: unknown[]) => call[0] === "uuid-intent")).toBe(true);
  });

  it("rejects readback with a matching UUID but mismatched canonical fields", async () => {
    api.getCompany.mockResolvedValue({ ...company, id: "uuid-intent", legal_name: "Khác" });
    view();
    fireEvent.change(screen.getByLabelText("Tên pháp nhân"), { target: { value: "Công ty A" } });
    fireEvent.change(screen.getByLabelText("Địa chỉ pháp lý"), { target: { value: "Hà Nội" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo Công ty" }));
    expect((await screen.findByRole("alert")).textContent).toContain("không khớp payload intent");
  });

  it("creates Site only below the selected canonical Company and verifies its owner", async () => {
    const onSiteVerified = vi.fn();
    render(<CompanySiteCreationDialog auth={auth} companyAction={available} onClose={vi.fn()} onSiteVerified={onSiteVerified} openAction="create_site" siteAction={siteAvailable} useStubAuth />);
    await screen.findByRole("option", { name: /Công ty A/ });
    fireEvent.change(screen.getByLabelText("Company canonical"), { target: { value: "company-A" } });
    await waitFor(() => expect(api.getCompany).toHaveBeenCalledWith("company-A", auth, true, undefined));
    fireEvent.change(screen.getByLabelText("Tên cơ sở"), { target: { value: "Cơ sở A" } });
    fireEvent.change(screen.getByLabelText("Địa chỉ cơ sở"), { target: { value: "Hà Nội" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo Cơ sở" }));
    await waitFor(() => expect(api.createSite).toHaveBeenCalledWith("company-A", expect.objectContaining({ site_id: "uuid-intent" }), auth, true, undefined));
    await waitFor(() => expect(onSiteVerified).toHaveBeenCalledWith("uuid-intent"));
  });

  it("does not let a late Company A detail replace current Company B", async () => {
    let resolveA!: (value: typeof company) => void;
    api.listCompanies.mockResolvedValue([{ id: "company-A", legacy_company_id: null, legal_name: "A", short_name: null }, { id: "company-B", legacy_company_id: null, legal_name: "B", short_name: null }]);
    api.getCompany.mockImplementation((id: string) => id === "company-A" ? new Promise((resolve) => { resolveA = resolve; }) : Promise.resolve({ ...company, id: "company-B", legal_name: "B" }));
    view("create_site");
    await screen.findByRole("option", { name: /A/ });
    fireEvent.change(screen.getByLabelText("Company canonical"), { target: { value: "company-A" } });
    fireEvent.change(screen.getByLabelText("Company canonical"), { target: { value: "company-B" } });
    await screen.findByText(/Company đã chọn:.*B/);
    resolveA(company);
    await waitFor(() => expect(screen.getByText(/Company đã chọn:.*B/).textContent).toContain("company-B"));
  });

  it("does not expose create when case.edit readiness is forbidden", () => {
    const disabled = { ...available, readiness_status: "forbidden", detail: "missing_permission" };
    render(<CompanySiteCreationDialog auth={auth} companyAction={disabled} onClose={vi.fn()} onSiteVerified={vi.fn()} openAction="create_company" siteAction={siteAvailable} useStubAuth />);
    expect((screen.getByRole("button", { name: "Tạo Công ty" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
