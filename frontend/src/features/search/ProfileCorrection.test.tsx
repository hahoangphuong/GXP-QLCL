import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiAccess } from "../../App";
import { correctCompanyProfile, correctSiteProfile, getCompany, getSite } from "../../lib/api";
import type { CompanyDetail, SiteDetail } from "../../types";
import { ProfileCorrectionActions, type ProfileDrafts } from "./ProfileCorrection";

vi.mock("../../lib/api", () => ({
  correctCompanyProfile: vi.fn(), correctSiteProfile: vi.fn(), getCompany: vi.fn(), getSite: vi.fn(),
}));

const access: ApiAccess = { auth: { username: "operator", role: "inspector" }, useStubAuth: true,
  bearerToken: null, canLoadSecureApi: true, accessGeneration: 1 };
const { auth } = access;
const company: CompanyDetail = { id: "company-a", legacy_company_id: 1, legal_name: "Công ty A",
  legal_address: "Địa chỉ A", english_name: null, short_name: "A", legal_address_en: null, is_inactive: false };
const site: SiteDetail = { id: "site-a", legacy_site_id: 2, company_id: company.id, site_name: "Cơ sở A",
  site_address: "Địa chỉ cũ", site_name_en: null, site_address_en: null, province_name: "Hà Nội", short_name: null };
const statusError = (status: number) => Object.assign(new Error("Synthetic error"), { status });
const siteExpected = { company_id: company.id, site_name: site.site_name, site_address: site.site_address,
  site_name_en: null, site_address_en: null, province_name: "Hà Nội", short_name: null };

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getSite).mockResolvedValue(site);
  vi.mocked(getCompany).mockResolvedValue(company);
});

function mount() {
  const drafts: ProfileDrafts = { entries: new Map(), pending: new Set() };
  const onReadback = vi.fn();
  const tree = (id: string) => <ProfileCorrectionActions key={id} access={access} siteId={id} drafts={drafts} onReadback={onReadback} />;
  return { ...render(tree(site.id)), tree, onReadback };
}
const button = (name: string) => screen.getByRole("button", { name });
const fill = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value } });
const save = () => fireEvent.click(button("Lưu thay đổi"));

async function open(kind: "Cơ sở" | "Công ty") {
  fireEvent.click(button(`Sửa thông tin ${kind}`));
  await screen.findByLabelText("Lý do hiệu chỉnh");
}

describe("canonical profile correction", () => {
  it("reads Company through canonical Site, PATCHes only the changed field, and applies only GET readback", async () => {
    const { onReadback } = mount();
    await open("Công ty");
    expect(getSite).toHaveBeenCalledWith(site.id, auth, true, null);
    expect(getCompany).toHaveBeenCalledWith(company.id, auth, true, null);
    fill("Tên pháp nhân", "Công ty đã sửa");
    fill("Lý do hiệu chỉnh", "  Sửa tên theo hồ sơ  ");
    const readback = { ...company, legal_name: "Công ty đã sửa (canonical)" };
    vi.mocked(correctCompanyProfile).mockResolvedValue({ ...company, legal_name: "Công ty đã sửa", audit_event_id: "audit-company" });
    vi.mocked(getCompany).mockResolvedValue(readback);
    save();
    expect(correctCompanyProfile).toHaveBeenCalledExactlyOnceWith(company.id, {
      expected: { legal_name: company.legal_name, legal_address: company.legal_address, english_name: null,
        short_name: "A", legal_address_en: null, is_inactive: false },
      changes: { legal_name: "Công ty đã sửa" }, reason: "Sửa tên theo hồ sơ",
    }, auth, true, null);
    expect(await screen.findByText("Mã audit: audit-company")).toBeInTheDocument();
    expect(getCompany).toHaveBeenCalledTimes(2);
    expect(onReadback).toHaveBeenCalledExactlyOnceWith({ kind: "company", value: readback });
    expect(screen.queryByLabelText(/UUID|Legacy|is_inactive/)).not.toBeInTheDocument();
  });

  it("handles multiple Site changes and clear-to-null with a full canonical snapshot", async () => {
    const initial = { ...site, site_name_en: "Old site" };
    vi.mocked(getSite).mockResolvedValue(initial);
    const { onReadback } = mount();
    await open("Cơ sở");
    expect(screen.queryByLabelText(/UUID|Legacy|company_id|GxP|dây chuyền/)).not.toBeInTheDocument();
    fill("Tên tiếng Anh", "");
    fill("Địa chỉ cơ sở", "Địa chỉ mới");
    fill("Lý do hiệu chỉnh", "Sửa địa chỉ");
    const readback = { ...site, site_address: "Địa chỉ mới" };
    vi.mocked(correctSiteProfile).mockResolvedValue({ ...readback, audit_event_id: "audit-site" });
    vi.mocked(getSite).mockResolvedValue(readback);
    save();
    expect(correctSiteProfile).toHaveBeenCalledExactlyOnceWith(site.id, {
      expected: { ...siteExpected, site_name_en: "Old site" }, changes: { site_name_en: null, site_address: "Địa chỉ mới" },
      reason: "Sửa địa chỉ",
    }, auth, true, null);
    expect(await screen.findByText("Mã audit: audit-site")).toBeInTheDocument();
    expect(getSite).toHaveBeenCalledTimes(2);
    expect(onReadback).toHaveBeenCalledExactlyOnceWith({ kind: "site", value: readback });
  });

  it("treats omitted nullable legacy fields as null in expected, without writing unchanged fields", async () => {
    const legacy: Partial<SiteDetail> = { ...site };
    delete legacy.site_name_en;
    delete legacy.site_address_en;
    delete legacy.short_name;
    vi.mocked(getSite).mockResolvedValue(legacy as SiteDetail);
    vi.mocked(correctSiteProfile).mockResolvedValue({ ...site, province_name: "Huế", audit_event_id: "audit-legacy" });
    mount();
    await open("Cơ sở");
    expect(screen.getByLabelText("Tên tiếng Anh")).toHaveValue("");
    fill("Tỉnh/thành phố", "Huế");
    fill("Lý do hiệu chỉnh", "Hiệu chỉnh tỉnh");
    save();
    expect(correctSiteProfile).toHaveBeenCalledExactlyOnceWith(site.id, { expected: siteExpected,
      changes: { province_name: "Huế" }, reason: "Hiệu chỉnh tỉnh" }, auth, true, null);
    await screen.findByText("Mã audit: audit-legacy");
  });

  it("requires an effective change and explanation and blocks clearing a required field", async () => {
    mount();
    await open("Cơ sở");
    fill("Lý do hiệu chỉnh", "Lý do");
    fill("Tên cơ sở", "  Cơ sở A  ");
    expect(button("Lưu thay đổi")).toBeDisabled();
    fill("Tên cơ sở", "  ");
    expect(button("Lưu thay đổi")).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("không được để trống");
    fill("Tên cơ sở", "Cơ sở mới");
    fill("Lý do hiệu chỉnh", "  ");
    expect(button("Lưu thay đổi")).toBeDisabled();
    expect(correctSiteProfile).not.toHaveBeenCalled();
  });

  it.each([[403, "không đủ quyền"], [404, "không còn tồn tại"], [422, "không hợp lệ"]])(
    "keeps the draft and surfaces HTTP %s", async (status, message) => {
      mount();
      await open("Cơ sở");
      fill("Tên cơ sở", "Bản nháp");
      fill("Lý do hiệu chỉnh", "Giải thích");
      vi.mocked(correctSiteProfile).mockRejectedValue(statusError(status));
      save();
      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(screen.getByLabelText("Tên cơ sở", { exact: true })).toHaveValue("Bản nháp");
      expect(screen.getByLabelText("Lý do hiệu chỉnh")).toHaveValue("Giải thích");
      expect(correctSiteProfile).toHaveBeenCalledTimes(1);
    },
  );

  it("synchronizes a 409 for review before allowing an explicit rebased PATCH", async () => {
    mount();
    await open("Cơ sở");
    fill("Địa chỉ cơ sở", "Bản nháp");
    fill("Lý do hiệu chỉnh", "Giải thích");
    const current = { ...site, site_address: "Đã đổi bởi người khác", province_name: "Huế" };
    vi.mocked(getSite).mockResolvedValue(current);
    vi.mocked(correctSiteProfile).mockRejectedValueOnce(statusError(409))
      .mockResolvedValue({ ...current, site_address: "Bản nháp", audit_event_id: "audit-reviewed" });
    save();
    const rebase = await screen.findByRole("button", { name: "Dùng dữ liệu mới để sửa tiếp" });
    expect(screen.getByRole("table", { name: "Đối chiếu hồ sơ hiện tại với bản nháp" })).toHaveTextContent("Đã đổi bởi người khác");
    expect(screen.getByLabelText("Địa chỉ cơ sở", { exact: true })).toHaveValue("Bản nháp");
    expect(screen.queryByRole("button", { name: "Lưu thay đổi" })).not.toBeInTheDocument();
    expect(correctSiteProfile).toHaveBeenCalledTimes(1);
    fireEvent.click(rebase);
    expect(screen.getByLabelText("Tỉnh/thành phố")).toHaveValue("Huế");
    save();
    expect(correctSiteProfile).toHaveBeenLastCalledWith(site.id, {
      expected: { ...siteExpected, site_address: "Đã đổi bởi người khác", province_name: "Huế" },
      changes: { site_address: "Bản nháp" }, reason: "Giải thích",
    }, auth, true, null);
    await screen.findByText("Mã audit: audit-reviewed");
  });

  it("keeps unknown outcome and draft even when explicit readback matches", async () => {
    mount();
    await open("Công ty");
    fill("Tên pháp nhân", "Bản nháp");
    fill("Lý do hiệu chỉnh", "Giải thích");
    vi.mocked(correctCompanyProfile).mockRejectedValue(new TypeError("Timed out"));
    vi.mocked(getCompany).mockResolvedValue({ ...company, legal_name: "Bản nháp" });
    save();
    expect(await screen.findByRole("alert")).toHaveTextContent("Chưa xác định");
    fireEvent.click(button("Kiểm tra hồ sơ hiện tại"));
    expect(await screen.findByRole("table")).toHaveTextContent("Bản nháp");
    expect(screen.queryByText(/Đã lưu|Mã audit/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Tên pháp nhân")).toHaveValue("Bản nháp");
    expect(correctCompanyProfile).toHaveBeenCalledTimes(1);
  });

  it("preserves a pending draft across A → B → A without late response or PATCH replay", async () => {
    const { rerender, tree, onReadback } = mount();
    await open("Cơ sở");
    fill("Tên cơ sở", "Bản nháp A");
    fill("Lý do hiệu chỉnh", "Giải thích");
    let resolve!: (value: SiteDetail & { audit_event_id: string }) => void;
    vi.mocked(correctSiteProfile).mockImplementation(() => new Promise(done => { resolve = done; }));
    save();
    rerender(tree("site-b"));
    vi.mocked(getSite).mockResolvedValue({ ...site, id: "site-b", site_name: "Cơ sở B" });
    await open("Cơ sở");
    expect(screen.getByLabelText("Tên cơ sở", { exact: true })).toHaveValue("Cơ sở B");
    rerender(tree(site.id));
    await open("Cơ sở");
    expect(screen.getByLabelText("Tên cơ sở", { exact: true })).toHaveValue("Bản nháp A");
    await act(async () => resolve({ ...site, site_name: "Tới muộn", audit_event_id: "audit-old" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Chưa xác định");
    expect(screen.queryByText("Mã audit: audit-old")).not.toBeInTheDocument();
    expect(onReadback).not.toHaveBeenCalled();
    expect(correctSiteProfile).toHaveBeenCalledTimes(1);
  });
});
