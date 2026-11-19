import { describe, expect, it } from "vitest";

import { reportReturnLocation } from "./reportReturnLocation";

describe("canonical report return locations", () => {
  it("keeps an exact internal Change Request report page", () => {
    const origin = "/reports?report=change_requests&state=under_review&q=site&offset=100";

    expect(reportReturnLocation({ reportReturn: origin }, "change_requests")).toBe(origin);
  });

  it.each([
    "/reports?report=certificates&gxp_type=GMP&gxp_type=GLP",
    "/reports?report=certificates&expiry_days=45",
    "/reports?report=change_requests&state=completed",
    "/reports?report=change_requests&offset=1",
    "/reports?report=change_requests&offset=100&offset=200",
    "/reports?report=change_requests&site_id=foreign-site",
  ])("rejects a malformed report return hint: %s", value => {
    expect(reportReturnLocation({ reportReturn: value }, value.includes("certificates") ? "certificates" : "change_requests")).toBeNull();
  });
});
