import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import type { ApiAccess } from "../../App";
import { getCertificateReport, getCaseWorkspace } from "../../lib/api";
import { CaseDirectOpen } from "../../pages/CaseDirectOpen";
import { CanonicalRecordReport } from "./CanonicalRecordReport";

vi.mock("../../lib/api", () => ({
  getCertificateReport: vi.fn(), getCaseWorkspace: vi.fn(),
  getChangeRequestReport: vi.fn(),
}));
const access: ApiAccess = {
  auth: { username: "reader", role: "reader" }, useStubAuth: true,
  bearerToken: null, canLoadSecureApi: true, accessGeneration: 1,
};
const reportRow = {
  certificate_id: "cert-uuid", certificate_version_id: "version-uuid",
  result_key: "site-uuid:GSP:facility_wide:", site_id: "site-uuid", case_id: "case-uuid",
  production_line_id: null, line_code: null, facility_name: "Cơ sở",
  company_name: "Công ty", gxp_type: "GSP", certificate_number: "GSP-TEST",
  issue_date: null, expiry_date: null, lifecycle_state: "GRANTED", status: "active",
};
function caseWorkspace(certificateSiteId = "site-uuid") {
  return {
    case_summary: {
      id: "case-uuid", site_id: "site-uuid", gxp_type: "GSP",
      production_line_id: null, production_line_code: null,
      production_line_identity_state: "facility_wide", state: "closed",
    },
    linked_gxp_certificates: [{
      certificate_id: "cert-uuid", site_id: certificateSiteId, case_id: "case-uuid",
      certificate_type: "GSP",
    }],
  } as Awaited<ReturnType<typeof getCaseWorkspace>>;
}
function Destination() {
  const location = useLocation();
  return <output data-testid="resolved-search">{location.pathname + location.search}</output>;
}
function mount() {
  render(<MemoryRouter initialEntries={["/reports?report=certificates"]}><Routes>
    <Route path="/reports" element={<CanonicalRecordReport access={access} kind="certificates" />} />
    <Route path="/cases/:caseId" element={<CaseDirectOpen access={access} />} />
    <Route path="/search" element={<Destination />} />
  </Routes></MemoryRouter>);
}
beforeEach(() => {
  vi.mocked(getCertificateReport).mockReset().mockResolvedValue({
    items: [reportRow], total_count: 1, limit: 100, offset: 0,
  });
  vi.mocked(getCaseWorkspace).mockReset();
});

it("navigates report Certificate → authoritative Case GET → exact Case/Certificate tab with no mutation", async () => {
  vi.mocked(getCaseWorkspace).mockResolvedValue(caseWorkspace());
  mount();
  fireEvent.click(await screen.findByRole("link", { name: "Mở Case" }));
  const value = (await screen.findByTestId("resolved-search")).textContent!;
  const url = new URL(value, "https://example.test");
  expect(url.pathname).toBe("/search");
  expect(url.searchParams.get("history_id")).toBe("case-uuid");
  expect(url.searchParams.get("site_id")).toBe("site-uuid");
  expect(url.searchParams.get("gxp_type")).toBe("GSP");
  expect(url.searchParams.get("event_tab")).toBe("Chứng nhận GxP");
  expect(getCaseWorkspace).toHaveBeenCalledOnce();
  expect(getCaseWorkspace).toHaveBeenCalledWith("case-uuid", expect.anything(), true, null);
});

it("does not navigate if the Case's independent linked Certificate Site disagrees with the report hint", async () => {
  vi.mocked(getCaseWorkspace).mockResolvedValue(caseWorkspace("foreign-site"));
  mount();
  fireEvent.click(await screen.findByRole("link", { name: "Mở Case" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Case không khớp chứng nhận và Site canonical");
  expect(screen.queryByTestId("resolved-search")).not.toBeInTheDocument();
});
