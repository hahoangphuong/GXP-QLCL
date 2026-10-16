import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CaseWorkspace, InspectionFolderLookup } from "../../types";
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

function withIdentity(overrides: Partial<CaseWorkspace["case_summary"]>): CaseWorkspace {
  return { ...workspace, case_summary: { ...workspace.case_summary, ...overrides } };
}

function resolved(relativePath: string): InspectionFolderLookup {
  return {
    status: "resolved",
    candidate_count: 1,
    relative_path: relativePath,
    source: "live_resolution",
    detail: null,
    storage_class: "synology_legacy",
  };
}

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

  it("rejects a late success from case A after switching to case B and releases B lookup", async () => {
    const pendingA = deferred<InspectionFolderLookup>();
    const onResolveInspectionFolder = vi.fn().mockReturnValueOnce(pendingA.promise).mockResolvedValueOnce(resolved("2025/B"));
    const onSave = vi.fn();
    const view = render(<CaseApplicationWorkspace caseWorkspace={workspace} onResolveInspectionFolder={onResolveInspectionFolder} onSave={onSave} />);

    fireEvent.click(screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" }));
    view.rerender(<CaseApplicationWorkspace caseWorkspace={withIdentity({ id: "case-B", site_id: "site-B", legacy_site_id: 17, legacy_inspection_code: "KT-B-GMP" })} onResolveInspectionFolder={onResolveInspectionFolder} onSave={onSave} />);

    const buttonB = screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" });
    expect(buttonB).toBeEnabled();
    await act(async () => pendingA.resolve(resolved("2024/A")));
    expect(screen.queryByText("Đã tìm thấy thư mục: 2024/A")).not.toBeInTheDocument();

    fireEvent.click(buttonB);
    expect(await screen.findByText("Đã tìm thấy thư mục: 2025/B")).toBeInTheDocument();
    expect(onResolveInspectionFolder).toHaveBeenCalledTimes(2);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("rejects a late infrastructure error from case A after switching to case B", async () => {
    const pendingA = deferred<InspectionFolderLookup>();
    const onResolveInspectionFolder = vi.fn().mockReturnValue(pendingA.promise);
    const view = render(<CaseApplicationWorkspace caseWorkspace={workspace} onResolveInspectionFolder={onResolveInspectionFolder} onSave={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" }));
    view.rerender(<CaseApplicationWorkspace caseWorkspace={withIdentity({ id: "case-B", site_id: "site-B", legacy_site_id: 17, legacy_inspection_code: "KT-B-GMP" })} onResolveInspectionFolder={onResolveInspectionFolder} onSave={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" })).toBeEnabled();

    await act(async () => pendingA.reject(new Error("A storage unavailable")));
    expect(screen.queryByText(/A storage unavailable/)).not.toBeInTheDocument();
  });

  it("owns A → B → A responses by operation generation rather than case ID alone", async () => {
    const firstA = deferred<InspectionFolderLookup>();
    const pendingB = deferred<InspectionFolderLookup>();
    const secondA = deferred<InspectionFolderLookup>();
    const onResolveInspectionFolder = vi.fn()
      .mockReturnValueOnce(firstA.promise)
      .mockReturnValueOnce(pendingB.promise)
      .mockReturnValueOnce(secondA.promise);
    const view = render(<CaseApplicationWorkspace caseWorkspace={workspace} onResolveInspectionFolder={onResolveInspectionFolder} onSave={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" }));
    view.rerender(<CaseApplicationWorkspace caseWorkspace={withIdentity({ id: "case-B", site_id: "site-B", legacy_site_id: 17, legacy_inspection_code: "KT-B-GMP" })} onResolveInspectionFolder={onResolveInspectionFolder} onSave={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" }));
    view.rerender(<CaseApplicationWorkspace caseWorkspace={{ ...workspace, case_summary: { ...workspace.case_summary } }} onResolveInspectionFolder={onResolveInspectionFolder} onSave={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" }));

    await act(async () => secondA.resolve(resolved("2026/A-generation-2")));
    expect(screen.getByText("Đã tìm thấy thư mục: 2026/A-generation-2")).toBeInTheDocument();
    await act(async () => pendingB.resolve(resolved("2025/B")));
    await act(async () => firstA.resolve(resolved("2024/A-generation-1")));
    expect(screen.getByText("Đã tìm thấy thư mục: 2026/A-generation-2")).toBeInTheDocument();
    expect(screen.queryByText(/2025\/B|2024\/A-generation-1/)).not.toBeInTheDocument();
    expect(onResolveInspectionFolder).toHaveBeenCalledTimes(3);
  });

  it("preserves an owned result across a same-identity workspace refresh without another request", async () => {
    const onResolveInspectionFolder = vi.fn().mockResolvedValue(resolved("2024/A"));
    const view = render(<CaseApplicationWorkspace caseWorkspace={workspace} onResolveInspectionFolder={onResolveInspectionFolder} onSave={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" }));
    expect(await screen.findByText("Đã tìm thấy thư mục: 2024/A")).toBeInTheDocument();

    view.rerender(<CaseApplicationWorkspace caseWorkspace={{ ...workspace, application: { ...workspace.application, dossier_code: "REFRESHED" } }} onResolveInspectionFolder={onResolveInspectionFolder} onSave={vi.fn()} />);
    expect(screen.getByText("Đã tìm thấy thư mục: 2024/A")).toBeInTheDocument();
    expect(onResolveInspectionFolder).toHaveBeenCalledOnce();
  });

  it.each([
    ["case UUID", { id: "case-B" }],
    ["site UUID", { site_id: "site-B" }],
    ["legacy site ID", { legacy_site_id: 17 }],
    ["inspection code", { legacy_inspection_code: "KT-B-GMP" }],
  ])("clears an owned result when %s changes", async (_label, identityChange) => {
    const onResolveInspectionFolder = vi.fn().mockResolvedValue(resolved("2024/A"));
    const view = render(<CaseApplicationWorkspace caseWorkspace={workspace} onResolveInspectionFolder={onResolveInspectionFolder} onSave={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" }));
    expect(await screen.findByText("Đã tìm thấy thư mục: 2024/A")).toBeInTheDocument();

    view.rerender(<CaseApplicationWorkspace caseWorkspace={withIdentity(identityChange)} onResolveInspectionFolder={onResolveInspectionFolder} onSave={vi.fn()} />);
    expect(screen.queryByText("Đã tìm thấy thư mục: 2024/A")).not.toBeInTheDocument();
    expect(onResolveInspectionFolder).toHaveBeenCalledOnce();
  });

  it("does not resolve a folder from focus-only keyboard navigation", () => {
    const onResolveInspectionFolder = vi.fn();
    render(<CaseApplicationWorkspace caseWorkspace={workspace} onResolveInspectionFolder={onResolveInspectionFolder} onSave={vi.fn()} />);
    const button = screen.getByRole("button", { name: "Tra cứu thư mục kiểm tra" });
    fireEvent.focus(button);
    fireEvent.keyDown(button, { key: "Tab" });
    expect(onResolveInspectionFolder).not.toHaveBeenCalled();
  });
});
