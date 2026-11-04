import { describe, expect, it, vi } from "vitest";
import type { FacilitySearchPage, FacilitySearchResult } from "../../types";
import { collectFacilityReport, facilityReportCsv, REPORT_MAX_ROWS } from "./facilityReportExport";

function row(index: number, name = "Cơ sở " + index): FacilitySearchResult {
  return {
    result_key: "key-" + index, site_id: "site-" + index,
    legacy_site_id: index, facility_code: "F" + index,
    context_code: null, result_grain: "facility", gxp_type: "GMP",
    line_code: null, facility_name: name, company_name: "Công ty " + index,
    gxp_types: ["GMP"], certificate_scope_summary: null,
    province_name: null, last_inspection_on: null, current_state: null,
    current_certificate_number: null, current_certificate_expiry: null,
  };
}
function page(items: FacilitySearchResult[], offset: number, total_count: number): FacilitySearchPage {
  return { items, offset, limit: 100, total_count };
}

describe("authorized facility report export", () => {
  it("fetches all pages, not just the first 100 results", async () => {
    const rows = Array.from({ length: 205 }, (_, i) => row(i));
    const fetch = vi.fn(async (offset: number, limit: number) =>
      page(rows.slice(offset, offset + limit), offset, rows.length));
    const result = await collectFacilityReport(fetch);
    expect(result).toEqual(rows);
    expect(fetch.mock.calls.map(([offset]) => offset)).toEqual([0, 100, 200]);
  });

  it("allows a genuinely empty result without extra API calls", async () => {
    const fetch = vi.fn(async () => page([], 0, 0));
    expect(await collectFacilityReport(fetch)).toEqual([]);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("fails closed on changing totals, duplicate identities or missing pages", async () => {
    const rows = Array.from({ length: 100 }, (_, i) => row(i));
    await expect(collectFacilityReport(async offset =>
      offset === 0 ? page(rows, 0, 101) : page([row(100)], 100, 102),
    )).rejects.toThrow("thay đổi");
    await expect(collectFacilityReport(async offset =>
      offset === 0 ? page(rows, 0, 101) : page([row(0)], 100, 101),
    )).rejects.toThrow("trùng");
    await expect(collectFacilityReport(async offset =>
      offset === 0 ? page(rows, 0, 101) : page([], 100, 101),
    )).rejects.toThrow("trang rỗng");
    await expect(collectFacilityReport(async () =>
      page([], 0, REPORT_MAX_ROWS + 1),
    )).rejects.toThrow("quá lớn");
  });

  it("rejects wrong offsets and stops when access generation changes", async () => {
    await expect(collectFacilityReport(async () => page([row(0)], 1, 1)))
      .rejects.toThrow("không hợp lệ");
    let current = true;
    await expect(collectFacilityReport(async () => {
      current = false;
      return page([row(0)], 0, 1);
    }, () => current)).rejects.toThrow("Phiên truy cập");
  });

  it("produces UTF-8 Excel-compatible CSV and neutralizes formulas", () => {
    const csv = facilityReportCsv([row(1, '=HYPERLINK("https://evil.example")'), row(2, "\t+SUM(1,2)")]);
    expect(csv.startsWith("\uFEFF")).toBe(true);
    expect(csv).toContain('"\'=HYPERLINK(""https://evil.example"")"');
    expect(csv).toContain('"\'\t+SUM(1,2)"');
    expect(csv).toContain("\r\n");
    expect(csv.split("\r\n").filter(Boolean)).toHaveLength(3);
  });
});
