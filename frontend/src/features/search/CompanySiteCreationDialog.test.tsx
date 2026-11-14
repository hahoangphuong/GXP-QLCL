import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ createCompany: vi.fn(), createSite: vi.fn(), getCompany: vi.fn(), getSite: vi.fn(), listCompanies: vi.fn() }));
vi.mock("../../lib/api", () => api);

import { CompanySiteCreationDialog } from "./CompanySiteCreationDialog";
import { CatalogCreateSessionRoot } from "./CatalogCreateSession";

const auth = { username: "operator", role: "admin" as const };
const available = { action_key: "create_company", label: "Công ty mới", readiness_status: "available", detail: "ready", required_permissions: ["case.edit"] };
const siteAvailable = { ...available, action_key: "create_site", label: "Cơ sở mới" };
const company = { id: "company-A", legacy_company_id: null, legal_name: "Công ty A", legal_address: "Hà Nội", english_name: null, short_name: null, legal_address_en: null, is_inactive: false };
const site = { id: "uuid-intent", legacy_site_id: null, company_id: "company-A", site_name: "Cơ sở A", site_address: "Hà Nội", site_name_en: null, site_address_en: null, province_name: null, short_name: null };

function view(openAction: "create_company" | "create_site" = "create_company") {
  return render(<CatalogCreateSessionRoot><CompanySiteCreationDialog auth={auth} companyAction={available} onClose={vi.fn()} onSiteVerified={vi.fn()} openAction={openAction} ownerIdentity="access-A" siteAction={siteAvailable} useStubAuth /></CatalogCreateSessionRoot>);
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
    render(<CatalogCreateSessionRoot><CompanySiteCreationDialog auth={auth} companyAction={available} onClose={vi.fn()} onSiteVerified={onSiteVerified} openAction="create_site" ownerIdentity="access-A" siteAction={siteAvailable} useStubAuth /></CatalogCreateSessionRoot>);
    fireEvent.change(screen.getByLabelText("Tìm Company theo tên"), { target: { value: "Công ty" } });
    await screen.findByRole("option", { name: /Công ty A/ });
    fireEvent.change(screen.getByLabelText("Company canonical"), { target: { value: "company-A" } });
    await waitFor(() => expect(api.getCompany).toHaveBeenCalledWith("company-A", auth, true, undefined));
    fireEvent.change(screen.getByLabelText("Tên cơ sở"), { target: { value: "Cơ sở A" } });
    fireEvent.change(screen.getByLabelText("Địa chỉ cơ sở"), { target: { value: "Hà Nội" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo Cơ sở" }));
    await waitFor(() => expect(api.createSite).toHaveBeenCalledWith("company-A", expect.objectContaining({ site_id: "uuid-intent" }), auth, true, undefined));
    await waitFor(() => expect(onSiteVerified).toHaveBeenCalledWith("uuid-intent"));
  });

  it("uses bounded server-side Company discovery instead of a legacy first-page list", async () => {
    api.listCompanies.mockResolvedValue(Array.from({ length: 50 }, (_, index) => ({ id: `company-${index + 21}`, legacy_company_id: null, legal_name: `Trùng tên ${index + 21}`, short_name: null })));
    view("create_site");
    fireEvent.change(screen.getByLabelText("Tìm Company theo tên"), { target: { value: "Trùng tên" } });
    await screen.findByRole("option", { name: /Trùng tên 70/ });
    expect(api.listCompanies).toHaveBeenCalledWith(auth, true, undefined, "Trùng tên");
  });

  it("does not let a late Company A detail replace current Company B", async () => {
    let resolveA!: (value: typeof company) => void;
    api.listCompanies.mockResolvedValue([{ id: "company-A", legacy_company_id: null, legal_name: "A", short_name: null }, { id: "company-B", legacy_company_id: null, legal_name: "B", short_name: null }]);
    api.getCompany.mockImplementation((id: string) => id === "company-A" ? new Promise((resolve) => { resolveA = resolve; }) : Promise.resolve({ ...company, id: "company-B", legal_name: "B" }));
    view("create_site");
    fireEvent.change(screen.getByLabelText("Tìm Company theo tên"), { target: { value: "A" } });
    await screen.findByRole("option", { name: /A/ });
    fireEvent.change(screen.getByLabelText("Company canonical"), { target: { value: "company-A" } });
    fireEvent.change(screen.getByLabelText("Company canonical"), { target: { value: "company-B" } });
    await screen.findByText(/Company đã chọn:.*B/);
    resolveA(company);
    await waitFor(() => expect(screen.getByText(/Company đã chọn:.*B/).textContent).toContain("company-B"));
  });

  it("does not expose create when case.edit readiness is forbidden", () => {
    const disabled = { ...available, readiness_status: "forbidden", detail: "missing_permission" };
    render(<CatalogCreateSessionRoot><CompanySiteCreationDialog auth={auth} companyAction={disabled} onClose={vi.fn()} onSiteVerified={vi.fn()} openAction="create_company" ownerIdentity="access-A" siteAction={siteAvailable} useStubAuth /></CatalogCreateSessionRoot>);
    expect((screen.getByRole("button", { name: "Tạo Công ty" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("admits two immediate Company submits as one UUID and one POST", async () => {
    let resolvePost!: () => void;
    api.createCompany.mockImplementationOnce(() => new Promise<void>((resolve) => { resolvePost = resolve; }));
    view();
    fireEvent.change(screen.getByLabelText("Tên pháp nhân"), { target: { value: "Công ty A" } });
    fireEvent.change(screen.getByLabelText("Địa chỉ pháp lý"), { target: { value: "Hà Nội" } });
    const form = screen.getByLabelText("Tên pháp nhân").closest("form")!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(api.createCompany).toHaveBeenCalledTimes(1);
    resolvePost();
    await waitFor(() => expect(api.getCompany).toHaveBeenCalledWith("uuid-intent", auth, true, undefined));
  });

  it("allows closing a verified Company without requiring Site creation", async () => {
    const onClose = vi.fn();
    api.getCompany.mockResolvedValueOnce({ ...company, id: "uuid-intent" });
    render(<CatalogCreateSessionRoot><CompanySiteCreationDialog auth={auth} companyAction={available} onClose={onClose} onSiteVerified={vi.fn()} openAction="create_company" ownerIdentity="access-A" siteAction={siteAvailable} useStubAuth /></CatalogCreateSessionRoot>);
    fireEvent.change(screen.getByLabelText("Tên pháp nhân"), { target: { value: "Công ty A" } });
    fireEvent.change(screen.getByLabelText("Địa chỉ pháp lý"), { target: { value: "Hà Nội" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo Công ty" }));
    await screen.findByRole("status");
    fireEvent.click(screen.getAllByRole("button", { name: "Đóng" })[0]);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not navigate on a late Site verification after the dialog closes", async () => {
    let resolveRead!: (value: typeof site) => void;
    api.getSite.mockImplementationOnce(() => new Promise((resolve) => { resolveRead = resolve; }));
    const onSiteVerified = vi.fn();
    const props = { auth, companyAction: available, onClose: vi.fn(), onSiteVerified, ownerIdentity: "access-A", siteAction: siteAvailable, useStubAuth: true };
    const rendered = render(<CatalogCreateSessionRoot><CompanySiteCreationDialog {...props} openAction="create_site" /></CatalogCreateSessionRoot>);
    fireEvent.change(screen.getByLabelText("Tìm Company theo tên"), { target: { value: "Công ty" } });
    await screen.findByRole("option", { name: /Công ty A/ });
    fireEvent.change(screen.getByLabelText("Company canonical"), { target: { value: "company-A" } });
    await waitFor(() => expect(api.getCompany).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText("Tên cơ sở"), { target: { value: "Cơ sở A" } });
    fireEvent.change(screen.getByLabelText("Địa chỉ cơ sở"), { target: { value: "Hà Nội" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo Cơ sở" }));
    await waitFor(() => expect(api.getSite).toHaveBeenCalled());
    rendered.rerender(<CatalogCreateSessionRoot><CompanySiteCreationDialog {...props} openAction={null} /></CatalogCreateSessionRoot>);
    await act(async () => { resolveRead(site); });
    expect(onSiteVerified).not.toHaveBeenCalled();
  });
});


describe("catalog create in-session lifecycle regressions", () => {
  it("ignores search results from an old query after the operator clears the search", async () => {
    let finishSearch!: (value: typeof company[]) => void;
    api.listCompanies.mockImplementationOnce(() => new Promise((resolve) => { finishSearch = resolve; }));
    view("create_site");
    fireEvent.change(screen.getByLabelText("Tìm Company theo tên"), { target: { value: "Pháp nhân cũ" } });
    await waitFor(() => expect(api.listCompanies).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText("Tìm Company theo tên"), { target: { value: "" } });
    await act(async () => { finishSearch([{ ...company, id: "stale-company", legal_name: "Pháp nhân cũ" }]); });
    expect(screen.queryByRole("option", { name: /Pháp nhân cũ/ })).toBeNull();
    expect((screen.getByLabelText("Tìm Company theo tên") as HTMLInputElement).value).toBe("");
  });

  it("revokes a stale Site navigation callback on actual route unmount", async () => {
    let finishReadback!: (value: typeof site) => void;
    api.getSite.mockImplementationOnce(() => new Promise((resolve) => { finishReadback = resolve; }));
    const onSiteVerified = vi.fn();
    const rendered = render(<CatalogCreateSessionRoot><CompanySiteCreationDialog
      auth={auth} companyAction={available} onClose={vi.fn()} onSiteVerified={onSiteVerified}
      openAction="create_site" ownerIdentity="access-A" siteAction={siteAvailable} useStubAuth
    /></CatalogCreateSessionRoot>);
    fireEvent.change(screen.getByLabelText("Tìm Company theo tên"), { target: { value: "Công ty" } });
    await screen.findByRole("option", { name: /Công ty A/ });
    fireEvent.change(screen.getByLabelText("Company canonical"), { target: { value: "company-A" } });
    await waitFor(() => expect(api.getCompany).toHaveBeenCalledWith("company-A", auth, true, undefined));
    fireEvent.change(screen.getByLabelText("Tên cơ sở"), { target: { value: "Cơ sở A" } });
    fireEvent.change(screen.getByLabelText("Địa chỉ cơ sở"), { target: { value: "Hà Nội" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo Cơ sở" }));
    await waitFor(() => expect(api.getSite).toHaveBeenCalledTimes(1));
    rendered.unmount();
    await act(async () => { finishReadback(site); });
    expect(onSiteVerified).not.toHaveBeenCalled();
  });

  it("lets an operator explicitly create two Companies with separate UUIDs in one session", async () => {
    const ids = ["first-company-uuid", "second-company-uuid"];
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => ids.shift()!) });
    api.getCompany.mockImplementation((id: string) => Promise.resolve({ ...company, id }));
    view();
    for (let index = 0; index < 2; index += 1) {
      fireEvent.change(screen.getByLabelText("Tên pháp nhân"), { target: { value: "Công ty A" } });
      fireEvent.change(screen.getByLabelText("Địa chỉ pháp lý"), { target: { value: "Hà Nội" } });
      fireEvent.click(screen.getByRole("button", { name: "Tạo Công ty" }));
      await screen.findByRole("status");
      if (index === 0) {
        fireEvent.click(screen.getByRole("button", { name: "Tạo công ty khác" }));
        expect((screen.getByLabelText("Tên pháp nhân") as HTMLInputElement).value).toBe("");
      }
    }
    expect(api.createCompany.mock.calls.map((call: unknown[]) => (call[0] as { company_id: string }).company_id))
      .toEqual(["first-company-uuid", "second-company-uuid"]);
  });

  it("lets an operator explicitly create two Sites under the same canonical Company", async () => {
    const ids = ["first-site-uuid", "second-site-uuid"];
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => ids.shift()!) });
    api.getSite.mockImplementation((id: string) => Promise.resolve({ ...site, id }));
    view("create_site");
    fireEvent.change(screen.getByLabelText("Tìm Company theo tên"), { target: { value: "Công ty" } });
    await screen.findByRole("option", { name: /Công ty A/ });
    fireEvent.change(screen.getByLabelText("Company canonical"), { target: { value: "company-A" } });
    await waitFor(() => expect(api.getCompany).toHaveBeenCalledWith("company-A", auth, true, undefined));
    for (let index = 0; index < 2; index += 1) {
      fireEvent.change(screen.getByLabelText("Tên cơ sở"), { target: { value: "Cơ sở A" } });
      fireEvent.change(screen.getByLabelText("Địa chỉ cơ sở"), { target: { value: "Hà Nội" } });
      fireEvent.click(screen.getByRole("button", { name: "Tạo Cơ sở" }));
      await screen.findByRole("status");
      if (index === 0) {
        fireEvent.click(screen.getByRole("button", { name: "Tạo cơ sở khác" }));
        expect((screen.getByLabelText("Tên cơ sở") as HTMLInputElement).value).toBe("");
      }
    }
    expect(api.createSite.mock.calls.map((call: unknown[]) => ({ companyId: call[0], siteId: (call[1] as { site_id: string }).site_id })))
      .toEqual([
        { companyId: "company-A", siteId: "first-site-uuid" },
        { companyId: "company-A", siteId: "second-site-uuid" },
      ]);
  });

  it("retains an uncertain Company intent across dialog remount under one session root", async () => {
    let finishReadback!: (value: typeof company) => void;
    api.getCompany.mockImplementationOnce(() => new Promise((resolve) => { finishReadback = resolve; }));
    const props = { auth, companyAction: available, onClose: vi.fn(), onSiteVerified: vi.fn(), ownerIdentity: "access-A", siteAction: siteAvailable, useStubAuth: true };
    const rendered = render(<CatalogCreateSessionRoot><CompanySiteCreationDialog {...props} openAction="create_company" /></CatalogCreateSessionRoot>);
    fireEvent.change(screen.getByLabelText("Tên pháp nhân"), { target: { value: "Công ty A" } });
    fireEvent.change(screen.getByLabelText("Địa chỉ pháp lý"), { target: { value: "Hà Nội" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo Công ty" }));
    await waitFor(() => expect(api.getCompany).toHaveBeenCalledTimes(1));
    rendered.rerender(<CatalogCreateSessionRoot><CompanySiteCreationDialog {...props} openAction={null} /></CatalogCreateSessionRoot>);
    rendered.rerender(<CatalogCreateSessionRoot><CompanySiteCreationDialog {...props} openAction="create_company" /></CatalogCreateSessionRoot>);
    expect((screen.getByRole("button", { name: "Đang xác minh..." }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.createCompany).toHaveBeenCalledTimes(1);
    await act(async () => { finishReadback({ ...company, id: "uuid-intent" }); });
    await screen.findByRole("status");
    expect(api.createCompany).toHaveBeenCalledTimes(1);
  });
});
