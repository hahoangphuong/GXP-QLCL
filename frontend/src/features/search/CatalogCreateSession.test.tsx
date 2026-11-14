import type { ReactNode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { CatalogCreateSessionRoot, useCatalogCreateSession } from "./CatalogCreateSession";

const lineUuid = "1f443b5f-ccca-49d2-a710-b2332d282a14";
const caseUuid = "35ae6a45-a8c0-4dd7-9b34-b669c997bd61";
const siteUuid = "a3f4d2aa-7fc8-4a83-8287-cfcdbbbf1426";
const selectionOwner = JSON.stringify(["initial-case-selection", "operator-A", "admin", 3, true, siteUuid]);
const selectionOtherUser = JSON.stringify(["initial-case-selection", "operator-B", "admin", 3, true, siteUuid]);
const caseOwner = JSON.stringify(["initial-case-create", "operator-A", "admin", 3, true, siteUuid, "GMP", lineUuid]);

function Selection({ owner = selectionOwner }: { owner?: string }) {
  const { state, update } = useCatalogCreateSession(owner);
  return <div>
    <output data-testid="gxp">{state.initialCaseSelectedGxp}</output>
    <output data-testid="line">{state.initialCaseSelectedLineId}</output>
    <output data-testid="error">{state.recoveryJournalError ?? ""}</output>
    <button onClick={() => update((old) => ({ ...old, initialCaseSelectedGxp: "GMP", initialCaseSelectedLineId: "" }))}>GMP</button>
    <button onClick={() => update((old) => ({ ...old, initialCaseSelectedGxp: "GMP", initialCaseSelectedLineId: lineUuid }))}>Select line</button>
    <button onClick={() => update((old) => ({ ...old, initialCaseSelectedGxp: "", initialCaseSelectedLineId: "" }))}>Clear</button>
  </div>;
}

function CaseIntent() {
  const { state, update } = useCatalogCreateSession(caseOwner);
  return <div>
    <output data-testid="phase">{state.initialCaseIntent?.phase ?? "none"}</output>
    <output data-testid="case-id">{state.initialCaseIntent?.payload.case_id ?? ""}</output>
    <output data-testid="persisted">{state.initialCaseIntent?.persisted?.id ?? ""}</output>
    <button onClick={() => update((old) => ({
      ...old, initialCaseIntent: {
        token: {}, phase: "pending", persisted: null, error: null, siteId: siteUuid,
        payload: {
          case_id: caseUuid, gxp_type: "GMP", production_line_id: lineUuid,
          inspection_type: "Mới", applicable_standard: "WHO-GMP", reason: "Fixture only",
        },
      },
    }))}>Admit intent</button>
  </div>;
}

const mount = (node: ReactNode) => render(<CatalogCreateSessionRoot>{node}</CatalogCreateSessionRoot>);
const journalKey = (owner: string) => "gxp-catalog-recovery-v1:" + owner;

beforeEach(() => { cleanup(); window.sessionStorage.clear(); });

describe("Initial Case selection routing journal across reload", () => {
  it("restores exact GxP and UUID line selection, without leaking it to another user", () => {
    const view = mount(<Selection />);
    fireEvent.click(screen.getByRole("button", { name: "Select line" }));
    expect(JSON.parse(window.sessionStorage.getItem(journalKey(selectionOwner))!)).toEqual({
      initialCaseSelectedGxp: "GMP", initialCaseSelectedLineId: lineUuid,
    });
    view.unmount();
    const another = mount(<Selection owner={selectionOtherUser} />);
    expect(screen.getByTestId("gxp").textContent).toBe("");
    expect(screen.getByTestId("line").textContent).toBe("");
    another.unmount();
    mount(<Selection />);
    expect(screen.getByTestId("gxp").textContent).toBe("GMP");
    expect(screen.getByTestId("line").textContent).toBe(lineUuid);
  });

  it("preserves the original Case owner intent as unverified after store remount", () => {
    const first = mount(<><Selection /><CaseIntent /></>);
    fireEvent.click(screen.getByRole("button", { name: "Select line" }));
    fireEvent.click(screen.getByRole("button", { name: "Admit intent" }));
    expect(screen.getByTestId("phase").textContent).toBe("pending");
    first.unmount();

    mount(<><Selection /><CaseIntent /></>);
    expect(screen.getByTestId("gxp").textContent).toBe("GMP");
    expect(screen.getByTestId("line").textContent).toBe(lineUuid);
    expect(screen.getByTestId("phase").textContent).toBe("unverified");
    expect(screen.getByTestId("case-id").textContent).toBe(caseUuid);
    expect(screen.getByTestId("persisted").textContent).toBe("");
  });

  it("clearing GxP selection deletes only its routing journal", () => {
    mount(<Selection />);
    fireEvent.click(screen.getByRole("button", { name: "GMP" }));
    expect(window.sessionStorage.getItem(journalKey(selectionOwner))).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(window.sessionStorage.getItem(journalKey(selectionOwner))).toBeNull();
  });

  it("rejects a corrupted GxP/line routing journal without inventing a selection", () => {
    window.sessionStorage.setItem(journalKey(selectionOwner), JSON.stringify({
      initialCaseSelectedGxp: "GMP", initialCaseSelectedLineId: "legacy-line",
    }));
    mount(<Selection />);
    expect(screen.getByTestId("error").textContent).toContain("không hợp lệ");
    expect(screen.getByTestId("gxp").textContent).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "Select line" }));
    expect(screen.getByTestId("line").textContent).toBe("");
  });
});
