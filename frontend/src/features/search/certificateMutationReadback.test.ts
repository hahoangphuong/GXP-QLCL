import { describe, expect, it } from "vitest";
import type {
  GxpCertificateDetail, GxpCertificateListItem,
  BusinessEligibilityDetail, BusinessEligibilityListItem,
} from "../../types";
import {
  assertGxpCertificateMutationReadback,
  assertEligibilityCertificateMutationReadback,
} from "./certificateMutationReadback";

const gxpRow = {
  certificate_id: "cert-A", site_id: "site-A", case_id: "case-A",
  certificate_type: "GMP", production_line_id: "line-A",
  production_line_identity_state: "canonical", latest_flag: true,
} as GxpCertificateListItem;
const gxpDetail = { ...gxpRow } as GxpCertificateDetail;
const ddkRow = {
  business_eligibility_certificate_id: "ddk-A", site_id: "site-A",
  company_id: "company-A", latest_flag: true,
} as BusinessEligibilityListItem;
const ddkDetail = { ...ddkRow } as BusinessEligibilityDetail;

describe("canonical Certificate mutation readback", () => {
  it("accepts exact GxP UUID/site/type/Case/line membership and confirmed current flag", () => {
    expect(() => assertGxpCertificateMutationReadback("cert-A", "site-A", "GMP", gxpDetail, [gxpRow], true)).not.toThrow();
  });

  it.each([
    ["wrong detail UUID", { certificate_id: "cert-B" }, gxpRow],
    ["wrong Site", { site_id: "site-B" }, gxpRow],
    ["wrong GxP", { certificate_type: "GLP" }, gxpRow],
    ["wrong Case", { case_id: "case-B" }, gxpRow],
    ["wrong production line", { production_line_id: "line-B" }, gxpRow],
    ["missing canonical list membership", {}, { ...gxpRow, certificate_id: "cert-B" }],
  ])("rejects GxP %s without accepting the mutation readback", (_label, override, row) => {
    expect(() => assertGxpCertificateMutationReadback(
      "cert-A", "site-A", "GMP", { ...gxpDetail, ...override }, [row],
    )).toThrow(/không khớp/);
  });

  it("does not call a promotion confirmed while canonical detail or list still says non-current", () => {
    expect(() => assertGxpCertificateMutationReadback("cert-A", "site-A", "GMP",
      { ...gxpDetail, latest_flag: false }, [gxpRow], true)).toThrow(/hiện hành/);
    expect(() => assertGxpCertificateMutationReadback("cert-A", "site-A", "GMP",
      gxpDetail, [{ ...gxpRow, latest_flag: false }], true)).toThrow(/hiện hành/);
    // Non-current latest-version edits are valid operations when identity agrees.
    expect(() => assertGxpCertificateMutationReadback("cert-A", "site-A", "GMP",
      { ...gxpDetail, latest_flag: false }, [{ ...gxpRow, latest_flag: false }])).not.toThrow();
  });

  it("accepts exact business-eligibility membership and current status", () => {
    expect(() => assertEligibilityCertificateMutationReadback("ddk-A", "site-A", ddkDetail, [ddkRow], true)).not.toThrow();
  });

  it.each([
    ["wrong UUID", { business_eligibility_certificate_id: "ddk-B" }, ddkRow],
    ["wrong Site", { site_id: "site-B" }, ddkRow],
    ["wrong company", { company_id: "company-B" }, ddkRow],
    ["missing list record", {}, { ...ddkRow, business_eligibility_certificate_id: "ddk-B" }],
  ])("rejects business-eligibility %s", (_label, override, row) => {
    expect(() => assertEligibilityCertificateMutationReadback("ddk-A", "site-A", { ...ddkDetail, ...override }, [row]))
      .toThrow(/không khớp/);
  });

  it("does not accept an unconfirmed business-eligibility current promotion", () => {
    expect(() => assertEligibilityCertificateMutationReadback("ddk-A", "site-A",
      { ...ddkDetail, latest_flag: false }, [ddkRow], true)).toThrow(/hiện hành/);
    expect(() => assertEligibilityCertificateMutationReadback("ddk-A", "site-A",
      ddkDetail, [{ ...ddkRow, latest_flag: false }], true)).toThrow(/hiện hành/);
  });
});
