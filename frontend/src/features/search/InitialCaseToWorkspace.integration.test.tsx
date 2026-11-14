import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getSite: vi.fn(), getCompany: vi.fn(), listSiteProductionLines: vi.fn(),
  getFacilityWorkspace: vi.fn(), createInitialCase: vi.fn(),
  getCaseDetail: vi.fn(), getCaseWorkspace: vi.fn(),
}));
vi.mock("../../lib/api", () => api);

import type { ApiAccess } from "../../App";
import { CaseDirectOpen } from "../../pages/CaseDirectOpen";
import { CatalogCreateSessionRoot } from "./CatalogCreateSession";
import { InitialCaseCreationDialog } from "./InitialCaseCreationDialog";

const siteId = "site-canonical";
const companyId = "company-canonical";
const caseId = "case-new-uuid";
const lineId = "physical-line-uuid";
const auth = { username: "synthetic-operator", role: "admin" as const };
const access: ApiAccess = {
  auth, useStubAuth: true, bearerToken: null, canLoadSecureApi: true, accessGeneration: 17,
};
const site = { id: siteId, company_id: companyId, site_name: "Cơ sở mới", site_address: "Hà Nội" };
const company = { id: companyId, legal_name: "Công ty mới", is_inactive: false };
const line = { id: lineId, site_id: siteId, code: "L1", effective_from: "2026-01-01", effective_to: null, row_version: 1 };

function Entrypoint() {
  const navigate = useNavigate();
  return <InitialCaseCreationDialog
    open siteId={siteId} auth={auth} useStubAuth bearerToken={null} accessGeneration={17}
    onClose={() => {}} onVerifiedOpen={(id) => navigate(`/cases/${encodeURIComponent(id)}`)}
  />;
}
function Destination() {
  const location = useLocation();
  return <output data-testid="verified-workspace-url">{location.pathname + location.search}</output>;
}
function mount() {
  return render(<CatalogCreateSessionRoot><MemoryRouter initialEntries={["/new"]}>
    <Routes>
      <Route path="/new" element={<Entrypoint />} />
      <Route path="/cases/:caseId" element={<CaseDirectOpen access={access} />} />
      <Route path="/search" element={<Destination />} />
    </Routes>
  </MemoryRouter></CatalogCreateSessionRoot>);
}

async function createDraft(selectedLine: string | null) {
  await screen.findByText(/Cơ sở: /);
  fireEvent.change(screen.getByLabelText("Loại GxP cho hồ sơ mới"), { target: { value: "GMP" } });
  if (selectedLine) {
    fireEvent.change(screen.getByLabelText("ProductionLine UUID"), { target: { value: selectedLine } });
  }
  await waitFor(() => expect(api.getFacilityWorkspace).toHaveBeenCalledWith(
    siteId, auth, true, "GMP", null, null, selectedLine,
  ));
  fireEvent.change(screen.getByLabelText("Loại kiểm tra hồ sơ đầu tiên"), { target: { value: "Mới" } });
  fireEvent.change(screen.getByLabelText("Tiêu chuẩn áp dụng"), { target: { value: "WHO-GMP" } });
  fireEvent.change(screen.getByLabelText("Lý do tạo hồ sơ đầu tiên"), { target: { value: "Hồ sơ đầu tiên" } });
  fireEvent.click(screen.getByLabelText("Xác nhận chỉ tạo Case Draft"));
  await waitFor(() => expect((screen.getByRole("button", { name: "Tạo hồ sơ Draft" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "Tạo hồ sơ Draft" }));
  await screen.findByText(/Case nháp canonical đã xác minh/);
}

beforeEach(() => {
  // Each Vitest scenario gets an independent tab journal, as a new browser tab would.
  window.sessionStorage.clear();
  vi.restoreAllMocks();
  vi.stubGlobal("crypto", { randomUUID: vi.fn(() => caseId) });
  api.getSite.mockResolvedValue(site);
  api.getCompany.mockResolvedValue(company);
  api.listSiteProductionLines.mockResolvedValue([line]);
  api.createInitialCase.mockResolvedValue({ case_id: caseId });
  api.getFacilityWorkspace.mockImplementation((_site: string, _auth: unknown, _stub: boolean, gxp: string, _code: unknown, _token: unknown, selectedLine: string | null) => Promise.resolve({
    summary: { site_id: siteId, selected_gxp_type: gxp, selected_production_line_id: selectedLine },
    action_readiness: [{ action_key: "create_initial_case", label: "Hồ sơ mới",
      readiness_status: "available", detail: "Tạo Case nháp", required_permissions: ["case.edit"] }],
  }));
});

describe("operator's first Case -> canonical direct-open -> workspace routing", () => {
  it.each([
    ["facility-wide", null],
    ["explicit physical line", lineId],
  ])("opens the exact new Draft Case without guessing %s identity", async (_label, selectedLine) => {
    api.getCaseDetail.mockResolvedValue({
      id: caseId, site_id: siteId, gxp_type: "GMP",
      production_line_id: selectedLine, inspection_type: "Mới", applicable_standard: "WHO-GMP",
      state: "draft", legacy_inspection_id: null, legacy_inspection_code: null,
    });
    api.getCaseWorkspace.mockResolvedValue({
      case_summary: {
        id: caseId, site_id: siteId, gxp_type: "GMP", state: "draft",
        production_line_id: selectedLine,
        production_line_code: selectedLine ? "L1" : null,
        production_line_identity_state: selectedLine ? "canonical" : "facility_wide",
      },
    });
    mount();
    await createDraft(selectedLine);
    expect(api.createInitialCase).toHaveBeenCalledTimes(1);
    expect(api.createInitialCase.mock.calls[0][1]).toMatchObject({
      case_id: caseId, production_line_id: selectedLine, gxp_type: "GMP",
    });
    // Explicit operator navigation after the persisted Case GET, never an automatic redirect on POST.
    expect(api.getCaseWorkspace).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Mở Case workspace" }));
    const link = new URL((await screen.findByTestId("verified-workspace-url")).textContent!, "https://synthetic.test");
    expect(link.pathname).toBe("/search");
    expect(link.searchParams.get("history_id")).toBe(caseId);
    expect(link.searchParams.get("site_id")).toBe(siteId);
    expect(link.searchParams.get("gxp_type")).toBe("GMP");
    expect(link.searchParams.get("production_line_id")).toBe(selectedLine);
    expect(link.searchParams.has("line_code")).toBe(Boolean(selectedLine));
    expect(api.getCaseWorkspace).toHaveBeenCalledTimes(1);
    expect(api.getCaseWorkspace).toHaveBeenCalledWith(caseId, auth, true, null);
  });

  it("refuses to open a canonical Case whose workspace resolves to a different Site", async () => {
    api.getCaseDetail.mockResolvedValue({
      id: caseId, site_id: siteId, gxp_type: "GMP",
      production_line_id: null, inspection_type: "Mới", applicable_standard: "WHO-GMP",
      state: "draft", legacy_inspection_id: null, legacy_inspection_code: null,
    });
    api.getCaseWorkspace.mockResolvedValue({
      case_summary: { id: "foreign-case", site_id: "other-site", gxp_type: "GMP",
        production_line_id: null, production_line_code: null,
        production_line_identity_state: "facility_wide", state: "draft" },
    });
    mount();
    await createDraft(null);
    fireEvent.click(screen.getByRole("button", { name: "Mở Case workspace" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Hồ sơ trả về không khớp định danh");
    expect(screen.queryByTestId("verified-workspace-url")).toBeNull();
    expect(api.createInitialCase).toHaveBeenCalledTimes(1);
  });
});
