import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BusinessEligibilitySourceEvidence } from "./BusinessEligibilitySourceEvidence";
import { useBusinessEligibilitySourceEvidence } from "./useBusinessEligibilitySourceEvidence";
import { getBusinessEligibilityGxpSourceEvidence } from "../../lib/api";
import type { BusinessEligibilityGxpSourceEvidence } from "../../types";

vi.mock("../../lib/api", () => ({ getBusinessEligibilityGxpSourceEvidence: vi.fn() }));
const load = vi.mocked(getBusinessEligibilityGxpSourceEvidence);
const auth = { username: "fixture.reader", role: "reader" as const };

export function sourceFixture(id = "ddk-a"): BusinessEligibilityGxpSourceEvidence {
  return {
    business_eligibility_certificate_id: id, legacy_dkkd_id: 42, source_status: "available",
    evidence_kind: "original_excel_cells_source_only", canonical_links_included: false,
    source_workbook_sha256: "a".repeat(64), source_sheet_name: "db.dkkd", source_row_number: 43,
    groups: (["GDP", "GSP", "GLP", "GMP"] as const).map(name => ({
      source_group_id: `${id}-${name}`, source_group: name, id_cc_excel_column: 15 + ["GMP", "GLP", "GSP", "GDP"].indexOf(name) * 4,
      certificate_scope_excel_column: 16 + ["GMP", "GLP", "GSP", "GDP"].indexOf(name) * 4, applicable_standard_excel_column: 17 + ["GMP", "GLP", "GSP", "GDP"].indexOf(name) * 4,
      business_activity_excel_column: 18 + ["GMP", "GLP", "GSP", "GDP"].indexOf(name) * 4, id_cc_raw: name === "GMP" ? "17, 17; 22" : "",
      certificate_scope_raw: `${name}: dòng 1\n  dòng 2`, applicable_standard_raw: name === "GDP" ? "" : `${name} standard`,
      business_activity_raw: `${name}: hoạt động nguồn`, source_values_sha256: "b".repeat(64),
      reference_tokens: name === "GMP" ? ["17", "17", "22"].map((raw_token, n) => ({
        source_reference_id: `${id}-token-${n}`, token_index: n + 1, raw_token,
        parsed_legacy_certificate_id: Number(raw_token),
      })) : [],
    })),
  };
}

afterEach(() => vi.resetAllMocks());

describe("original ĐĐK source presentation", () => {
  it("keeps four groups, verbatim multiline cells, repeated source tokens and GDP activity without ID CC", () => {
    const { container } = render(<BusinessEligibilitySourceEvidence state={{ status: "ready", data: sourceFixture() }} />);
    expect(Array.from(container.querySelectorAll("summary"), node => node.textContent)).toEqual(["GMP", "GLP", "GSP", "GDP"]);
    const gmp = container.querySelector("details")!;
    expect(gmp.querySelectorAll("dd")[1].textContent).toBe("GMP: dòng 1\n  dòng 2");
    expect(Array.from(gmp.querySelectorAll("li"), node => [node.getAttribute("value"), node.textContent]))
      .toEqual([["1", "17"], ["2", "17"], ["3", "22"]]);
    const gdp = container.querySelectorAll("details")[3];
    expect(gdp).toHaveTextContent("GDP: hoạt động nguồn");
    expect(gdp.querySelectorAll("dd")[0]).toHaveTextContent("Ô nguồn trống");
    expect(screen.getByText(/chưa phải liên kết GxP được xác nhận/)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
  it.each(["legacy_identity_missing", "not_in_imported_source"] as const)("distinguishes %s from no canonical certificates", source_status => {
    render(<BusinessEligibilitySourceEvidence state={{ status: "ready", data: { ...sourceFixture(), source_status, groups: [] } }} />);
    expect(screen.getByRole("status")).toHaveTextContent(source_status === "legacy_identity_missing" ? "chưa có định danh legacy" : "không nằm trong nguồn Excel");
    expect(screen.queryByText("Không có chứng nhận GxP")).not.toBeInTheDocument();
  });
  it.each([401, 403, 404, 409, 503, null])("presents HTTP %s without actions/retry", httpStatus => {
    render(<BusinessEligibilitySourceEvidence state={{ status: "error", httpStatus }} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    if (httpStatus === 409) expect(screen.getByRole("alert")).toHaveTextContent("không tự tải lại");
  });
  it("announces loading with no old group values", () => {
    const { rerender } = render(<BusinessEligibilitySourceEvidence state={{ status: "ready", data: sourceFixture() }} />);
    rerender(<BusinessEligibilitySourceEvidence state={{ status: "loading" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Đang tải");
    expect(screen.queryByText("GMP: hoạt động nguồn")).not.toBeInTheDocument();
  });
});

describe("selected ĐĐK source request ownership", () => {
  it("closes old access ownership immediately when the authenticated session changes", async () => {
    load.mockResolvedValueOnce(sourceFixture()).mockImplementationOnce(() => new Promise(() => undefined));
    const { result, rerender } = renderHook(({ token }) => useBusinessEligibilitySourceEvidence("site-line", "ddk-a", auth, false, token), { initialProps: { token: "old-session" } });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    rerender({ token: "new-session" });
    expect(result.current.status).toBe("loading");
    expect(load.mock.calls[0][4]?.aborted).toBe(true);
  });
  it.each([401, 403, 409, 503, null])("keeps current HTTP %s local with one read and no automatic retry", async status => {
    load.mockRejectedValue(Object.assign(new Error("source unavailable"), { status }));
    const { result } = renderHook(() => useBusinessEligibilitySourceEvidence("site-line", "ddk-a", auth, false, null));
    await waitFor(() => expect(result.current).toEqual({ status: "error", httpStatus: status }));
    expect(load).toHaveBeenCalledTimes(1);
  });
  it("does not read without a selected canonical certificate/context", () => {
    renderHook(() => useBusinessEligibilitySourceEvidence(null, null, auth, false, null));
    expect(load).not.toHaveBeenCalled();
  });
  it("aborts A, hides it in B's first render and rejects its late success", async () => {
    let resolveA!: (value: BusinessEligibilityGxpSourceEvidence) => void;
    load.mockImplementationOnce(() => new Promise(resolve => { resolveA = resolve; })).mockResolvedValueOnce(sourceFixture("ddk-b"));
    const { result, rerender } = renderHook(({ id }) => useBusinessEligibilitySourceEvidence("site-line", id, auth, false, "oidc"), { initialProps: { id: "ddk-a" } });
    const signal = load.mock.calls[0][4]!;
    rerender({ id: "ddk-b" });
    expect(signal.aborted).toBe(true);
    await waitFor(() => expect(result.current.status).toBe("ready"));
    await act(async () => { resolveA(sourceFixture("ddk-a")); });
    expect(result.current).toEqual({ status: "ready", data: sourceFixture("ddk-b") });
  });
  it.each([403, 404, 409])("silences late A HTTP %s after B succeeds", async status => {
    let rejectA!: (value: Error) => void;
    load.mockImplementationOnce(() => new Promise((_, reject) => { rejectA = reject; })).mockResolvedValueOnce(sourceFixture("ddk-b"));
    const { result, rerender } = renderHook(({ id }) => useBusinessEligibilitySourceEvidence("site-line", id, auth, false, null), { initialProps: { id: "ddk-a" } });
    rerender({ id: "ddk-b" });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    await act(async () => { rejectA(Object.assign(new Error("old error"), { status })); });
    expect(result.current.status).toBe("ready");
    expect(load).toHaveBeenCalledTimes(2);
  });
  it("rejects replaced A in an A → B → A round trip", async () => {
    let resolveOld!: (value: BusinessEligibilityGxpSourceEvidence) => void;
    load.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }))
      .mockResolvedValueOnce(sourceFixture("ddk-b")).mockResolvedValueOnce({ ...sourceFixture(), source_row_number: 99 });
    const { result, rerender } = renderHook(({ id }) => useBusinessEligibilitySourceEvidence("site-line", id, auth, false, null), { initialProps: { id: "ddk-a" } });
    rerender({ id: "ddk-b" }); rerender({ id: "ddk-a" });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    await act(async () => { resolveOld(sourceFixture()); });
    expect(result.current.status === "ready" && result.current.data.source_row_number).toBe(99);
  });
  it("does not load again for unrelated focus/collapse renders", async () => {
    load.mockResolvedValue(sourceFixture());
    function Test({ focus }: { focus: number }) {
      const state = useBusinessEligibilitySourceEvidence("site-line", "ddk-a", auth, false, null);
      return <div data-focus={focus}><BusinessEligibilitySourceEvidence state={state} /></div>;
    }
    const { rerender } = render(<Test focus={0} />);
    await screen.findByText("GMP: hoạt động nguồn");
    rerender(<Test focus={1} />); fireEvent.click(screen.getByText("GMP", { selector: "summary" }));
    expect(load).toHaveBeenCalledTimes(1);
  });
  it("fails closed on mismatched UUID and incomplete physical groups", async () => {
    load.mockResolvedValueOnce(sourceFixture("other-id")).mockResolvedValueOnce({ ...sourceFixture(), groups: [] });
    const { result, rerender } = renderHook(({ context }) => useBusinessEligibilitySourceEvidence(context, "ddk-a", auth, false, null), { initialProps: { context: "site-a" } });
    await waitFor(() => expect(result.current.status).toBe("error"));
    rerender({ context: "site-b" });
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.status).toBe("error"));
  });
});
