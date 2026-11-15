import { useEffect, useRef, useState, type FormEvent } from "react";

import { createProductionLine, getCompany, getProductionLine, getSite } from "../../lib/api";
import type { CompanyDetail, ProductionLineMasterCreateRequest, ProductionLineMasterRead, SiteDetail, StubAuthState, WorkspaceActionReadiness } from "../../types";
import { emptyProductionLineDraft, useCatalogCreateSession, type ProductionLineCreateIntent } from "./CatalogCreateSession";

function newCanonicalId(): string { return crypto.randomUUID(); }

function actionAvailable(action: WorkspaceActionReadiness | null): boolean {
  return action?.readiness_status === "available";
}

function errorMessage(error: unknown): string {
  const status = (error as { status?: number } | null)?.status;
  if (status === 401) return "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.";
  if (status === 403) return "Bạn không có quyền case.edit để tạo dây chuyền.";
  if (status === 404) return "Không tìm thấy Site hoặc ProductionLine canonical.";
  if (status === 409) return "Xung đột canonical. Không gửi lại; hãy đọc lại bản ghi theo UUID của intent.";
  if (status === 422) return "Dữ liệu không hợp lệ theo contract backend.";
  return error instanceof Error ? error.message : "Không thể xác minh kết quả mutation.";
}

function isDefinitiveRejection(error: unknown): boolean {
  const status = (error as { status?: number } | null)?.status;
  return status === 401 || status === 403 || status === 404 || status === 422;
}

function lineMatches(intent: ProductionLineCreateIntent, value: ProductionLineMasterRead): boolean {
  const payload = intent.payload;
  return value.id === payload.production_line_id && value.site_id === intent.siteId && value.code === payload.code
    && value.effective_from === payload.effective_from && (value.effective_to ?? null) === (payload.effective_to ?? null);
}

export function ProductionLineCreationDialog({
  action, auth, bearerToken, onClose, onVerified, open, ownerIdentity, siteId, useStubAuth,
}: {
  action: WorkspaceActionReadiness | null;
  auth: StubAuthState;
  bearerToken?: string | null;
  onClose: () => void;
  onVerified: () => void;
  open: boolean;
  ownerIdentity: string;
  siteId: string | null;
  useStubAuth: boolean;
}) {
  const { state: session, update } = useCatalogCreateSession(ownerIdentity);
  const { productionLineDraft, productionLineIntent } = session;
  const [site, setSite] = useState<SiteDetail | null>(null);
  const [company, setCompany] = useState<CompanyDetail | null>(null);
  const [ownerError, setOwnerError] = useState<string | null>(null);
  const [ownerLoading, setOwnerLoading] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const ownerSequence = useRef(0);
  const dialogEpoch = useRef(0);
  const visibleRef = useRef(open);
  const notifiedIntentRef = useRef<object | null>(null);
  visibleRef.current = open;
  const locked = productionLineIntent?.phase === "pending" || productionLineIntent?.phase === "unverified" || productionLineIntent?.phase === "verified";
  const siteReady = site?.id === siteId && company?.id === site?.company_id && !company.is_inactive;

  const setDraft = (change: (draft: typeof productionLineDraft) => typeof productionLineDraft) => {
    update((current) => ({ ...current, productionLineDraft: change(current.productionLineDraft) }));
  };

  useEffect(() => {
    dialogEpoch.current += 1;
    return () => { dialogEpoch.current += 1; visibleRef.current = false; };
  }, [open, ownerIdentity]);

  useEffect(() => {
    if (!open || !siteId) {
      ++ownerSequence.current;
      setSite(null); setCompany(null); setOwnerError(null); setOwnerLoading(false);
      return;
    }
    const sequence = ++ownerSequence.current;
    setSite(null); setCompany(null); setOwnerError(null); setOwnerLoading(true);
    void getSite(siteId, auth, useStubAuth, bearerToken).then(async (canonicalSite) => {
      const canonicalCompany = await getCompany(canonicalSite.company_id, auth, useStubAuth, bearerToken);
      if (ownerSequence.current === sequence && canonicalSite.id === siteId) {
        setSite(canonicalSite); setCompany(canonicalCompany);
      }
    }).catch((error) => {
      if (ownerSequence.current === sequence) setOwnerError(errorMessage(error));
    }).finally(() => {
      if (ownerSequence.current === sequence) setOwnerLoading(false);
    });
    return () => { if (ownerSequence.current === sequence) ++ownerSequence.current; };
  }, [auth, bearerToken, open, siteId, useStubAuth]);

  // A verified intent can outlive this dialog during a route/tab change.  On
  // the next safe render of the same Site owner, refresh projections without
  // selecting the new line or creating any downstream regulatory record.
  useEffect(() => {
    if (!open || productionLineIntent?.phase !== "verified" || !productionLineIntent.persisted
      || productionLineIntent.siteId !== siteId || notifiedIntentRef.current === productionLineIntent.token) return;
    notifiedIntentRef.current = productionLineIntent.token;
    onVerified();
  }, [onVerified, open, productionLineIntent, siteId]);

  async function verify(intent: ProductionLineCreateIntent, submittedEpoch: number): Promise<boolean> {
    try {
      const persisted = await getProductionLine(intent.payload.production_line_id, auth, useStubAuth, bearerToken);
      if (!lineMatches(intent, persisted)) throw new Error("Bản ghi canonical không khớp UUID, Site UUID hoặc effective interval của intent.");
      let currentOwner = false;
      update((current) => {
        if (current.productionLineIntent?.token !== intent.token) return current;
        currentOwner = true;
        return { ...current, productionLineIntent: { ...current.productionLineIntent, phase: "verified", persisted, error: null } };
      });
      if (currentOwner && dialogEpoch.current === submittedEpoch && visibleRef.current) {
        notifiedIntentRef.current = intent.token;
        onVerified();
      }
      return currentOwner;
    } catch (error) {
      update((current) => current.productionLineIntent?.token === intent.token
        ? { ...current, productionLineIntent: { ...current.productionLineIntent, phase: "unverified", error: errorMessage(error) } }
        : current);
      return false;
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const code = productionLineDraft.code.trim();
    const evidence = productionLineDraft.physical_identity_evidence_reference.trim();
    const reason = productionLineDraft.reason.trim();
    const effectiveFrom = productionLineDraft.effective_from;
    const effectiveTo = productionLineDraft.effective_to?.trim() || null;
    if (!siteId || !actionAvailable(action) || locked || !siteReady || !acknowledged || !code || !evidence || !reason || !effectiveFrom || (effectiveTo !== null && effectiveTo <= effectiveFrom)) return;
    let intent: ProductionLineCreateIntent | null = null;
    let admitted = false;
    update((current) => {
      if (current.productionLineIntent) return current;
      admitted = true;
      const payload: ProductionLineMasterCreateRequest = {
        production_line_id: newCanonicalId(), code, effective_from: effectiveFrom, effective_to: effectiveTo,
        physical_identity_evidence_reference: evidence, reason,
      };
      intent = { siteId, payload, phase: "pending", error: null, persisted: null, token: {} };
      return { ...current, productionLineIntent: intent };
    });
    if (!admitted || !intent) return;
    const admittedIntent = intent as ProductionLineCreateIntent;
    try {
      await createProductionLine(admittedIntent.siteId, admittedIntent.payload, auth, useStubAuth, bearerToken);
    } catch (error) {
      if (isDefinitiveRejection(error)) {
        update((current) => current.productionLineIntent?.token === admittedIntent.token
          ? { ...current, productionLineIntent: { ...current.productionLineIntent, phase: "rejected", error: errorMessage(error) } }
          : current);
        return;
      }
      // 409 and transport errors are ambiguous: one canonical GET of this UUID is the only recovery.
    }
    await verify(admittedIntent, dialogEpoch.current);
  }

  function discardRejected() {
    update((current) => current.productionLineIntent?.phase === "rejected"
      ? { ...current, productionLineIntent: null }
      : current);
  }

  function startAnother() {
    update((current) => current.productionLineIntent?.phase === "verified"
      ? { ...current, productionLineIntent: null, productionLineDraft: emptyProductionLineDraft() }
      : current);
  }

  if (!open) return null;
  const intervalInvalid = Boolean(productionLineDraft.effective_to && productionLineDraft.effective_from && productionLineDraft.effective_to <= productionLineDraft.effective_from);
  return <div className="dialog-backdrop" role="presentation">
    <section aria-labelledby="production-line-create-title" aria-modal="true" className="panel reassessment-dialog" role="dialog">
      <header className="panel-header reassessment-dialog-header"><div><h2 id="production-line-create-title">Dây chuyền mới</h2><p>{action?.detail}</p></div></header>
      <dl className="reassessment-context-grid" aria-label="Ngữ cảnh Site canonical">
        <div><dt>Site UUID</dt><dd>{siteId ?? "Chưa chọn"}</dd></div>
        <div className="reassessment-source-context"><dt>Company / Site</dt><dd>{ownerLoading ? "Đang đọc canonical…" : siteReady ? `${company?.legal_name} / ${site?.site_name}` : "Chưa xác minh canonical"}</dd></div>
      </dl>
      {ownerError ? <p className="form-error" role="alert">{ownerError}</p> : null}
      {company?.is_inactive ? <p className="form-error" role="alert">Company sở hữu Site đã ngừng hoạt động; không thể tạo dây chuyền.</p> : null}
      <form className="stack-form reassessment-form" onSubmit={(event) => void submit(event)}>
        <label><span>Mã dây chuyền *</span><input aria-label="Mã dây chuyền" disabled={locked || !siteReady || !actionAvailable(action)} onChange={(event) => setDraft((draft) => ({ ...draft, code: event.target.value }))} required value={productionLineDraft.code} /></label>
        <label><span>Ngày bắt đầu hiệu lực *</span><input aria-label="Ngày bắt đầu hiệu lực" disabled={locked || !siteReady || !actionAvailable(action)} onChange={(event) => setDraft((draft) => ({ ...draft, effective_from: event.target.value }))} required type="date" value={productionLineDraft.effective_from} /></label>
        <label><span>Ngày kết thúc hiệu lực (exclusive)</span><input aria-label="Ngày kết thúc hiệu lực" disabled={locked || !siteReady || !actionAvailable(action)} onChange={(event) => setDraft((draft) => ({ ...draft, effective_to: event.target.value || null }))} type="date" value={productionLineDraft.effective_to ?? ""} /></label>
        {intervalInvalid ? <p className="form-error" role="alert">Ngày kết thúc phải sau ngày bắt đầu hiệu lực.</p> : null}
        <label><span>Tham chiếu bằng chứng định danh vật lý *</span><input aria-label="Tham chiếu bằng chứng định danh vật lý" disabled={locked || !siteReady || !actionAvailable(action)} onChange={(event) => setDraft((draft) => ({ ...draft, physical_identity_evidence_reference: event.target.value }))} required value={productionLineDraft.physical_identity_evidence_reference} /></label>
        <label><span>Lý do tạo bản ghi *</span><textarea aria-label="Lý do tạo dây chuyền" disabled={locked || !siteReady || !actionAvailable(action)} onChange={(event) => setDraft((draft) => ({ ...draft, reason: event.target.value }))} required value={productionLineDraft.reason} /></label>
        <label className="production-line-acknowledgement"><input aria-label="Xác nhận dây chuyền vật lý riêng biệt" checked={acknowledged} disabled={locked || !siteReady || !actionAvailable(action)} onChange={(event) => setAcknowledged(event.target.checked)} type="checkbox" /><span>Xác nhận đây là dây chuyền vật lý riêng biệt, chưa liên kết GxP, Case hoặc Certificate.</span></label>
        {productionLineIntent?.phase === "unverified" ? <p className="form-error" role="alert">Chưa xác minh: {productionLineIntent.error}. UUID và payload đã bị khóa; chỉ có thể đọc lại canonical.</p> : null}
        {productionLineIntent?.phase === "rejected" ? <p className="form-error" role="alert">Mutation bị từ chối: {productionLineIntent.error}. Không gửi lại cùng intent.</p> : null}
        {productionLineIntent?.phase === "verified" ? <p role="status">Đã xác minh ProductionLine canonical: {productionLineIntent.persisted?.id}. Backend không xác minh độc lập tham chiếu bằng chứng vật lý.</p> : null}
        <div className="panel-actions reassessment-dialog-actions"><button disabled={locked || !siteReady || !acknowledged || !actionAvailable(action) || intervalInvalid || productionLineIntent?.phase === "rejected"} type="submit">{locked ? "Đang xác minh..." : "Tạo dây chuyền"}</button>{productionLineIntent?.phase === "unverified" ? <button onClick={() => void verify(productionLineIntent, dialogEpoch.current)} type="button">Đọc lại canonical</button> : null}{productionLineIntent?.phase === "rejected" ? <button onClick={discardRejected} type="button">Sửa dữ liệu và tạo intent mới</button> : null}{productionLineIntent?.phase === "verified" ? <button onClick={startAnother} type="button">Tạo dây chuyền khác</button> : null}<button disabled={productionLineIntent?.phase === "pending" || productionLineIntent?.phase === "unverified"} onClick={onClose} type="button">Đóng</button></div>
      </form>
    </section>
  </div>;
}
