import { describe, expect, it } from "vitest";

import { formatCompactDate, formatFacilityNameForGrid } from "./presentation";

describe("presentation helpers", () => {
  it("abbreviates longer overlapping facility phrases before shorter ones", () => {
    expect(formatFacilityNameForGrid("Công ty cổ phần trang thiết bị y tế và sinh phẩm y tế")).toBe(
      "Cty CP TTBYT và SPYT",
    );
    expect(formatFacilityNameForGrid("Chi nhánh sản xuất và thương mại dược phẩm")).toBe("CN SX và TM DP");
  });

  it("formats date strings as dd-mm-yyyy without changing owner data", () => {
    expect(formatCompactDate("2026-07-21")).toBe("21-07-2026");
    expect(formatCompactDate("2026-07-21T00:00:00+00:00")).toBe("21-07-2026");
    expect(formatCompactDate(null)).toBe("Chưa có");
  });
});
