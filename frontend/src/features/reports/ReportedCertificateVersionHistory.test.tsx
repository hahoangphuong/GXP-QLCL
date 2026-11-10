import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import type { ApiAccess } from "../../App";
import { getGxpCertificateVersionHistory } from "../../lib/api";
import type { GxpCertificateDetail, GxpCertificateVersionHistory } from "../../types";
import { ReportedCertificateVersionHistory } from "./ReportedCertificateVersionHistory";

vi.mock("../../lib/api", () => ({ getGxpCertificateVersionHistory: vi.fn() }));
const access: ApiAccess = {
  auth: { username: "reader", role: "reader" }, useStubAuth: true,
  bearerToken: null, canLoadSecureApi: true, accessGeneration: 1,
};
const detail = {
  certificate_id: "cert-uuid", site_id: "site-uuid", certificate_type: "GSP",
  case_id: null, row_version: 5,
} as GxpCertificateDetail;
const history: GxpCertificateVersionHistory = {
  certificate_id: "cert-uuid", site_id: "site-uuid", certificate_type: "GSP",
  case_id: null, issuance_basis: "legacy_import",
  aggregate_latest_flag: false, latest_version_id: "version-two",
  versions: [2, 1].map(n => ({
    certificate_version_id: n === 2 ? "version-two" : "version-one",
    version_no: n, row_version: 5, is_latest_version: n === 2,
    lifecycle_state: null, certificate_number: `GSP-${n}`,
    issue_date: null, expiry_date: null, applicable_standard: null,
    issuing_authority: null, scope_summary: `Phạm vi ${n}`,
    scopes: [{ id: `scope-${n}`, scope_key: null,
      scope_text: `Bảo quản lần ${n}`, language_code: "vi", sort_order: 0 }],
  })),
};
function Controls() {
  const location = useLocation();
  const navigate = useNavigate();
  return <>
    <output data-testid="current-location">{location.pathname + location.search}</output>
    <button onClick={() => navigate(-1)}>Quay lại phiên bản trước</button>
    <ReportedCertificateVersionHistory detail={detail} access={access} />
  </>;
}
function mount(route = "/reports/certificates/cert-uuid?site_id=site-uuid") {
  return render(<MemoryRouter initialEntries={[route]}><Controls /></MemoryRouter>);
}
beforeEach(() => vi.mocked(getGxpCertificateVersionHistory).mockReset().mockResolvedValue(history));

it("selects a persisted GxP version in the URL, preserves Site, and restores selection with Back", async () => {
  mount();
  fireEvent.click(await screen.findByText("Các phiên bản GPs đã lưu"));
  expect(await screen.findByText("Bảo quản lần 2")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "Phiên bản đã lưu" }),
    { target: { value: "version-one" } });
  expect(screen.getByTestId("current-location")).toHaveTextContent("site_id=site-uuid&version_id=version-one");
  expect(screen.getByRole("combobox", { name: "Phiên bản đã lưu" })).toHaveValue("version-one");
  expect(screen.getByText("Bảo quản lần 1")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Quay lại phiên bản trước" }));
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Phiên bản đã lưu" })).toHaveValue("version-two"));
  expect(screen.getByTestId("current-location")).not.toHaveTextContent("version_id");
  expect(getGxpCertificateVersionHistory).toHaveBeenCalledOnce();
});

it("loads an exact historical version URL without relying on the default latest selection", async () => {
  mount("/reports/certificates/cert-uuid?site_id=site-uuid&version_id=version-one");
  fireEvent.click(await screen.findByText("Các phiên bản GPs đã lưu"));
  expect(await screen.findByText("Bảo quản lần 1")).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Phiên bản đã lưu" })).toHaveValue("version-one");
});

it("fails closed for an unknown version ID even when the Certificate aggregate is valid", async () => {
  mount("/reports/certificates/cert-uuid?version_id=another-version");
  expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy UUID phiên bản");
  expect(screen.queryByRole("combobox", { name: "Phiên bản đã lưu" })).not.toBeInTheDocument();
});

it("rejects duplicate and empty version hints without requesting protected history", async () => {
  for (const route of [
    "/reports/certificates/cert-uuid?version_id=version-one&version_id=version-two",
    "/reports/certificates/cert-uuid?version_id=",
  ]) {
    const view = mount(route);
    expect(screen.getByRole("alert")).toHaveTextContent("Tham số phiên bản chứng nhận không hợp lệ");
    view.unmount();
  }
  expect(getGxpCertificateVersionHistory).not.toHaveBeenCalled();
});

it("never displays a historical version if its aggregate belongs to a foreign Site", async () => {
  vi.mocked(getGxpCertificateVersionHistory).mockResolvedValue({ ...history, site_id: "foreign-site" });
  mount("/reports/certificates/cert-uuid?version_id=version-one");
  expect(await screen.findByRole("alert")).toHaveTextContent("Lịch sử phiên bản không khớp");
  expect(screen.queryByRole("combobox", { name: "Phiên bản đã lưu" })).not.toBeInTheDocument();
});
