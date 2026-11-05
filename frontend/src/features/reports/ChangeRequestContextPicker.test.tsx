import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../../App";
import { searchFacilities } from "../../lib/api";
import type { FacilitySearchResult } from "../../types";
import { ChangeRequestContextPicker, changeRequestSearchLink } from "./ChangeRequestContextPicker";

vi.mock("../../lib/api", () => ({ searchFacilities: vi.fn() }));

const access: ApiAccess = {
  auth: { username: "reader", role: "reader" }, useStubAuth: true,
  bearerToken: null, canLoadSecureApi: true, accessGeneration: 1,
};
const row: FacilitySearchResult = {
  result_key: "site-1:GMP:line-1", site_id: "site-1", legacy_site_id: 2, facility_code: "F",
  context_code: "GMP-L1", result_grain: "production_line", gxp_type: "GMP",
  line_code: "L1", production_line_id: "line-1", production_line_code: "L1",
  production_line_identity_state: "canonical", facility_name: "Cơ sở A",
  company_name: "Công ty B", gxp_types: ["GMP"], certificate_scope_summary: null,
  province_name: null, last_inspection_on: null, current_state: null,
  current_certificate_number: null, current_certificate_expiry: null,
};
function mount(currentAccess = access) {
  return render(<MemoryRouter><ChangeRequestContextPicker access={currentAccess}
    siteId="site-1" changeRequestId="cr-uuid" /></MemoryRouter>);
}
function page(items: FacilitySearchResult[], totalCount = items.length, offset = 0) {
  return { items, total_count: totalCount, offset, limit: 200 };
}

beforeEach(() => {
  vi.mocked(searchFacilities).mockReset().mockResolvedValue(page([row]));
});

describe("Change Request to editing workspace chooser", () => {
  it("forms an exact Search history deep link including the user-chosen line identity", async () => {
    mount();
    expect(searchFacilities).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Chọn ngữ cảnh xử lý" }));
    const link = await screen.findByRole("link", { name: "Mở ngữ cảnh này" });
    expect(searchFacilities).toHaveBeenCalledWith(
      { site_id: "site-1", offset: 0, limit: 200 }, expect.anything(), true, null,
    );
    const target = new URL(link.getAttribute("href")!, "https://app.test");
    expect(target.pathname).toBe("/search");
    expect(target.searchParams.get("site_id")).toBe("site-1");
    expect(target.searchParams.get("result_key")).toBe(row.result_key);
    expect(target.searchParams.get("gxp_type")).toBe("GMP");
    expect(target.searchParams.get("context_gxp")).toBe("GMP");
    expect(target.searchParams.get("history_id")).toBe("cr-uuid");
    expect(target.searchParams.get("production_line_id")).toBe("line-1");
    expect(target.searchParams.get("line_code")).toBe("L1");
    expect(target.searchParams.get("event_tab")).toBe("Đề nghị");
  });

  it("does not invent a GxP or line on site-only Change Request context", async () => {
    const emptyGxp = { ...row, result_key: "site-only", result_grain: "facility" as const,
      gxp_type: null as unknown as string, line_code: null,
      production_line_id: null, production_line_identity_state: "facility_wide" as const };
    vi.mocked(searchFacilities).mockResolvedValue(page([emptyGxp]));
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Chọn ngữ cảnh xử lý" }));
    expect(await screen.findByText("Không hỗ trợ")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Mở ngữ cảnh này" })).not.toBeInTheDocument();
    expect(changeRequestSearchLink(emptyGxp, "site-1", "cr-uuid")).toBeNull();
  });

  it("fails closed on cross-Site data instead of navigating to unrelated Site", async () => {
    vi.mocked(searchFacilities).mockResolvedValue(page([{ ...row, site_id: "site-2" }]));
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Chọn ngữ cảnh xử lý" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("không khớp Site");
    expect(screen.queryByRole("link", { name: "Mở ngữ cảnh này" })).not.toBeInTheDocument();
  });

  it("rejects incomplete pages and duplicate canonical result keys", async () => {
    vi.mocked(searchFacilities).mockResolvedValueOnce(page([row], 2))
      .mockResolvedValueOnce(page([{ ...row }], 2, 1));
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Chọn ngữ cảnh xử lý" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("trùng");
    expect(screen.queryByRole("link", { name: "Mở ngữ cảnh này" })).not.toBeInTheDocument();
  });

  it("rejects a missing next page, over-limit totals and invalid line identities", async () => {
    vi.mocked(searchFacilities).mockResolvedValueOnce(page([], 1, 0));
    const { unmount } = mount();
    fireEvent.click(screen.getByRole("button", { name: "Chọn ngữ cảnh xử lý" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("không đầy đủ");
    unmount();
    vi.mocked(searchFacilities).mockResolvedValueOnce(page([row], 10001, 0));
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Chọn ngữ cảnh xử lý" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("không đầy đủ");
    expect(changeRequestSearchLink({ ...row, production_line_id: null }, "site-1", "cr-uuid")).toBeNull();
    expect(changeRequestSearchLink({ ...row, site_id: "site-2" }, "site-1", "cr-uuid")).toBeNull();
  });

  it("does not request a protected list when session has expired", () => {
    mount({ ...access, canLoadSecureApi: false });
    fireEvent.click(screen.getByRole("button", { name: "Chọn ngữ cảnh xử lý" }));
    expect(searchFacilities).not.toHaveBeenCalled();
    expect(screen.queryByRole("link", { name: "Mở ngữ cảnh này" })).not.toBeInTheDocument();
  });

  it("renders multiple distinct GxP contexts for explicit operator choice", async () => {
    vi.mocked(searchFacilities).mockResolvedValue(page([
      row, { ...row, result_key: "site-1:GLP:facility", gxp_type: "GLP", context_code: "GLP",
        result_grain: "facility", production_line_identity_state: "facility_wide",
        production_line_id: null, line_code: null },
    ]));
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Chọn ngữ cảnh xử lý" }));
    await waitFor(() => expect(screen.getAllByRole("link", { name: "Mở ngữ cảnh này" })).toHaveLength(2));
    expect(screen.getByText("GMP-L1")).toBeInTheDocument();
    expect(screen.getAllByText("GLP")).toHaveLength(2);
  });
});
