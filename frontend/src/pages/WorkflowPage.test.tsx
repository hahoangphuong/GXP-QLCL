import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../App";
import { WorkflowPage } from "./WorkflowPage";

vi.mock("../features/reports/CaseReport", () => ({
  CaseReport: ({ inspectionQueue, initialState, showDocumentsLink }: { inspectionQueue: boolean; initialState: string; showDocumentsLink: boolean }) =>
    <output data-testid="case-queue">{String(inspectionQueue) + ":" + initialState + ":" + showDocumentsLink}</output>,
}));
vi.mock("../features/reports/CanonicalRecordReport", () => ({
  CanonicalRecordReport: ({ kind, showDocumentsLink }: { kind: string; showDocumentsLink?: boolean }) =>
    <output data-testid="record-queue">{kind + ":" + Boolean(showDocumentsLink)}</output>,
}));

const access: ApiAccess = { auth: { username: "reader", role: "reader" }, useStubAuth: true,
  bearerToken: null, canLoadSecureApi: true, accessGeneration: 1 };

describe("operator workflow landing", () => {
  it("opens real canonical queues and filters certificate decision by backend Case state", () => {
    render(<MemoryRouter><WorkflowPage access={access} statusError={null} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Bàn công việc GxP" })).toBeInTheDocument();
    expect(screen.getByTestId("case-queue")).toHaveTextContent("false::true");
    fireEvent.click(screen.getByRole("button", { name: "Chuẩn bị và đang kiểm tra" }));
    expect(screen.getByTestId("case-queue")).toHaveTextContent("true::true");
    fireEvent.click(screen.getByRole("button", { name: "Chờ quyết định cấp GCN" }));
    expect(screen.getByTestId("case-queue")).toHaveTextContent("false:awaiting_certificate_decision:true");
    fireEvent.click(screen.getByRole("button", { name: "Yêu cầu thay đổi đang mở" }));
    expect(screen.getByTestId("record-queue")).toHaveTextContent("change_requests:true");
    fireEvent.click(screen.getByRole("button", { name: "GCN sắp hết hạn" }));
    expect(screen.getByTestId("record-queue")).toHaveTextContent("certificates:false");
    expect(screen.getByRole("link", { name: "Mở Báo cáo đầy đủ" })).toHaveAttribute("href", "/reports?report=certificates");
  });

  it("keeps full-report navigation in the corresponding operator category", () => {
    render(<MemoryRouter><WorkflowPage access={access} statusError={null} /></MemoryRouter>);
    const link = screen.getByRole("link", { name: "Mở Báo cáo đầy đủ" });
    expect(link).toHaveAttribute("href", "/reports?report=cases");
    fireEvent.click(screen.getByRole("button", { name: "Chuẩn bị và đang kiểm tra" }));
    expect(link).toHaveAttribute("href", "/reports?report=inspection");
    fireEvent.click(screen.getByRole("button", { name: "Chờ quyết định cấp GCN" }));
    expect(link).toHaveAttribute("href", "/reports?report=cases");
    fireEvent.click(screen.getByRole("button", { name: "Yêu cầu thay đổi đang mở" }));
    expect(link).toHaveAttribute("href", "/reports?report=change_requests");
    fireEvent.click(screen.getByRole("button", { name: "GCN sắp hết hạn" }));
    expect(link).toHaveAttribute("href", "/reports?report=certificates");
  });

  it("never mounts the operator queue for unauthorized visitors", () => {
    render(<MemoryRouter><WorkflowPage access={{ ...access, canLoadSecureApi: false }} statusError={null} /></MemoryRouter>);
    expect(screen.getByText("Cần đăng nhập")).toBeInTheDocument();
    expect(screen.queryByTestId("case-queue")).not.toBeInTheDocument();
  });
});
