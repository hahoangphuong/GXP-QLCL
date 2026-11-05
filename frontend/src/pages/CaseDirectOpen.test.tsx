import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess, } from "../App";
import { getCaseWorkspace } from "../lib/api";
import { CaseDirectOpen } from "./CaseDirectOpen";

vi.mock("../lib/api", () => ({ getCaseWorkspace: vi.fn() }));
const access: ApiAccess = { auth: { username: "reader", role: "reader" },
  useStubAuth: true, bearerToken: null, canLoadSecureApi: true, accessGeneration: 1 };

function Destination() {
  const location = useLocation();
  return <output data-testid="resolved-url">{location.pathname + location.search}</output>;
}
function mount(url: string, currentAccess = access) {
  return render(<MemoryRouter initialEntries={[url]}><Routes>
    <Route path="/cases/:caseId" element={<CaseDirectOpen access={currentAccess} />} />
    <Route path="/search" element={<Destination />} />
  </Routes></MemoryRouter>);
}
function workspace(id: string, site = "site-uuid") {
  return {
    case_summary: { id, site_id: site, gxp_type: "GMP", production_line_id: "line-uuid", production_line_code: "L1" },
  } as Awaited<ReturnType<typeof getCaseWorkspace>>;
}

beforeEach(() => vi.mocked(getCaseWorkspace).mockReset());

describe("canonical Case UUID entry", () => {
  it("resolves a Case to exact site, GxP, line and history selection", async () => {
    vi.mocked(getCaseWorkspace).mockResolvedValue(workspace("case-uuid"));
    mount("/cases/case-uuid");
    const resolved = await screen.findByTestId("resolved-url");
    const uri = new URL(resolved.textContent!, "https://app.test");
    expect(uri.pathname).toBe("/search");
    expect(uri.searchParams.get("history_id")).toBe("case-uuid");
    expect(uri.searchParams.get("site_id")).toBe("site-uuid");
    expect(uri.searchParams.get("gxp_type")).toBe("GMP");
    expect(uri.searchParams.get("production_line_id")).toBe("line-uuid");
    expect(uri.searchParams.get("line_code")).toBe("L1");
  });

  it("refuses an incorrect returned Case UUID instead of selecting the wrong record", async () => {
    vi.mocked(getCaseWorkspace).mockResolvedValue(workspace("other-case"));
    mount("/cases/case-uuid");
    expect(await screen.findByRole("alert")).toHaveTextContent("không khớp định danh");
    expect(screen.queryByTestId("resolved-url")).not.toBeInTheDocument();
  });

  it("does not call protected API without access", () => {
    mount("/cases/case-uuid", { ...access, canLoadSecureApi: false });
    expect(screen.getByText("Cần đăng nhập")).toBeInTheDocument();
    expect(getCaseWorkspace).not.toHaveBeenCalled();
  });

  it("does not redirect when the canonical Case response lacks its Site identity", async () => {
    vi.mocked(getCaseWorkspace).mockResolvedValue(workspace("blocked-case", ""));
    mount("/cases/blocked-case");
    expect(await screen.findByRole("alert")).toHaveTextContent("thiếu ngữ cảnh");
    expect(screen.queryByTestId("resolved-url")).not.toBeInTheDocument();
  });
});
