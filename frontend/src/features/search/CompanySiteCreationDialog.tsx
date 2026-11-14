import { useEffect, useRef, useState, type FormEvent } from "react";

import { createCompany, createSite, getCompany, getSite, listCompanies } from "../../lib/api";
import type { Company, CompanyDetail, CompanyMasterCreateRequest, SiteDetail, SiteMasterCreateRequest, StubAuthState, WorkspaceActionReadiness } from "../../types";

type CreatePhase = "idle" | "pending" | "unverified" | "verified";
type CompanyIntent = { payload: CompanyMasterCreateRequest; phase: CreatePhase; error: string | null; persisted: CompanyDetail | null };
type SiteIntent = { companyId: string; payload: SiteMasterCreateRequest; phase: CreatePhase; error: string | null; persisted: SiteDetail | null };

const emptyCompany = (): Omit<CompanyMasterCreateRequest, "company_id"> => ({ legal_name: "", legal_address: "", english_name: "", short_name: "", legal_address_en: "", reason: "" });
const emptySite = (): Omit<SiteMasterCreateRequest, "site_id"> => ({ site_name: "", site_address: "", site_name_en: "", site_address_en: "", province_name: "", short_name: "", reason: "" });

function newCanonicalId(): string {
  return crypto.randomUUID();
}

function optional(value: string | null | undefined): string | null {
  const normalized = value?.trim() ?? "";
  return normalized || null;
}

function errorMessage(error: unknown): string {
  const status = (error as { status?: number } | null)?.status;
  if (status === 403) return "Bạn không có quyền case.edit để tạo dữ liệu danh mục.";
  if (status === 404) return "Không tìm thấy Company/Cơ sở canonical cần thao tác.";
  if (status === 409) return "Xung đột canonical. Không gửi lại; hãy đọc lại bản ghi theo UUID của intent.";
  if (status === 422) return "Dữ liệu không hợp lệ theo contract backend.";
  if (status === 401) return "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại trước khi xác minh intent.";
  return error instanceof Error ? error.message : "Không thể xác minh kết quả mutation.";
}

function companyMatches(intent: CompanyMasterCreateRequest, value: CompanyDetail): boolean {
  return value.id === intent.company_id && value.legal_name === intent.legal_name && value.legal_address === intent.legal_address
    && (value.english_name ?? null) === (intent.english_name ?? null) && (value.short_name ?? null) === (intent.short_name ?? null)
    && (value.legal_address_en ?? null) === (intent.legal_address_en ?? null);
}

function siteMatches(intent: SiteIntent, value: SiteDetail): boolean {
  const payload = intent.payload;
  return value.id === payload.site_id && value.company_id === intent.companyId && value.site_name === payload.site_name
    && value.site_address === payload.site_address && (value.site_name_en ?? null) === (payload.site_name_en ?? null)
    && (value.site_address_en ?? null) === (payload.site_address_en ?? null) && (value.province_name ?? null) === (payload.province_name ?? null)
    && (value.short_name ?? null) === (payload.short_name ?? null);
}

function actionAvailable(action: WorkspaceActionReadiness | null): boolean {
  return action?.readiness_status === "available";
}

export function CompanySiteCreationDialog({
  openAction,
  companyAction,
  siteAction,
  auth,
  useStubAuth,
  bearerToken,
  onClose,
  onSiteVerified,
}: {
  openAction: "create_company" | "create_site" | null;
  companyAction: WorkspaceActionReadiness | null;
  siteAction: WorkspaceActionReadiness | null;
  auth: StubAuthState;
  useStubAuth: boolean;
  bearerToken?: string | null;
  onClose: () => void;
  onSiteVerified: (siteId: string) => void;
}) {
  const [companyDraft, setCompanyDraft] = useState(emptyCompany);
  const [siteDraft, setSiteDraft] = useState(emptySite);
  const [companyIntent, setCompanyIntent] = useState<CompanyIntent | null>(null);
  const [siteIntent, setSiteIntent] = useState<SiteIntent | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companiesError, setCompaniesError] = useState<string | null>(null);
  const [companiesLoading, setCompaniesLoading] = useState(false);
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null);
  const [selectedCompanyDetail, setSelectedCompanyDetail] = useState<CompanyDetail | null>(null);
  const [selectedCompanyError, setSelectedCompanyError] = useState<string | null>(null);
  const listSequence = useRef(0);
  const companyReadSequence = useRef(0);
  const selectedCompanyRef = useRef<string | null>(null);
  selectedCompanyRef.current = selectedCompanyId;

  const selectedCompany = companyIntent?.phase === "verified" && companyIntent.persisted && companyIntent.persisted.id === selectedCompanyId
    ? companyIntent.persisted : selectedCompanyDetail;
  const companyOpen = openAction === "create_company";
  const siteOpen = openAction === "create_site" || (companyOpen && companyIntent?.phase === "verified");
  // A verified intent is terminal in this dialog: creating a second record
  // needs an explicit new operator intent, never a second submit by accident.
  const companyLocked = companyIntent?.phase === "pending" || companyIntent?.phase === "unverified" || companyIntent?.phase === "verified";
  const siteLocked = siteIntent?.phase === "pending" || siteIntent?.phase === "unverified" || siteIntent?.phase === "verified";

  useEffect(() => {
    if (!siteOpen) return;
    const sequence = ++listSequence.current;
    setCompaniesLoading(true);
    setCompaniesError(null);
    void listCompanies(auth, useStubAuth, bearerToken).then((value) => {
      if (listSequence.current === sequence) setCompanies(value);
    }).catch((error) => {
      if (listSequence.current === sequence) setCompaniesError(errorMessage(error));
    }).finally(() => {
      if (listSequence.current === sequence) setCompaniesLoading(false);
    });
  }, [auth, bearerToken, siteOpen, useStubAuth]);

  useEffect(() => {
    if (!selectedCompanyId || (companyIntent?.phase === "verified" && companyIntent.persisted?.id === selectedCompanyId)) {
      setSelectedCompanyDetail(null);
      setSelectedCompanyError(null);
      return;
    }
    const sequence = ++companyReadSequence.current;
    setSelectedCompanyDetail(null);
    setSelectedCompanyError(null);
    void getCompany(selectedCompanyId, auth, useStubAuth, bearerToken).then((value) => {
      if (companyReadSequence.current === sequence && selectedCompanyRef.current === value.id) setSelectedCompanyDetail(value);
    }).catch((error) => {
      if (companyReadSequence.current === sequence) setSelectedCompanyError(errorMessage(error));
    });
  }, [auth, bearerToken, companyIntent?.persisted?.id, companyIntent?.phase, selectedCompanyId, useStubAuth]);

  async function verifyCompany(intent: CompanyIntent): Promise<boolean> {
    try {
      const persisted = await getCompany(intent.payload.company_id, auth, useStubAuth, bearerToken);
      if (!companyMatches(intent.payload, persisted)) throw new Error("Bản ghi canonical cùng UUID không khớp payload intent.");
      setCompanyIntent((current) => current === intent ? { ...current, phase: "verified", persisted, error: null } : current);
      setSelectedCompanyId((current) => current ?? persisted.id);
      return true;
    } catch (error) {
      setCompanyIntent((current) => current === intent ? { ...current, phase: "unverified", error: errorMessage(error) } : current);
      return false;
    }
  }

  async function verifySite(intent: SiteIntent): Promise<boolean> {
    try {
      const persisted = await getSite(intent.payload.site_id, auth, useStubAuth, bearerToken);
      if (!siteMatches(intent, persisted)) throw new Error("Bản ghi canonical không khớp Site UUID, Company UUID hoặc payload intent.");
      setSiteIntent((current) => current === intent ? { ...current, phase: "verified", persisted, error: null } : current);
      onSiteVerified(persisted.id);
      return true;
    } catch (error) {
      setSiteIntent((current) => current === intent ? { ...current, phase: "unverified", error: errorMessage(error) } : current);
      return false;
    }
  }

  async function submitCompany(event: FormEvent) {
    event.preventDefault();
    if (!actionAvailable(companyAction) || companyLocked || !companyDraft.legal_name.trim() || !companyDraft.legal_address.trim()) return;
    const intent: CompanyIntent = { phase: "pending", error: null, persisted: null, payload: {
      company_id: newCanonicalId(), legal_name: companyDraft.legal_name.trim(), legal_address: companyDraft.legal_address.trim(),
      english_name: optional(companyDraft.english_name), short_name: optional(companyDraft.short_name), legal_address_en: optional(companyDraft.legal_address_en), reason: optional(companyDraft.reason),
    } };
    setCompanyIntent(intent);
    try {
      await createCompany(intent.payload, auth, useStubAuth, bearerToken);
    } catch {
      // A transport failure has an unknown mutation outcome. The sole recovery is canonical GET by this UUID.
    }
    await verifyCompany(intent);
  }

  async function submitSite(event: FormEvent) {
    event.preventDefault();
    if (!actionAvailable(siteAction) || siteLocked || !selectedCompany || selectedCompany.is_inactive || !siteDraft.site_name.trim() || !siteDraft.site_address.trim()) return;
    const intent: SiteIntent = { companyId: selectedCompany.id, phase: "pending", error: null, persisted: null, payload: {
      site_id: newCanonicalId(), site_name: siteDraft.site_name.trim(), site_address: siteDraft.site_address.trim(),
      site_name_en: optional(siteDraft.site_name_en), site_address_en: optional(siteDraft.site_address_en), province_name: optional(siteDraft.province_name), short_name: optional(siteDraft.short_name), reason: optional(siteDraft.reason),
    } };
    setSiteIntent(intent);
    try {
      await createSite(intent.companyId, intent.payload, auth, useStubAuth, bearerToken);
    } catch {
      // Same UUID is read back; we intentionally never retry POST after an uncertain outcome.
    }
    await verifySite(intent);
  }

  if (!openAction) return null;
  return <div className="dialog-backdrop" role="presentation">
    <section aria-labelledby="master-create-dialog-title" aria-modal="true" className="panel reassessment-dialog" role="dialog">
      <header className="panel-header reassessment-dialog-header"><div><h2 id="master-create-dialog-title">{companyOpen ? "Công ty mới" : "Cơ sở mới"}</h2><p>{companyOpen ? companyAction?.detail : siteAction?.detail}</p></div></header>
      {companyOpen ? <form className="stack-form reassessment-form" onSubmit={(event) => void submitCompany(event)}>
        <label><span>Tên pháp nhân *</span><input aria-label="Tên pháp nhân" disabled={companyLocked || !actionAvailable(companyAction)} onChange={(event) => setCompanyDraft((draft) => ({ ...draft, legal_name: event.target.value }))} required value={companyDraft.legal_name} /></label>
        <label><span>Địa chỉ pháp lý *</span><textarea aria-label="Địa chỉ pháp lý" disabled={companyLocked || !actionAvailable(companyAction)} onChange={(event) => setCompanyDraft((draft) => ({ ...draft, legal_address: event.target.value }))} required value={companyDraft.legal_address} /></label>
        <label><span>Tên tiếng Anh</span><input aria-label="Tên tiếng Anh" disabled={companyLocked} onChange={(event) => setCompanyDraft((draft) => ({ ...draft, english_name: event.target.value }))} value={companyDraft.english_name ?? ""} /></label>
        <label><span>Tên viết tắt</span><input aria-label="Tên viết tắt công ty" disabled={companyLocked} onChange={(event) => setCompanyDraft((draft) => ({ ...draft, short_name: event.target.value }))} value={companyDraft.short_name ?? ""} /></label>
        <label><span>Địa chỉ tiếng Anh</span><textarea aria-label="Địa chỉ tiếng Anh" disabled={companyLocked} onChange={(event) => setCompanyDraft((draft) => ({ ...draft, legal_address_en: event.target.value }))} value={companyDraft.legal_address_en ?? ""} /></label>
        <label><span>Lý do</span><input aria-label="Lý do tạo công ty" disabled={companyLocked} onChange={(event) => setCompanyDraft((draft) => ({ ...draft, reason: event.target.value }))} value={companyDraft.reason ?? ""} /></label>
        {companyIntent?.phase === "unverified" ? <p className="form-error" role="alert">Chưa xác minh: {companyIntent.error}. UUID và intent đã bị khóa; chỉ có thể đọc lại canonical.</p> : null}
        {companyIntent?.phase === "verified" ? <p role="status">Đã xác minh Công ty canonical. Có thể chọn để tạo Cơ sở.</p> : null}
        <div className="panel-actions reassessment-dialog-actions"><button disabled={companyLocked || !actionAvailable(companyAction)} type="submit">{companyLocked ? "Đang xác minh..." : "Tạo Công ty"}</button>{companyIntent?.phase === "unverified" ? <button onClick={() => void verifyCompany(companyIntent)} type="button">Đọc lại canonical</button> : null}<button disabled={companyLocked} onClick={onClose} type="button">Đóng</button></div>
      </form> : null}
      {siteOpen ? <form className="stack-form reassessment-form" onSubmit={(event) => void submitSite(event)}>
        <label><span>Chọn Công ty *</span><select aria-label="Company canonical" disabled={siteLocked || companiesLoading || !actionAvailable(siteAction)} onChange={(event) => setSelectedCompanyId(event.target.value || null)} value={selectedCompanyId ?? ""}><option value="">-- Chọn Company canonical --</option>{companies.map((company) => <option key={company.id} value={company.id}>{company.legal_name} — {company.id}</option>)}</select></label>
        {selectedCompany ? <p>Company đã chọn: <strong>{selectedCompany.legal_name}</strong> ({selectedCompany.id}){selectedCompany.is_inactive ? " — không còn hoạt động" : ""}</p> : null}
        {selectedCompanyError ? <p className="form-error" role="alert">{selectedCompanyError}</p> : null}
        {companiesError ? <p className="form-error" role="alert">{companiesError}</p> : null}
        <label><span>Tên cơ sở *</span><input aria-label="Tên cơ sở" disabled={siteLocked || !selectedCompany || selectedCompany.is_inactive} onChange={(event) => setSiteDraft((draft) => ({ ...draft, site_name: event.target.value }))} required value={siteDraft.site_name} /></label>
        <label><span>Địa chỉ cơ sở *</span><textarea aria-label="Địa chỉ cơ sở" disabled={siteLocked || !selectedCompany} onChange={(event) => setSiteDraft((draft) => ({ ...draft, site_address: event.target.value }))} required value={siteDraft.site_address} /></label>
        <label><span>Tên cơ sở tiếng Anh</span><input aria-label="Tên cơ sở tiếng Anh" disabled={siteLocked || !selectedCompany} onChange={(event) => setSiteDraft((draft) => ({ ...draft, site_name_en: event.target.value }))} value={siteDraft.site_name_en ?? ""} /></label>
        <label><span>Địa chỉ cơ sở tiếng Anh</span><textarea aria-label="Địa chỉ cơ sở tiếng Anh" disabled={siteLocked || !selectedCompany} onChange={(event) => setSiteDraft((draft) => ({ ...draft, site_address_en: event.target.value }))} value={siteDraft.site_address_en ?? ""} /></label>
        <label><span>Tỉnh/thành</span><input aria-label="Tỉnh thành" disabled={siteLocked || !selectedCompany} onChange={(event) => setSiteDraft((draft) => ({ ...draft, province_name: event.target.value }))} value={siteDraft.province_name ?? ""} /></label>
        <label><span>Tên viết tắt</span><input aria-label="Tên viết tắt cơ sở" disabled={siteLocked || !selectedCompany} onChange={(event) => setSiteDraft((draft) => ({ ...draft, short_name: event.target.value }))} value={siteDraft.short_name ?? ""} /></label>
        <label><span>Lý do</span><input aria-label="Lý do tạo cơ sở" disabled={siteLocked || !selectedCompany} onChange={(event) => setSiteDraft((draft) => ({ ...draft, reason: event.target.value }))} value={siteDraft.reason ?? ""} /></label>
        {siteIntent?.phase === "unverified" ? <p className="form-error" role="alert">Chưa xác minh: {siteIntent.error}. UUID và intent đã bị khóa; không tạo successor.</p> : null}
        {siteIntent?.phase === "verified" ? <p role="status">Đã xác minh Cơ sở canonical; không có GxP, ProductionLine, Case hoặc Certificate nào được tạo.</p> : null}
        <div className="panel-actions reassessment-dialog-actions"><button disabled={siteLocked || !selectedCompany || selectedCompany.is_inactive || !actionAvailable(siteAction)} type="submit">{siteLocked ? "Đang xác minh..." : "Tạo Cơ sở"}</button>{siteIntent?.phase === "unverified" ? <button onClick={() => void verifySite(siteIntent)} type="button">Đọc lại canonical</button> : null}<button disabled={siteLocked} onClick={onClose} type="button">Đóng</button></div>
      </form> : null}
    </section>
  </div>;
}
