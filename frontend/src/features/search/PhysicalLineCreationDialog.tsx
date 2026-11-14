import { useEffect, useRef, useState, type FormEvent } from "react";

import { createProductionLine, getCompany, getProductionLine, getSite, listSiteProductionLines } from "../../lib/api";
import type { CompanyDetail, ProductionLineMasterRead, SiteDetail, StubAuthState, WorkspaceActionReadiness } from "../../types";
import { emptyPhysicalLineDraft, useCatalogCreateSession, type PhysicalLineCreateIntent } from "./CatalogCreateSession";

function message(error: unknown): string {
  const status = (error as { status?: number } | null)?.status;
  if (status === 401) return "Phiên đăng nhập đã hết hạn; hãy đăng nhập lại.";
  if (status === 403) return "Không có quyền case.edit hoặc quyền đọc bản ghi.";
  if (status === 404) return "Site hoặc ProductionLine canonical không tồn tại.";
  if (status === 409) return "Xung đột canonical; chỉ đọc lại đúng UUID, không gửi lại POST.";
  if (status === 422) return "Dữ liệu không phù hợp hợp đồng backend.";
  return error instanceof Error ? error.message : "Không xác minh được kết quả.";
}

function exactReadback(intent: PhysicalLineCreateIntent, row: ProductionLineMasterRead): boolean {
  return row.id === intent.payload.production_line_id
    && row.site_id === intent.siteId
    && row.code === intent.payload.code
    && row.effective_from === intent.payload.effective_from
    && (row.effective_to ?? null) === (intent.payload.effective_to ?? null);
}

/** A single physical identity is owned by its UUID, not a Site+code tuple. */
export function PhysicalLineCreationDialog({
  open, siteId, action, auth, useStubAuth, bearerToken, accessGeneration, onClose,
}: {
  open: boolean;
  siteId: string | null;
  action: WorkspaceActionReadiness | null;
  auth: StubAuthState;
  useStubAuth: boolean;
  bearerToken?: string | null;
  accessGeneration: number;
  onClose: () => void;
}) {
  const owner = JSON.stringify(["physical-line-create", auth.username, auth.role, accessGeneration, useStubAuth, siteId]);
  const { state, update } = useCatalogCreateSession(owner);
  const { physicalLineDraft: draft, physicalLineIntent: intent } = state;
  const [site, setSite] = useState<SiteDetail | null>(null);
  const [company, setCompany] = useState<CompanyDetail | null>(null);
  const [ownerError, setOwnerError] = useState<string | null>(null);
  const [lines, setLines] = useState<ProductionLineMasterRead[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const fetchEpoch = useRef(0);
  const activeRef = useRef(false);
  const visibleOwnerRef = useRef(owner);
  activeRef.current = open;
  visibleOwnerRef.current = owner;

  const ready = action?.readiness_status === "available";
  const canonicalOwner = Boolean(siteId && site?.id === siteId && company?.id === site?.company_id && !company?.is_inactive);
  const locked = intent !== null;
  const canSubmit = ready && canonicalOwner && !locked
    && draft.confirmedDistinct && draft.code.trim().length > 0 && draft.code.trim().length <= 64
    && draft.physical_identity_evidence_reference.trim().length > 0
    && draft.physical_identity_evidence_reference.trim().length <= 512
    && draft.reason.trim().length > 0 && draft.reason.trim().length <= 10000
    && Boolean(draft.effective_from)
    && (!draft.effective_to || draft.effective_to > draft.effective_from);

  const change = (fields: Partial<typeof draft>) => {
    update((current) => ({ ...current, physicalLineDraft: { ...current.physicalLineDraft, ...fields } }));
  };

  useEffect(() => {
    const epoch = ++fetchEpoch.current;
    setSite(null);
    setCompany(null);
    setOwnerError(null);
    setLines([]);
    setListError(null);
    if (!open || !siteId) return () => { ++fetchEpoch.current; };
    void getSite(siteId, auth, useStubAuth, bearerToken).then(async (siteValue) => {
      if (siteValue.id !== siteId) throw new Error("Site UUID readback không khớp lựa chọn.");
      const companyValue = await getCompany(siteValue.company_id, auth, useStubAuth, bearerToken);
      if (companyValue.id !== siteValue.company_id) throw new Error("Company UUID không khớp owner Site.");
      if (fetchEpoch.current !== epoch) return;
      setSite(siteValue);
      setCompany(companyValue);
    }).catch((error) => {
      if (fetchEpoch.current === epoch) setOwnerError(message(error));
    });
    void listSiteProductionLines(siteId, auth, useStubAuth, bearerToken).then((rows) => {
      if (fetchEpoch.current === epoch) setLines(rows.filter((row) => row.site_id === siteId));
    }).catch((error) => {
      if (fetchEpoch.current === epoch) setListError(message(error));
    });
    return () => { ++fetchEpoch.current; activeRef.current = false; };
  }, [open, siteId, auth.username, auth.role, useStubAuth, bearerToken, accessGeneration]);

  async function verify(original: PhysicalLineCreateIntent) {
    try {
      const row = await getProductionLine(original.payload.production_line_id, auth, useStubAuth, bearerToken);
      if (!exactReadback(original, row)) throw new Error("Canonical GET không khớp UUID/Site/mã/khoảng hiệu lực của intent.");
      let accepted = false;
      update((current) => {
        if (current.physicalLineIntent?.token !== original.token || current.physicalLineIntent.phase === "verified") return current;
        accepted = true;
        return { ...current, physicalLineIntent: {
          ...current.physicalLineIntent, phase: "verified", persisted: row, error: null,
        } };
      });
      if (accepted && activeRef.current && visibleOwnerRef.current === JSON.stringify(["physical-line-create", accessGeneration, useStubAuth, original.siteId])) {
        // Display only the verified identity. Never infer GxP, Case or Certificate.
        setLines((current) => [row, ...current.filter((item) => item.id !== row.id)]);
      }
    } catch (error) {
      update((current) => current.physicalLineIntent?.token !== original.token || current.physicalLineIntent.phase === "verified" ? current : {
        ...current, physicalLineIntent: { ...current.physicalLineIntent, phase: "unverified", error: message(error) },
      });
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit || !siteId) return;
    let admitted: PhysicalLineCreateIntent | null = null;
    update((current) => {
      if (current.physicalLineIntent !== null || !canonicalOwner || !ready) return current;
      const source = current.physicalLineDraft;
      const code = source.code.trim();
      const evidence = source.physical_identity_evidence_reference.trim();
      const reason = source.reason.trim();
      if (!source.confirmedDistinct || !code || code.length > 64 || !source.effective_from
        || (source.effective_to && source.effective_to <= source.effective_from)
        || !evidence || evidence.length > 512 || !reason || reason.length > 10000) return current;
      admitted = {
        token: {}, siteId, phase: "pending", error: null, persisted: null,
        payload: {
          production_line_id: crypto.randomUUID(), code, effective_from: source.effective_from,
          effective_to: source.effective_to || null, physical_identity_evidence_reference: evidence, reason,
        },
      };
      return { ...current, physicalLineIntent: admitted };
    });
    if (!admitted) return;
    const original = admitted as PhysicalLineCreateIntent;
    try {
      await createProductionLine(original.siteId, original.payload, auth, useStubAuth, bearerToken);
    } catch {
      // All uncertain outcomes retain their UUID. No automatic POST replay.
    }
    await verify(original);
  }

  function newIntent() {
    update((current) => current.physicalLineIntent?.phase !== "verified" ? current : {
      ...current, physicalLineIntent: null, physicalLineDraft: emptyPhysicalLineDraft(),
    });
  }

  if (!open) return null;
  return <div className="dialog-backdrop" role="presentation">
    <section aria-labelledby="physical-line-title" aria-modal="true" role="dialog" className="panel reassessment-dialog catalog-create-scroll-dialog">
      <header className="panel-header reassessment-dialog-header">
        <div>
          <h2 id="physical-line-title">Dây chuyền sản xuất vật lý mới</h2>
          <p>Đây là khai báo định danh vật lý, không phải công nhận GMP/GLP, tạo Case hay cấp GCN.</p>
        </div>
      </header>
      <p>Site UUID: <code>{siteId ?? "Chưa chọn Site"}</code></p>
      {site && company ? <p>Site: <strong>{site.site_name}</strong> · Công ty: <strong>{company.legal_name}</strong>{company.is_inactive ? " (ngừng hoạt động)" : ""}</p> : null}
      {ownerError ? <p className="form-error" role="alert">{ownerError}</p> : null}
      {!ready ? <p role="status">Không được phép tạo dây chuyền: {action?.detail ?? "Backend chưa xác nhận readiness."}</p> : null}
      {listError ? <p className="form-error" role="alert">Chưa tải được danh sách dây chuyền: {listError}</p> : null}
      {lines.length ? <p>Hiện có {lines.length} dây chuyền trên Site. Mã trùng không có nghĩa là cùng định danh vật lý.</p> : null}
      <form className="stack-form reassessment-form" onSubmit={(event) => void submit(event)}>
        <label><span>Mã dây chuyền *</span><input aria-label="Mã dây chuyền vật lý" maxLength={64} disabled={locked} required value={draft.code} onChange={(e) => change({ code: e.target.value })} /></label>
        <label><span>Hiệu lực từ *</span><input aria-label="Hiệu lực từ" type="date" disabled={locked} required value={draft.effective_from} onChange={(e) => change({ effective_from: e.target.value })} /></label>
        <label><span>Hiệu lực đến (không bắt buộc, exclusive)</span><input aria-label="Hiệu lực đến" type="date" disabled={locked} min={draft.effective_from || undefined} value={draft.effective_to ?? ""} onChange={(e) => change({ effective_to: e.target.value || null })} /></label>
        {draft.effective_to && draft.effective_from && draft.effective_to <= draft.effective_from ? <p className="form-error" role="alert">Ngày kết thúc phải sau ngày bắt đầu.</p> : null}
        <label><span>Tham chiếu bằng chứng định danh vật lý *</span><textarea aria-label="Bằng chứng định danh vật lý" maxLength={512} disabled={locked} required value={draft.physical_identity_evidence_reference} onChange={(e) => change({ physical_identity_evidence_reference: e.target.value })} /></label>
        <label><span>Lý do khai báo *</span><textarea aria-label="Lý do khai báo dây chuyền" maxLength={10000} disabled={locked} required value={draft.reason} onChange={(e) => change({ reason: e.target.value })} /></label>
        <label><input aria-label="Xác nhận định danh vật lý độc lập" type="checkbox" disabled={locked} checked={draft.confirmedDistinct} onChange={(e) => change({ confirmedDistinct: e.target.checked })} /> Tôi xác nhận đây là thực thể vật lý được nhận diện từ bằng chứng riêng, không suy ra từ mã legacy/GxP/Case/GCN.</label>
        {intent?.phase === "pending" ? <p role="status">Đã gửi một lần. Đang đọc lại canonical theo UUID đã cấp.</p> : null}
        {intent?.phase === "unverified" ? <p className="form-error" role="alert">Chưa xác minh được kết quả: {intent.error}. UUID và payload đang được khóa; không gửi POST lại.</p> : null}
        {intent?.phase === "verified" && intent.persisted ? <p role="status">Đã xác minh dây chuyền UUID <code>{intent.persisted.id}</code> thuộc Site <code>{intent.persisted.site_id}</code>. Tham chiếu bằng chứng đã gửi audit, không được xác minh bởi GET; không có GxP/Case/GCN nào được tạo.</p> : null}
        <div className="panel-actions reassessment-dialog-actions">
          <button type="submit" disabled={!canSubmit}>{locked ? "Đã khóa intent" : "Tạo dây chuyền vật lý"}</button>
          {intent?.phase === "unverified" ? <button type="button" onClick={() => void verify(intent)}>Đọc lại canonical</button> : null}
          {intent?.phase === "verified" ? <button type="button" onClick={newIntent}>Tạo dây chuyền khác</button> : null}
          <button type="button" disabled={intent?.phase === "pending" || intent?.phase === "unverified"} onClick={onClose}>Đóng</button>
        </div>
      </form>
    </section>
  </div>;
}
