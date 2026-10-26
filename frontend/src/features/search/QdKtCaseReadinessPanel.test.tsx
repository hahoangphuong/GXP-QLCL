import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getCaseQdKtCurrentTeam, getCaseQdKtReadiness } from "../../lib/api";
import { QdKtCaseReadinessPanel } from "./QdKtCaseReadinessPanel";

vi.mock("../../lib/api", () => ({
  getCaseQdKtCurrentTeam: vi.fn(),
  getCaseQdKtReadiness: vi.fn(),
}));

const loadReadiness = vi.mocked(getCaseQdKtReadiness);
const loadCurrentTeam = vi.mocked(getCaseQdKtCurrentTeam);
const auth = { username: "fixture.reader", role: "reader" as const };

function readiness(caseId = "case-a") {
  return {
    case_id: caseId,
    family_code: "INSPECTION_QD_KT" as const,
    ready_to_render: false as const,
    decision_source_id: `decision-${caseId}`,
    registered_site_id: `site-${caseId}`,
    blocked_reasons: ["QDKT_TYPED_RENDER_CONTRACT_MISSING"],
  };
}

function currentTeam(caseId = "case-a") {
  return {
    case_id: caseId,
    team_id: `team-${caseId}`,
    team_revision: 2,
    source_kind: "CURRENT_CASE_TEAM" as const,
    draft_snapshot_available: false as const,
    issued_team_confirmed: false as const,
    members: [],
  };
}

function panel(caseId = "case-a") {
  return <QdKtCaseReadinessPanel caseId={caseId} auth={auth} useStubAuth={false} bearerToken="oidc" accessGeneration={1} />;
}

afterEach(() => vi.resetAllMocks());

describe("Case QĐKT readiness ownership", () => {
  it("shows canonical decision and registered-Site provenance without implying issuance", async () => {
    loadReadiness.mockResolvedValue(readiness());
    loadCurrentTeam.mockResolvedValue(currentTeam());
    render(panel());

    expect(loadReadiness).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Xem trạng thái QĐKT" }));

    expect(await screen.findByText(/decision-case-a/)).toBeInTheDocument();
    expect(screen.getByText(/site-case-a/)).toBeInTheDocument();
    expect(screen.getByText(/không phải QĐKT đã ban hành/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Tạo.*QĐKT/i })).not.toBeInTheDocument();
  });

  it("fails closed and retries readiness only after explicit activation", async () => {
    loadReadiness
      .mockRejectedValueOnce(Object.assign(new Error("conflict"), { status: 409 }))
      .mockResolvedValueOnce(readiness());
    loadCurrentTeam.mockResolvedValue(currentTeam());
    render(panel());

    fireEvent.click(screen.getByRole("button", { name: "Xem trạng thái QĐKT" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("conflict");
    expect(loadReadiness).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Thử kiểm tra lại QĐKT" }));
    await waitFor(() => expect(screen.getByText(/decision-case-a/)).toBeInTheDocument());
    expect(loadReadiness).toHaveBeenCalledTimes(2);
  });

  it("rejects a late Case A readiness response after switching to Case B", async () => {
    let resolveA!: (value: ReturnType<typeof readiness>) => void;
    loadReadiness
      .mockImplementationOnce(() => new Promise(resolve => { resolveA = resolve; }))
      .mockResolvedValueOnce(readiness("case-b"));
    loadCurrentTeam.mockResolvedValue(currentTeam("case-b"));
    const { rerender } = render(panel());

    fireEvent.click(screen.getByRole("button", { name: "Xem trạng thái QĐKT" }));
    await waitFor(() => expect(loadReadiness).toHaveBeenCalledTimes(1));
    rerender(panel("case-b"));
    expect(await screen.findByText(/decision-case-b/)).toBeInTheDocument();
    await act(async () => { resolveA(readiness("case-a")); });
    expect(screen.queryByText(/decision-case-a/)).not.toBeInTheDocument();
  });
});
