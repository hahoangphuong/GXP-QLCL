import { describe, expect, it } from "vitest";

import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";
import { raiseBusinessEligibilityWriteFailure } from "./businessEligibilityWriteRecovery";

describe("business-eligibility Certificate write outcome", () => {
  it.each(["version", "promotion"] as const)("fences %s when the accepted POST cannot be read back", operation => {
    const error = Object.assign(new Error("GET after POST failed"), { status: 404 });
    try { raiseBusinessEligibilityWriteFailure(error, true, operation); }
    catch (caught) {
      expect(caught).toBeInstanceOf(CaseFieldMutationRecoveryError);
      expect((caught as Error).cause).toBe(error);
      expect((caught as Error).message).toContain("Không gửi lại");
      return;
    }
    throw new Error("Expected an unverified-outcome error");
  });

  it.each(["version", "promotion"] as const)("fences %s on unknown network or server outcomes", operation => {
    for (const error of [new TypeError("network closed"), Object.assign(new Error("gateway"), { status: 502 })]) {
      expect(() => raiseBusinessEligibilityWriteFailure(error, false, operation)).toThrow(CaseFieldMutationRecoveryError);
    }
  });

  it.each(["version", "promotion"] as const)("preserves definitive pre-write errors for %s", operation => {
    for (const status of [401, 403, 409, 422]) {
      const error = Object.assign(new Error("Rejected"), { status });
      expect(() => raiseBusinessEligibilityWriteFailure(error, false, operation)).toThrow(error);
    }
  });
});
