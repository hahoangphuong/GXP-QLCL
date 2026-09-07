import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CaseWorkspace } from "../../types";
import { CaseApplicationWorkspace } from "./CaseApplicationWorkspace";

const workspace = {
  case_summary: {
    id: "case-139",
    row_version: 1,
    legacy_inspection_id: 139,
    legacy_inspection_code: "KT-139-GMP",
    site_id: "site-16",
    legacy_site_id: 16,
    facility_name: "Cơ sở kiểm tra",
    company_name: "Công ty kiểm tra",
    gxp_type: "GMP",
    scope_code: null,
    applicable_standard: null,
    inspection_type: null,
    state: "inspection_completed",
    opened_year: 2018,
  },
  application: { row_version: null, submitted_on: null, dossier_code: null, dossier_reference: null, applicant_name: null, assigned_specialist: null, assigned_specialist_source: null },
} as CaseWorkspace;

describe("CaseApplicationWorkspace inspection-folder lookup", () => {
  it("surfaces AMBIGUOUS without auto-selecting a folder", async () => {
    const onResolveInspectionFolder = vi.fn().mockResolvedValue({
      status: "ambiguous",
      candidate_count: 2,
      relative_path: null,
    });
    render(<CaseApplicationWorkspace caseWorkspace={workspace} onResolveInspectionFolder={onResolveInspectionFolder} onSave={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("không chọn tự động");
    expect(onResolveInspectionFolder).toHaveBeenCalledOnce();
    expect(screen.queryByText("Đã tìm thấy thư mục:")).not.toBeInTheDocument();
  });

  it("surfaces NOT_FOUND without fallback", async () => {
    render(
      <CaseApplicationWorkspace
        caseWorkspace={workspace}
        onResolveInspectionFolder={vi.fn().mockResolvedValue({ status: "not_found", candidate_count: 0, relative_path: null })}
        onSave={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy thư mục kiểm tra khớp chính xác");
  });
});
