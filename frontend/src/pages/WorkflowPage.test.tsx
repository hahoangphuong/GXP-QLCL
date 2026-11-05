import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
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

function HistoryControls() {
  const location = useLocation();
  const navigate = useNavigate();
  return <>
    <output data-testid="url">{location.pathname + location.search}</output>
    <button type="button" onClick={() => navigate(-1)}>Quay lại lịch sử</button>
    <button type="button" onClick={() => navigate(1)}>Tiến lịch sử</button>
  </>;
}

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

  it("restores a bookmarked Certificate or Change Request queue by exact URL", () => {
    const first = render(<MemoryRouter initialEntries={["/workflow?queue=expiring"]}>
      <WorkflowPage access={access} statusError={null} /><HistoryControls />
    </MemoryRouter>);
    expect(screen.getByTestId("record-queue")).toHaveTextContent("certificates:false");
    expect(screen.getByRole("button", { name: "GCN sắp hết hạn" })).toHaveAttribute("aria-pressed", "true");
    first.unmount();
    render(<MemoryRouter initialEntries={["/workflow?queue=change_requests"]}>
      <WorkflowPage access={access} statusError={null} />
    </MemoryRouter>);
    expect(screen.getByTestId("record-queue")).toHaveTextContent("change_requests:true");
  });

  it("keeps the selected queue in URL history across Back/Forward navigation", () => {
    render(<MemoryRouter initialEntries={["/workflow?source=dashboard&queue=inspection"]}>
      <WorkflowPage access={access} statusError={null} /><HistoryControls />
    </MemoryRouter>);
    expect(screen.getByTestId("case-queue")).toHaveTextContent("true::true");
    fireEvent.click(screen.getByRole("button", { name: "Chờ quyết định cấp GCN" }));
    expect(screen.getByTestId("url")).toHaveTextContent("queue=certificate_decision");
    expect(screen.getByTestId("url")).toHaveTextContent("source=dashboard");
    expect(screen.getByTestId("case-queue")).toHaveTextContent("false:awaiting_certificate_decision:true");
    fireEvent.click(screen.getByRole("button", { name: "Quay lại lịch sử" }));
    expect(screen.getByTestId("case-queue")).toHaveTextContent("true::true");
    fireEvent.click(screen.getByRole("button", { name: "Tiến lịch sử" }));
    expect(screen.getByTestId("case-queue")).toHaveTextContent("false:awaiting_certificate_decision:true");
  });

  it("ignores unknown or malformed URL queue selections instead of guessing a business category", () => {
    render(<MemoryRouter initialEntries={["/workflow?queue=GSP&queue=expiring"]}>
      <WorkflowPage access={access} statusError={null} />
    </MemoryRouter>);
    expect(screen.getByTestId("case-queue")).toHaveTextContent("false::true");
    expect(screen.getByRole("button", { name: "Hồ sơ đang xử lý" })).toHaveAttribute("aria-pressed", "true");
  });

  it("keeps full-report navigation in the corresponding operator category", () => {
    render(<MemoryRouter><WorkflowPage access={access} statusError={null} /></MemoryRouter>);
    const link = screen.getByRole("link", { name: "Mở Báo cáo đầy đủ" });
    expect(link).toHaveAttribute("href", "/reports?report=cases");
    fireEvent.click(screen.getByRole("button", { name: "Chuẩn bị và đang kiểm tra" }));
    expect(link).toHaveAttribute("href", "/reports?report=inspection");
    fireEvent.click(screen.getByRole("button", { name: "Chờ quyết định cấp GCN" }));
    expect(link).toHaveAttribute("href", "/reports?report=cases&case_state=awaiting_certificate_decision");
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
