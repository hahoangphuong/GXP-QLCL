import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ContextualDocumentAction } from "../../types";
import { ContextualDocumentSection, LinkedGxpCertificates } from "./EventWorkspace";

function item(createAvailable = true): ContextualDocumentAction {
  return {
    checklist_key: "case:case-1:INSPECTION_KE_HOACH_KT",
    label: "Kế hoạch kiểm tra",
    family_code: "INSPECTION_KE_HOACH_KT",
    workflow_step: "Kiểm tra",
    parent_scope: "case",
    parent_id: "case-1",
    status: "missing",
    document_id: null,
    document_type_code: null,
    title: null,
    original_filename: null,
    issued_on: null,
    available_variant_types: [],
    detail_available: false,
    actions: [
      {
        action_key: "create",
        label: "Tạo",
        available: createAvailable,
        disabled_reason: createAvailable ? null : "blocked",
        required_permissions: ["document.write"],
        reason_code: createAvailable ? null : "blocked",
        create_readiness: createAvailable ? "READY_CREATE_OPEN_HISTORY" : "OTHER_BLOCKED",
        family_code: "INSPECTION_KE_HOACH_KT",
        parent_scope: "case",
        parent_id: "case-1",
        document_type_code: null,
        create_gxp_type: "GMP",
        create_storage_scope: "inspection_folder",
        create_output_filename: "3. Kế hoạch kiểm tra GMP.docx",
      },
    ],
  };
}

describe("ContextualDocumentSection typed create", () => {
  it("invokes the backend-owned create contract instead of hiding an available create action", async () => {
    const onCreateDocument = vi.fn().mockResolvedValue(undefined);
    const actionItem = item(true);
    render(
      <ContextualDocumentSection
        items={[actionItem]}
        onCreateDocument={onCreateDocument}
        onLoadDocumentDetail={vi.fn()}
        onOpenDocument={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Tạo Kế hoạch kiểm tra" }));

    await waitFor(() => expect(onCreateDocument).toHaveBeenCalledTimes(1));
    expect(onCreateDocument).toHaveBeenCalledWith(actionItem, actionItem.actions[0]);
  });

  it("keeps a blocked create action disabled and surfaces its backend reason", () => {
    render(
      <ContextualDocumentSection
        items={[item(false)]}
        onCreateDocument={vi.fn()}
        onLoadDocumentDetail={vi.fn()}
        onOpenDocument={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: "Tạo Kế hoạch kiểm tra" })).not.toBeInTheDocument();
    expect(screen.getByText("blocked")).toBeInTheDocument();
  });
});


describe("LinkedGxpCertificates canonical handoff", () => {
  const certificate = (id: string) => ({
    certificate_id: id, certificate_type: "GMP", case_id: "case-A",
    site_id: "site-1", line_code: null, certificate_number: id, issue_date: null, latest_flag: true,
  });
  it("opens only the explicitly permitted selected UUID", () => {
    const open = vi.fn();
    const { rerender } = render(
      <LinkedGxpCertificates items={[certificate("cert-A"), certificate("cert-B")] as never}
        openableCertificateIds={["cert-B"]} onOpenCertificate={open} />,
    );
    expect(screen.queryByRole("button", { name: "Xem chứng nhận trong sổ GxP" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("row", { name: /cert-B/ }));
    fireEvent.click(screen.getByRole("button", { name: "Xem chứng nhận trong sổ GxP" }));
    expect(open).toHaveBeenCalledOnce();
    expect(open).toHaveBeenCalledWith("cert-B");
    rerender(<LinkedGxpCertificates items={[certificate("cert-A"), certificate("cert-B")] as never}
      openableCertificateIds={[]} onOpenCertificate={open} />);
    expect(screen.queryByRole("button", { name: "Xem chứng nhận trong sổ GxP" })).not.toBeInTheDocument();
  });
});
