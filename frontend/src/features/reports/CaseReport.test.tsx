import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../../App";
import { getCaseReport } from "../../lib/api";
import { CaseReport } from "./CaseReport";

vi.mock("../../lib/api", () => ({ getCaseReport: vi.fn() }));
const access: ApiAccess = { auth: { username: "test", role: "reader" }, useStubAuth: true, bearerToken: null, canLoadSecureApi: true, accessGeneration: 1 };
const row = { case_id: "case-a", site_id: "site-a", result_key: "site-a:GMP:canonical:line-a", production_line_id: "line-a", facility_name: "Cơ sở A", company_name: "Công ty A", gxp_type: "GMP", state: "planned", reference_code: "KT-01", opened_year: 2026 };

beforeEach(() => { vi.mocked(getCaseReport).mockReset(); });
describe("case report", () => {
  it("filters cases and links the canonical case and line", async () => {
    vi.mocked(getCaseReport).mockResolvedValue({ items: [row], total_count: 1, offset: 0, limit: 100 });
    render(<MemoryRouter><CaseReport access={access} inspectionQueue={false} /></MemoryRouter>);
    const link = await screen.findByRole("link", { name: "KT-01" });
    expect(link).toHaveAttribute("href", "/cases/case-a");
    expect(link).not.toHaveAttribute("href", expect.stringContaining("site_id="));
    fireEvent.change(screen.getByLabelText("Cơ sở, công ty hoặc mã hồ sơ"), { target: { value: "Công ty A" } });
    fireEvent.change(screen.getByLabelText("Năm hồ sơ"), { target: { value: "2026" } });
    fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
    await waitFor(() => expect(getCaseReport).toHaveBeenLastCalledWith(expect.objectContaining({ q: "Công ty A", opened_year: "2026", offset: 0 }), access.auth, true, null));
  });
  it("uses the canonical Case UUID even when a report projection contains stale site or line context", async () => {
    vi.mocked(getCaseReport).mockResolvedValue({ items: [{ ...row, site_id: "stale-site", result_key: "stale", production_line_id: "stale-line" }], total_count: 1, offset: 0, limit: 100 });
    render(<MemoryRouter><CaseReport access={access} inspectionQueue={false} showDocumentsLink /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "KT-01" })).toHaveAttribute("href", "/cases/case-a");
    expect(screen.getByRole("link", { name: "Xem tài liệu" })).toHaveAttribute("href", "/documents/cases/case-a");
  });

  it("limits inspection states and does not expose stale results when access changes", async () => {
    vi.mocked(getCaseReport).mockResolvedValueOnce({ items: [row], total_count: 1, offset: 0, limit: 100 }).mockImplementationOnce(() => new Promise(() => {}));
    const { rerender } = render(<MemoryRouter><CaseReport access={access} inspectionQueue /></MemoryRouter>);
    await screen.findByText("Cơ sở A");
    expect(screen.queryByRole("option", { name: /hoàn thành/i })).not.toBeInTheDocument();
    rerender(<MemoryRouter><CaseReport access={{ ...access, accessGeneration: 2 }} inspectionQueue /></MemoryRouter>);
    expect(screen.queryByText("Cơ sở A")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Đang tải");
  });
  it("exports the applied filter using the complete report", async () => {
    const dangerous = { ...row, facility_name: "=HYPERLINK(\"x\")" };
    vi.mocked(getCaseReport).mockImplementation(async filters => ({ items: [dangerous], total_count: 1, offset: 0, limit: filters.export ? 10000 : 100 }));
    const create = vi.fn().mockReturnValue("blob:test");
    const revoke = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<MemoryRouter><CaseReport access={access} inspectionQueue={false} /></MemoryRouter>);
    await screen.findByText(dangerous.facility_name);
    fireEvent.change(screen.getByLabelText("Cơ sở, công ty hoặc mã hồ sơ"), { target: { value: "A" } });
    fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
    await waitFor(() => expect(getCaseReport).toHaveBeenLastCalledWith(expect.objectContaining({ q: "A" }), access.auth, true, null));
    fireEvent.click(await screen.findByRole("button", { name: "Xuất CSV (Excel)" }));
    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(getCaseReport).toHaveBeenLastCalledWith(expect.objectContaining({ q: "A", export: true }), access.auth, true, null);
    expect(click).toHaveBeenCalledOnce();
    expect(revoke).toHaveBeenCalledWith("blob:test");
    Reflect.deleteProperty(URL, "createObjectURL"); Reflect.deleteProperty(URL, "revokeObjectURL"); click.mockRestore();
  });
  it("refuses an incomplete export rather than downloading it", async () => {
    vi.mocked(getCaseReport).mockImplementation(async filters => ({ items: [row], total_count: filters.export ? 2 : 1, offset: 0, limit: 100 }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<MemoryRouter><CaseReport access={access} inspectionQueue={false} /></MemoryRouter>);
    await screen.findByText("Cơ sở A");
    fireEvent.click(screen.getByRole("button", { name: "Xuất CSV (Excel)" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("không đầy đủ");
    expect(click).not.toHaveBeenCalled();
    click.mockRestore();
  });
});
