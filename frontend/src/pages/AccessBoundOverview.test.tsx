import "@testing-library/jest-dom/vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import { useLayoutEffect } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../App";
import type { AppStatus, DashboardSummary } from "../types";
import { AdminSystemStatusPage } from "./AdminSystemStatusPage";
import { DashboardPage } from "./DashboardPage";
const mocks = vi.hoisted(() => ({ admin: vi.fn(), dashboard: vi.fn() }));
vi.mock("../lib/api", () => ({ getAdminSystemStatus: mocks.admin, getDashboardSummary: mocks.dashboard }));
const auth = { username: "synthetic", role: "reader" } as const;
const access = (generation: number, token = "synthetic-only-A"): ApiAccess => ({ auth, accessGeneration: generation, bearerToken: token, useStubAuth: false, canLoadSecureApi: true });
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (error: Error) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
const status = (marker: string) => ({ deployment: { git_short_sha: marker, db_name: "synthetic", branch: "fixture" }, deployment_platform: "fixture", frontend_topology: "fixture", auth_mode: "google_oidc" }) as AppStatus;
const summary = (count: number): DashboardSummary => ({ total_facilities: count, total_cases: 2, active_cases: 3, waiting_inspection: 4, waiting_certificate_decision: 5, active_certificates: 6, expiring_certificates_90_days: 7, incomplete_changes: 8, queue: [] });
function Probe({ kind, owner, commits }: { kind: "admin" | "dashboard"; owner: ApiAccess; commits: string[] }) {
  useLayoutEffect(() => { commits.push(document.body.textContent ?? ""); }, [owner, commits]);
  return kind === "admin" ? <AdminSystemStatusPage access={owner} /> : <DashboardPage access={owner} statusError={null} />;
}
beforeEach(() => { mocks.admin.mockReset(); mocks.dashboard.mockReset(); });
describe.each(["admin", "dashboard"] as const)("%s access-bound read ownership", kind => {
  const api = () => kind === "admin" ? mocks.admin : mocks.dashboard;
  const payload = (id: number) => kind === "admin" ? status(`ONLY-OWNER-${id}`) : summary(1300 + id);
  const marker = (id: number) => kind === "admin" ? `ONLY-OWNER-${id}` : `${1300 + id}`;
  it("hides old data in B's first commit and refetches for same-token access generation", async () => {
    const next = deferred<unknown>(), commits: string[] = [];
    api().mockResolvedValueOnce(payload(1)).mockReturnValueOnce(next.promise);
    const draw = (owner: ApiAccess) => <MemoryRouter><Probe kind={kind} owner={owner} commits={commits} /></MemoryRouter>;
    const view = render(draw(access(1)));await screen.findByText(marker(1));
    view.rerender(draw(access(2)));
    expect(commits.at(-1)).not.toContain(marker(1));
    expect(api()).toHaveBeenCalledTimes(2);
    await act(async () => next.resolve(payload(2)));
    expect(screen.getByText(marker(2))).toBeInTheDocument();
  });
  it("does not retain A's forbidden error while B is loading", async () => {
    const next = deferred<unknown>(), commits: string[] = [];
    api().mockRejectedValueOnce(Object.assign(new Error("ONLY-A-FORBIDDEN"), { status: 403 })).mockReturnValueOnce(next.promise);
    const draw = (owner: ApiAccess) => <MemoryRouter><Probe kind={kind} owner={owner} commits={commits} /></MemoryRouter>;
    const view = render(draw(access(1)));await screen.findByText("ONLY-A-FORBIDDEN");
    view.rerender(draw(access(2, "synthetic-only-B")));
    expect(commits.at(-1)).not.toContain("ONLY-A-FORBIDDEN");
    await act(async () => next.reject(Object.assign(new Error("ONLY-B-FORBIDDEN"), { status: 403 })));
    expect(screen.getByText("ONLY-B-FORBIDDEN")).toBeInTheDocument();
  });
  it("ignores late A and B responses after A-B-A and logout", async () => {
    const old = deferred<unknown>(), b = deferred<unknown>(), latest = deferred<unknown>(), commits: string[] = [];
    api().mockReturnValueOnce(old.promise).mockReturnValueOnce(b.promise).mockReturnValueOnce(latest.promise);
    const draw = (owner: ApiAccess) => <MemoryRouter><Probe kind={kind} owner={owner} commits={commits} /></MemoryRouter>;
    const view = render(draw(access(1)));view.rerender(draw(access(2, "synthetic-only-B")));view.rerender(draw(access(3)));
    await act(async () => latest.resolve(payload(3)));
    await act(async () => { old.resolve(payload(1));b.reject(new Error("OLD-B-ERROR")); });
    expect(screen.getByText(marker(3))).toBeInTheDocument();expect(screen.queryByText("OLD-B-ERROR")).not.toBeInTheDocument();
    view.rerender(draw({ ...access(4), canLoadSecureApi: false, bearerToken: null }));
    expect(screen.getByText("Cần đăng nhập")).toBeInTheDocument();expect(screen.queryByText(marker(3))).not.toBeInTheDocument();
  });
  it("does not repeat a read when only the access wrapper object rerenders", async () => {
    const commits: string[] = [], owner = access(1);api().mockResolvedValue(payload(1));
    const draw = (value: ApiAccess) => <MemoryRouter><Probe kind={kind} owner={value} commits={commits} /></MemoryRouter>;
    const view = render(draw(owner));await screen.findByText(marker(1));view.rerender(draw({ ...owner }));
    await waitFor(() => expect(api()).toHaveBeenCalledTimes(1));
  });
});
