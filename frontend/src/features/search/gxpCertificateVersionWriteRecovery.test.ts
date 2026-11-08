import { describe, expect, it } from "vitest";

import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";
import { raiseGxpCertificateVersionWriteFailure, raiseGxpCertificatePromotionFailure } from "./gxpCertificateVersionWriteRecovery";

describe("GxP certificate latest-version write outcome classification", () => {
  it.each([
    ["canonical readback failure after accepted POST", true, Object.assign(new Error("GET failed"), { status: 404 })],
    ["network failure with no response", false, new TypeError("connection closed")],
    ["server error with unknown commit outcome", false, Object.assign(new Error("server failure"), { status: 503 })],
  ])("requires reconciliation for %s", (_label, accepted, error) => {
    try {
      raiseGxpCertificateVersionWriteFailure(error, accepted);
      throw new Error("Expected recovery error");
    } catch (raised) {
      expect(raised).toBeInstanceOf(CaseFieldMutationRecoveryError);
      expect((raised as Error).message).toContain("Không gửi lại");
      expect((raised as Error).cause).toBe(error);
    }
  });

  it.each([
    ["accepted promotion but canonical GET failed", true, Object.assign(new Error("unreadable current"), { status: 404 })],
    ["transport uncertainty before response", false, new TypeError("socket closed")],
    ["unknown server promotion outcome", false, Object.assign(new Error("server failure"), { status: 502 })],
  ])("requires reconciliation for %s", (_label, accepted, error) => {
    try {
      raiseGxpCertificatePromotionFailure(error, accepted);
      throw new Error("Expected recovery error");
    } catch (raised) {
      expect(raised).toBeInstanceOf(CaseFieldMutationRecoveryError);
      expect((raised as Error).message).toContain("Không gửi lại");
      expect((raised as Error).cause).toBe(error);
    }
  });

  it.each([401, 403, 409, 422])("retains a definitive pre-promotion %s rejection", status => {
    const error = Object.assign(new Error("rejected"), { status });
    expect(() => raiseGxpCertificatePromotionFailure(error, false)).toThrow(error);
  });

  it.each([401, 403, 409, 422])("retains a definitive pre-write %s rejection", status => {
    const rejected = Object.assign(new Error("Definitively rejected"), { status });
    expect(() => raiseGxpCertificateVersionWriteFailure(rejected, false)).toThrow(rejected);
  });
});
