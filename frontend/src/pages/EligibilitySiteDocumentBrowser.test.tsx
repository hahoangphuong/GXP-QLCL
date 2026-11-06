import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../App";
import { listSiteBusinessEligibilityCertificates, searchSitesByName } from "../lib/api";
import { EligibilitySiteDocumentBrowser } from "./EligibilitySiteDocumentBrowser";

vi.mock("../lib/api", () => ({ listSiteBusinessEligibilityCertificates: vi.fn(), searchSitesByName: vi.fn() }));

const siteA = "11111111-1111-4111-8111-111111111111";
const siteB = "22222222-2222-4222-8222-222222222222";
const certificate = "33333333-3333-4333-8333-333333333333";
const company = "44444444-4444-4444-8444-444444444444";
const access: ApiAccess = {
  auth: { username: "reader", role: "reader" }, bearerToken: null,
  useStubAuth: true, canLoadSecureApi: true, accessGeneration: 1,
};
const row = {
  business_eligibility_certificate_id: certificate, site_id: siteA, company_id: company,
  latest_flag: true, certificate_number: "ABC-123", issued_on: "2026-01-01",
  issuance_sequence_text: null, current_status_text: "Còn hiệu lực",
};
const response = (items: typeof row[]) => ({ items, issue_readiness: null }) as Awaited<ReturnType<typeof listSiteBusinessEligibilityCertificates>>;
const submit = (id: string) => {
  fireEvent.change(screen.getByLabelText("Site UUID"), { target: { value: id } });
  fireEvent.click(screen.getByRole("button", { name: "Tra cứu theo Site" }));
};
function UrlControls() {
  const location = useLocation();
  const navigate = useNavigate();
  return <><output data-testid="location">{location.pathname + location.search}</output>
    <button onClick={() => navigate(-1)}>Back</button><button onClick={() => navigate(1)}>Forward</button></>;
}
const mount = (props = access, path = "/documents") => render(
  <MemoryRouter initialEntries={[path]}><UrlControls /><EligibilitySiteDocumentBrowser access={props} /></MemoryRouter>,
);

beforeEach(() => {
  vi.mocked(listSiteBusinessEligibilityCertificates).mockReset().mockResolvedValue(response([row]));
  vi.mocked(searchSitesByName).mockReset().mockResolvedValue([]);
});

describe("site-scoped business eligibility document discovery", () => {
  it("discovers a canonical certificate through the authorized Site API and opens registered metadata", async () => {
    mount();
    expect(listSiteBusinessEligibilityCertificates).not.toHaveBeenCalled();
    submit(siteA);
    expect(await screen.findByRole("link", { name: "Xem metadata" }))
      .toHaveAttribute("href", `/documents/business-eligibility-certificates/${certificate}?return_site_id=${siteA}`);
    expect(screen.getByRole("link", { name: "Xem chi tiết GCN" }))
      .toHaveAttribute("href", `/certificates/business-eligibility/${certificate}?site_id=${siteA}`);
    expect(screen.getByText("ABC-123")).toBeInTheDocument();
    expect(screen.getByText(/không xác minh bản gốc/)).toBeInTheDocument();
    expect(listSiteBusinessEligibilityCertificates).toHaveBeenCalledWith(siteA, access.auth, true, null);
  });

  it("selects a name-matched canonical Site and opens its authorized certificate inventory with a bookmark URL", async () => {
    vi.mocked(searchSitesByName).mockResolvedValueOnce([
      { id: siteA, company_id: company, site_name: "Cơ sở A", province_name: "Hà Nội", legacy_site_id: 11 },
      { id: siteB, company_id: company, site_name: "Cơ sở B", province_name: "Đà Nẵng", legacy_site_id: 11 },
    ]);
    vi.mocked(listSiteBusinessEligibilityCertificates).mockImplementation(siteId =>
      Promise.resolve(response([{ ...row, site_id: siteId }])));
    mount();
    fireEvent.change(screen.getByLabelText("Tìm cơ sở theo tên"), { target: { value: "Cơ sở" } });
    fireEvent.click(screen.getByRole("button", { name: "Tìm cơ sở" }));
    expect(await screen.findByText("Cơ sở B")).toBeInTheDocument();
    expect(listSiteBusinessEligibilityCertificates).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: `Chọn Site Cơ sở B — ${siteB}` }));
    expect(await screen.findByRole("link", { name: "Xem chi tiết GCN" }))
      .toHaveAttribute("href", `/certificates/business-eligibility/${certificate}?site_id=${siteB}`);
    expect(screen.getByTestId("location")).toHaveTextContent(`kind=business_eligibility&site_id=${siteB}`);
    expect(screen.getByLabelText("Site UUID")).toHaveValue(siteB);
    expect(listSiteBusinessEligibilityCertificates).toHaveBeenCalledWith(siteB, access.auth, true, null);
    expect(screen.getByRole("link", { name: "Xem metadata" }))
      .toHaveAttribute("href", `/documents/business-eligibility-certificates/${certificate}?return_site_id=${siteB}`);
  });

  it("does not request protected data for malformed Site UUID or signed-out access", () => {
    const ui = mount();
    submit("../not-site");
    expect(screen.getByRole("alert")).toHaveTextContent("Site UUID hợp lệ");
    expect(listSiteBusinessEligibilityCertificates).not.toHaveBeenCalled();
    ui.unmount();
    render(<MemoryRouter><EligibilitySiteDocumentBrowser access={{ ...access, canLoadSecureApi: false }} /></MemoryRouter>);
    expect(screen.getByText(/Cần đăng nhập/)).toBeInTheDocument();
    expect(listSiteBusinessEligibilityCertificates).not.toHaveBeenCalled();
  });

  it("fails closed on cross-Site, duplicate and malformed identities", async () => {
    const ui = mount();
    vi.mocked(listSiteBusinessEligibilityCertificates).mockResolvedValueOnce(response([{ ...row, site_id: siteB }]));
    submit(siteA);
    expect(await screen.findByRole("alert")).toHaveTextContent("không khớp Site canonical");
    expect(screen.queryByRole("link", { name: "Xem metadata" })).not.toBeInTheDocument();
    ui.unmount();

    vi.mocked(listSiteBusinessEligibilityCertificates).mockResolvedValueOnce(response([row, row]));
    mount();
    submit(siteA);
    expect(await screen.findByRole("alert")).toHaveTextContent("định danh không hợp lệ");
    expect(screen.queryByRole("link", { name: "Xem metadata" })).not.toBeInTheDocument();
  });

  it("does not display obsolete Site A rows or errors after changing to Site B", async () => {
    let resolveA!: (value: Awaited<ReturnType<typeof listSiteBusinessEligibilityCertificates>>) => void;
    vi.mocked(listSiteBusinessEligibilityCertificates)
      .mockImplementationOnce(() => new Promise(resolve => { resolveA = resolve; }))
      .mockResolvedValueOnce(response([{ ...row, site_id: siteB }]));
    mount();
    submit(siteA);
    submit(siteB);
    expect(await screen.findByRole("link", { name: "Xem metadata" })).toBeInTheDocument();
    resolveA(response([row]));
    await waitFor(() => expect(screen.getAllByRole("link", { name: "Xem metadata" })).toHaveLength(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("restores a Site-scoped list from a bookmarked URL and refetches by authorized API", async () => {
    mount(access, `/documents?kind=business_eligibility&site_id=${siteA}`);
    expect(await screen.findByRole("link", { name: "Xem metadata" }))
      .toHaveAttribute("href", `/documents/business-eligibility-certificates/${certificate}?return_site_id=${siteA}`);
    expect(screen.getByLabelText("Site UUID")).toHaveValue(siteA);
    expect(listSiteBusinessEligibilityCertificates).toHaveBeenCalledWith(siteA, access.auth, true, null);
  });

  it("restores A after Back/Forward without adopting a stale Site B read", async () => {
    vi.mocked(listSiteBusinessEligibilityCertificates).mockImplementation(id =>
      Promise.resolve(response([{ ...row, site_id: id }])))
    mount();
    submit(siteA);
    expect(await screen.findByRole("link", { name: "Xem metadata" }))
      .toHaveAttribute("href", `/documents/business-eligibility-certificates/${certificate}?return_site_id=${siteA}`);
    submit(siteB);
    expect(await screen.findByRole("link", { name: "Xem metadata" }))
      .toHaveAttribute("href", `/documents/business-eligibility-certificates/${certificate}?return_site_id=${siteB}`);
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("link", { name: "Xem metadata" }))
      .toHaveAttribute("href", `/documents/business-eligibility-certificates/${certificate}?return_site_id=${siteA}`);
    fireEvent.click(screen.getByRole("button", { name: "Forward" }));
    expect(await screen.findByRole("link", { name: "Xem metadata" }))
      .toHaveAttribute("href", `/documents/business-eligibility-certificates/${certificate}?return_site_id=${siteB}`);
  });

  it("rejects malformed bookmarked Site without making any secure request", () => {
    mount(access, "/documents?kind=business_eligibility&site_id=wrong-site");
    expect(screen.getByRole("alert")).toHaveTextContent("Site UUID trong đường dẫn không hợp lệ");
    expect(listSiteBusinessEligibilityCertificates).not.toHaveBeenCalled();
    expect(screen.queryByRole("link", { name: "Xem metadata" })).not.toBeInTheDocument();
  });

  it("invalidates prior inventory on credential generation change", async () => {
    const ui = mount();
    submit(siteA);
    expect(await screen.findByRole("link", { name: "Xem metadata" })).toBeInTheDocument();
    vi.mocked(listSiteBusinessEligibilityCertificates).mockImplementationOnce(() => new Promise(() => {}));
    ui.rerender(<MemoryRouter><EligibilitySiteDocumentBrowser access={{ ...access, accessGeneration: 2 }} /></MemoryRouter>);
    expect(screen.queryByRole("link", { name: "Xem metadata" })).not.toBeInTheDocument();
  });
});
