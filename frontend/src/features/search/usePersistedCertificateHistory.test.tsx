import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getBusinessEligibilityVersionHistory, getGxpCertificateVersionHistory } from "../../lib/api";
import { usePersistedCertificateHistory } from "./usePersistedCertificateHistory";
import type { GxpCertificateVersionHistory } from "../../types";
vi.mock("../../lib/api", () => ({ getGxpCertificateVersionHistory: vi.fn(), getBusinessEligibilityVersionHistory: vi.fn() }));
const load = vi.mocked(getGxpCertificateVersionHistory);
const auth = { username: "fixture.reader", role: "reader" as const };
const fixture = (id: string): GxpCertificateVersionHistory => ({ certificate_id: id, site_id: "site", case_id: null,
  certificate_type: "GMP", issuance_basis: "legacy_import", aggregate_latest_flag: true, latest_version_id: null, versions: [] });
beforeEach(() => { vi.resetAllMocks(); });
describe("history read ownership", () => {
  it.each([403, 404, 409])("ignores stale HTTP %i and rejects an A request replaced by A/B/A", async status => {
    let rejectA!: (error: unknown) => void;
    let resolveB!: (v: GxpCertificateVersionHistory) => void;
    load.mockImplementationOnce(() => new Promise((_, reject) => { rejectA = reject; }))
      .mockImplementationOnce(() => new Promise(resolve => { resolveB = resolve; }))
      .mockResolvedValueOnce(fixture("A"));
    const { result, rerender } = renderHook(({ id }) => usePersistedCertificateHistory("gxp", "context", id, 1, true, auth, true, null), { initialProps: { id: "A" } });
    rerender({ id: "B" }); rerender({ id: "A" });
    await waitFor(() => expect(result.current).toMatchObject({ status: "ready", data: fixture("A") }));
    await act(async () => { rejectA({ status }); resolveB(fixture("B")); });
    expect(result.current).toMatchObject({ status: "ready", data: fixture("A") });
    expect(load).toHaveBeenCalledTimes(3);
  });
  it("aborts A, hides its snapshot synchronously and rejects late A after B and A/B/A", async () => {
    let resolveA!: (v: GxpCertificateVersionHistory) => void;
    load.mockImplementationOnce(() => new Promise(resolve => { resolveA = resolve; })).mockResolvedValue(fixture("B"));
    const { result, rerender } = renderHook(({ id }) => usePersistedCertificateHistory("gxp", "context", id, 1, true, auth, true, null), { initialProps: { id: "A" } });
    const signal = load.mock.calls[0][4];
    rerender({ id: "B" });
    expect(signal?.aborted).toBe(true);
    await waitFor(() => expect(result.current).toMatchObject({ status: "ready", data: fixture("B") }));
    await act(async () => resolveA(fixture("A")));
    expect(result.current).toMatchObject({ status: "ready", data: fixture("B") });
    load.mockResolvedValueOnce(fixture("A"));
    rerender({ id: "A" });
    await waitFor(() => expect(result.current).toMatchObject({ status: "ready", data: fixture("A") }));
    expect(load).toHaveBeenCalledTimes(3);
  });
  it("reuses a settled read across tab exit and temporary missing current detail, refreshes only its revision", async () => {
    load.mockResolvedValue(fixture("A"));
    const { result, rerender } = renderHook(({ enabled, revision }: { enabled: boolean; revision: number | undefined }) => usePersistedCertificateHistory("gxp", "context", "A", revision, enabled, auth, true, null), { initialProps: { enabled: true, revision: 1 as number | undefined } });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    act(() => { if (result.current.status === "ready") result.current.onSelectVersion?.("old-version"); });
    rerender({ enabled: false, revision: undefined });
    rerender({ enabled: true, revision: 1 });
    expect(load).toHaveBeenCalledTimes(1);
    expect(result.current).toMatchObject({ selectedVersionId: "old-version" });
    rerender({ enabled: true, revision: 2 });
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  });
  it.each([401, 403, 404, 409, 500])("does not retry HTTP %i on focus/tab navigation", async status => {
    load.mockRejectedValue({ status });
    const { result, rerender } = renderHook(({ enabled }) => usePersistedCertificateHistory("gxp", "context", "A", 1, enabled, auth, true, null), { initialProps: { enabled: true } });
    await waitFor(() => expect(result.current).toEqual({ status: "error", httpStatus: status }));
    rerender({ enabled: false }); rerender({ enabled: true });
    expect(load).toHaveBeenCalledTimes(1);
  });
  it("rejects wrong aggregate identity and never requests inactive aggregates", async () => {
    load.mockResolvedValue(fixture("wrong"));
    const { result, rerender } = renderHook(({ enabled }) => usePersistedCertificateHistory("gxp", "context", "A", 1, enabled, auth, true, null), { initialProps: { enabled: false } });
    expect(load).not.toHaveBeenCalled();
    rerender({ enabled: true });
    await waitFor(() => expect(result.current.status).toBe("error"));
  });
  it("rejects DDK history that includes source tokens instead of per-version FK evidence", async () => {
    vi.mocked(getBusinessEligibilityVersionHistory).mockResolvedValue({ business_eligibility_certificate_id: "A", gxp_source_tokens_included: true } as never);
    const { result } = renderHook(() => usePersistedCertificateHistory("ddk", "context", "A", 1, true, auth, true, null));
    await waitFor(() => expect(result.current.status).toBe("error"));
  });
});
