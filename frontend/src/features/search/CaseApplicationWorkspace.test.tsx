import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
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

  it("renders a resolved relative path", async () => {
    render(
      <CaseApplicationWorkspace
        caseWorkspace={workspace}
        onResolveInspectionFolder={vi.fn().mockResolvedValue({
          status: "resolved",
          candidate_count: 1,
          relative_path: "2024/Facility - (ID-16) - (KT-139-GMP)",
        })}
        onSave={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" }));

    expect(await screen.findByText("Đã tìm thấy thư mục: 2024/Facility - (ID-16) - (KT-139-GMP)")).toBeInTheDocument();
  });

  it("surfaces INVALID as an anchor state rather than a storage failure", async () => {
    render(
      <CaseApplicationWorkspace
        caseWorkspace={workspace}
        onResolveInspectionFolder={vi.fn().mockResolvedValue({ status: "invalid", candidate_count: 0, relative_path: null })}
        onSave={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Không đủ định danh legacy");
    expect(screen.queryByText("Không thể truy cập lưu trữ:")).not.toBeInTheDocument();
  });

  it("prevents duplicate submissions while the lookup is pending", async () => {
    let resolveLookup: (value: {
      status: "resolved";
      candidate_count: number;
      relative_path: string;
      source: string;
      detail: string | null;
      storage_class: string;
    }) => void;
    const onResolveInspectionFolder = vi.fn(
      () => new Promise<{
        status: "resolved";
        candidate_count: number;
        relative_path: string;
        source: string;
        detail: string | null;
        storage_class: string;
      }>((resolve) => {
        resolveLookup = resolve;
      }),
    );
    render(<CaseApplicationWorkspace caseWorkspace={workspace} onResolveInspectionFolder={onResolveInspectionFolder} onSave={vi.fn()} />);

    const button = screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" });
    fireEvent.click(button);
    fireEvent.click(button);

    expect(onResolveInspectionFolder).toHaveBeenCalledOnce();
    expect(button).toBeDisabled();
    await act(async () => {
      resolveLookup!({
        status: "resolved",
        candidate_count: 1,
        relative_path: "2024/folder",
        source: "live_resolution",
        detail: null,
        storage_class: "synology_legacy",
      });
    });
  });

  it("keeps infrastructure failures distinct from semantic lookup states", async () => {
    render(
      <CaseApplicationWorkspace
        caseWorkspace={workspace}
        onResolveInspectionFolder={vi.fn().mockRejectedValue(new Error("SMB unavailable"))}
        onSave={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Không thể truy cập lưu trữ: SMB unavailable");
    expect(screen.queryByText("Không đủ định danh legacy")).not.toBeInTheDocument();
  });
});
