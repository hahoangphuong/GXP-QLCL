import { describe, expect, it } from "vitest";
import { buildOperationalReportQuery, INITIAL_REPORT_FILTERS, reportExportFilename, type ReportFilters } from "./reportCatalog";

function query(kind: ReportFilters["kind"], expiry_days: ReportFilters["expiry_days"] = 90) {
  return buildOperationalReportQuery({ ...INITIAL_REPORT_FILTERS, kind, expiry_days, q: "  cơ sở A ", province: " Hà Nội " });
}

describe("operational report predicates are the existing dashboard facility contracts", () => {
  it("keeps the generic facility list unrestricted by lifecycle", () => {
    expect(query("facilities")).toEqual({ gxp_type: "GMP", q: "cơ sở A", province: "Hà Nội" });
  });

  it("matches the dashboard's unfinished Case set (facility grain, not Case grain)", () => {
    expect(query("active_cases")).toEqual({
      gxp_type: "GMP", q: "cơ sở A", province: "Hà Nội",
      case_state: ["draft", "application_received", "under_assessment", "planned", "decision_issued",
        "inspection_in_progress", "inspection_completed", "awaiting_certificate_decision"],
    });
  });

  it("selects inspection-stage and certificate-decision Case facilities without inventing Case rows", () => {
    expect(query("inspection")).toMatchObject({
      case_state: ["planned", "decision_issued", "inspection_in_progress"],
    });
    expect(query("certificate_decision")).toMatchObject({ case_state: ["awaiting_certificate_decision"] });
  });

  it("filters current active expiring certificate contexts with the requested 30/60/90 day window", () => {
    for (const days of [30, 60, 90] as const) {
      expect(query("expiring_certificates", days)).toMatchObject({
        certificate_state: "active", certificate_expiring_within_days: days,
      });
      expect(reportExportFilename({ ...INITIAL_REPORT_FILTERS, kind: "expiring_certificates", expiry_days: days }))
        .toBe(`bao-cao-expiring_certificates-GMP-${days}ngay.csv`);
    }
  });

  it("uses only backed Change Request unfinished states", () => {
    expect(query("open_changes")).toMatchObject({ change_request_state: ["received", "under_review"] });
    expect(query("open_changes")).not.toHaveProperty("case_state");
  });

  it("keeps the query free of report-kind client-only fields", () => {
    for (const kind of ["facilities", "active_cases", "inspection", "certificate_decision", "expiring_certificates", "open_changes"] as const) {
      const predicate = query(kind);
      expect(predicate).not.toHaveProperty("kind");
      expect(predicate).not.toHaveProperty("expiry_days");
    }
  });
});
