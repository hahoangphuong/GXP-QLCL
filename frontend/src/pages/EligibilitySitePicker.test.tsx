import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../App";
import { searchSitesByName } from "../lib/api";
import type { Site } from "../types";
import { EligibilitySitePicker } from "./EligibilitySitePicker";

vi.mock("../lib/api", () => ({ searchSitesByName: vi.fn() }));
const siteA = "11111111-1111-4111-8111-111111111111";
const siteB = "22222222-2222-4222-8222-222222222222";
const company = "44444444-4444-4444-8444-444444444444";
const access: ApiAccess = {
  auth: { username: "reader", role: "reader" }, bearerToken: null,
  useStubAuth: true, canLoadSecureApi: true, accessGeneration: 1,
};
const results: Site[] = [
  { id: siteA, company_id: company, site_name: "Cơ sở Minh Chứng", province_name: "Hà Nội", legacy_site_id: 12 },
  { id: siteB, company_id: company, site_name: "Cơ sở Minh Chứng", province_name: "Đà Nẵng", legacy_site_id: 12 },
];
const onSelect = vi.fn();
function mount(props = access) {
  return render(<EligibilitySitePicker access={props} onSelect={onSelect} />);
}
function search(query: string) {
  fireEvent.change(screen.getByLabelText("Tìm cơ sở theo tên"), { target: { value: query } });
  fireEvent.click(screen.getByRole("button", { name: "Tìm cơ sở" }));
}
beforeEach(() => {
  vi.mocked(searchSitesByName).mockReset().mockResolvedValue(results);
  onSelect.mockReset();
});
describe("canonical Site name discovery for business eligibility", () => {
  it("does not load Sites until requested; distinguishes same names by province and canonical UUID", async () => {
    mount();
    expect(searchSitesByName).not.toHaveBeenCalled();
    search("  Minh Chứng  ");
    await screen.findAllByRole("button", { name: /Chọn Site/ });
    expect(searchSitesByName).toHaveBeenCalledWith("Minh Chứng", access.auth, true, null);
    expect(screen.getByText("Hà Nội")).toBeInTheDocument();
    expect(screen.getByText("Đà Nẵng")).toBeInTheDocument();
    expect(screen.getAllByText("Cơ sở Minh Chứng")).toHaveLength(2);
    expect(screen.getByText(siteA)).toBeInTheDocument();
    expect(screen.getByText(siteB)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: `Chọn Site Cơ sở Minh Chứng — ${siteB}` }));
    expect(onSelect).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith(siteB);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it.each(["", "a", "a".repeat(81)])("does not request an invalid search query", input => {
    const { container } = mount();
    const field = screen.getByLabelText("Tìm cơ sở theo tên");
    // Input maxLength is a browser affordance; the handler also validates independent of it.
    fireEvent.change(field, { target: { value: input } });
    fireEvent.submit(container.querySelector("form")!);
    expect(screen.getByRole("alert")).toHaveTextContent("2 đến 80 ký tự");
    expect(searchSitesByName).not.toHaveBeenCalled();
  });

  it("rejects duplicate Site UUID and malformed company UUID before displaying choices", async () => {
    vi.mocked(searchSitesByName).mockResolvedValueOnce([results[0], { ...results[0] }]);
    const view = mount();
    search("Minh");
    expect(await screen.findByRole("alert")).toHaveTextContent("Không thể tìm cơ sở");
    expect(screen.queryByRole("button", { name: /Chọn Site/ })).not.toBeInTheDocument();
    view.unmount();
    vi.mocked(searchSitesByName).mockResolvedValueOnce([{ ...results[0], company_id: "legacy-12" }]);
    mount();
    search("Minh");
    expect(await screen.findByRole("alert")).toHaveTextContent("định danh không hợp lệ");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("fails closed if the backend returns more than the supported 20 rows", async () => {
    vi.mocked(searchSitesByName).mockResolvedValueOnce(Array.from({ length: 21 }, (_, i) => ({
      ...results[0], id: `${String(i + 1).padStart(8, "0")}-1111-4111-8111-111111111111`,
    })));
    mount();
    search("Minh");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Chọn Site/ })).not.toBeInTheDocument();
  });

  it("hides old rows immediately when editing search terms; ignores A response after B succeeds", async () => {
    let resolveA!: (value: Site[]) => void;
    vi.mocked(searchSitesByName).mockImplementationOnce(() => new Promise(resolve => { resolveA = resolve; }))
      .mockResolvedValueOnce([results[1]]);
    mount();
    search("Cơ sở A");
    search("Cơ sở B");
    expect(await screen.findByText(siteB)).toBeInTheDocument();
    await act(async () => resolveA([results[0]]));
    expect(screen.queryByText(siteA)).not.toBeInTheDocument();
    expect(screen.getByText(siteB)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Tìm cơ sở theo tên"), { target: { value: "Cơ sở C" } });
    expect(screen.queryByText(siteB)).not.toBeInTheDocument();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("rejects late errors from a previous query after the new one returns", async () => {
    let rejectOld!: (error: Error) => void;
    vi.mocked(searchSitesByName).mockImplementationOnce(() => new Promise((_, reject) => { rejectOld = reject; }))
      .mockResolvedValueOnce([results[1]]);
    mount();
    search("Old");
    search("New");
    expect(await screen.findByText(siteB)).toBeInTheDocument();
    await act(async () => rejectOld(new Error("Old HTTP 403")));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText(siteB)).toBeInTheDocument();
  });

  it("hides prior rows across credential generations and ignores late previous-session success", async () => {
    let resolveNew!: (value: Site[]) => void;
    vi.mocked(searchSitesByName).mockResolvedValueOnce([results[0]])
      .mockImplementationOnce(() => new Promise(resolve => { resolveNew = resolve; }));
    const view = mount();
    search("Minh");
    expect(await screen.findByText(siteA)).toBeInTheDocument();
    view.rerender(<EligibilitySitePicker access={{ ...access, accessGeneration: 2, auth: { username: "other", role: "reader" } }} onSelect={onSelect} />);
    expect(screen.queryByText(siteA)).not.toBeInTheDocument();
    search("Other");
    expect(searchSitesByName).toHaveBeenCalledTimes(2);
    await act(async () => resolveNew([results[1]]));
    expect(await screen.findByText(siteB)).toBeInTheDocument();
    expect(screen.queryByText(siteA)).not.toBeInTheDocument();
  });

  it("does not search or display choices without secure API access", () => {
    mount({ ...access, canLoadSecureApi: false });
    expect(screen.queryByRole("button", { name: "Tìm cơ sở" })).not.toBeInTheDocument();
    expect(searchSitesByName).not.toHaveBeenCalled();
  });

  it("presents an empty result and a denied read without fabricating Site options or retry", async () => {
    vi.mocked(searchSitesByName).mockResolvedValueOnce([]);
    const view = mount();
    search("Unknown");
    expect(await screen.findByRole("status")).toHaveTextContent("Không tìm thấy cơ sở");
    view.unmount();
    vi.mocked(searchSitesByName).mockRejectedValueOnce(new Error("HTTP 403"));
    mount();
    search("Denied");
    expect(await screen.findByRole("alert")).toHaveTextContent("Không thể tìm cơ sở");
    expect(searchSitesByName).toHaveBeenCalledTimes(2);
    expect(onSelect).not.toHaveBeenCalled();
  });
});
