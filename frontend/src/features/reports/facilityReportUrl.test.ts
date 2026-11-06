import { describe, expect, it } from "vitest";
import { parseFacilityReportLocation, writeFacilityReportLocation } from "./facilityReportUrl";

describe("facility report URL ownership", () => {
  it("restores a valid GxP, query, province and page without dropping unrelated context", () => {
    const initial = new URLSearchParams("source=workflow&report=facilities");
    const next = writeFacilityReportLocation(initial, {
      filters: { gxp_type: "GLP", q: "Hà Nội", province: "Hải Phòng" }, offset: 200,
    });
    expect(next.get("source")).toBe("workflow");
    expect(parseFacilityReportLocation(next)).toEqual({
      filters: { gxp_type: "GLP", q: "Hà Nội", province: "Hải Phòng" }, offset: 200,
    });
    expect(writeFacilityReportLocation(next, { filters: { gxp_type: "GMP", q: "", province: "" }, offset: 0 }).toString())
      .toContain("report=facilities");
  });

  it.each([
    "gxp_type=GSP",
    "gxp_type=GMP&gxp_type=GLP",
    "q=one&q=two",
    "province=A&province=B",
    "offset=1",
    "offset=1.0",
    "offset=-100",
    "offset=00100",
    "offset=9007199254741000",
    "offset=100&offset=200",
    "q=%00",
    "q=%E2%80%AE",
    "province=%0A",
  ])("rejects malformed bookmark %s before any facility query", query => {
    expect(parseFacilityReportLocation(new URLSearchParams(query))).toBeNull();
  });
});
