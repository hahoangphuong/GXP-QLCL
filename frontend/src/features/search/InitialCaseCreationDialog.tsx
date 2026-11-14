import { useEffect, useRef, useState, type FormEvent } from "react";

import { createInitialCase, getCaseDetail, getCompany, getFacilityWorkspace, getSite, listSiteProductionLines } from "../../lib/api";
import type { CaseDetail, CompanyDetail, ProductionLineMasterRead, SiteDetail, StubAuthState, WorkspaceActionReadiness } from "../../types";
import { emptyInitialCaseDraft, useCatalogCreateSession, type InitialCaseIntent } from "./CatalogCreateSession";

type Gxp = "GMP" | "GLP" | "GMPbb";
const supported: Gxp[] = ["GMP", "GLP", "GMPbb"];

function errText(error: unknown): string {
  const code = (error as { status?: number } | null)?.status;
  if (code === 401) return "Phiên đã hết hạn. Hãy xác thực lại trước khi thao tác.";
  if (code === 403) return "Không có quyền tạo hoặc đọc hồ sơ.";
  if (code === 404) return "Site hoặc Case canonical không tồn tại.";
  if (code === 409) return "Đã có Case/GCN trong ngữ cảnh hoặc UUID xung đột; không POST lại.";
  if (code === 422) return "Dữ liệu không hợp lệ theo hợp đồng backend.";
  return error instanceof Error ? error.message : "Không xác minh được kết quả.";
}

export function exactInitialCaseReadback(intent: InitialCaseIntent, row: CaseDetail): boolean {
  return row.id === intent.payload.case_id
    && row.site_id === intent.siteId
    && row.gxp_type === intent.payload.gxp_type
    && (row.production_line_id ?? null) === (intent.payload.production_line_id ?? null)
    && row.inspection_type?.trim() === intent.payload.inspection_type
    && (row.applicable_standard ?? null) === (intent.payload.applicable_standard ?? null)
    && row.state === "draft"
    && row.legacy_inspection_id === null
    && row.legacy_inspection_code === null;
}

export function InitialCaseCreationDialog({
  open, siteId, auth, useStubAuth, bearerToken, accessGeneration, onClose, onVerifiedOpen,
}: {
  open: boolean;
  siteId: string | null;
  auth: StubAuthState;
  useStubAuth: boolean;
  bearerToken?: string | null;
  accessGeneration: number;
  onClose: () => void;
  onVerifiedOpen: (caseId: string) => void;
}) {
  // Selection must survive dialog unmount/navigation inside one App session.
  // Keep it under the Site owner, separate from the per-GxP/line create intent.
  const selectionOwner = JSON.stringify(["initial-case-selection", auth.username, auth.role, accessGeneration, useStubAuth, siteId]);
  const { state: selection, update: updateSelection } = useCatalogCreateSession(selectionOwner);
  const gxp = selection.initialCaseSelectedGxp;
  const lineId = selection.initialCaseSelectedLineId;
  const setGxp = (value: Gxp | "") => updateSelection((current) => ({
    ...current, initialCaseSelectedGxp: value, initialCaseSelectedLineId: "",
  }));
  const setLineId = (value: string) => updateSelection((current) => ({
    ...current, initialCaseSelectedLineId: value,
  }));
  const owner = JSON.stringify(["initial-case-create", auth.username, auth.role, accessGeneration, useStubAuth, siteId, gxp, lineId || null]);
  const { state, update } = useCatalogCreateSession(owner);
  const { initialCaseDraft: draft, initialCaseIntent: intent } = state;
  const [site, setSite] = useState<SiteDetail | null>(null);
  const [company, setCompany] = useState<CompanyDetail | null>(null);
  const [lines, setLines] = useState<ProductionLineMasterRead[]>([]);
  const [ownerError, setOwnerError] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<WorkspaceActionReadiness | null>(null);
  const [readinessContext, setReadinessContext] = useState<string | null>(null);
  const [readinessRevision, setReadinessRevision] = useState(0);
  const [readinessError, setReadinessError] = useState<string | null>(null);
  const ownerEpoch = useRef(0);
  const readinessEpoch = useRef(0);
  const visibleOwnerRef = useRef(owner);
  visibleOwnerRef.current = owner;
  const activeRef = useRef(open);
  activeRef.current = open;

  const validOwner = Boolean(siteId && site?.id === siteId && company?.id === site?.company_id && !company?.is_inactive);
  const lineValid = !lineId || lines.some((line) => line.id === lineId && line.site_id === siteId);
  const context = JSON.stringify([accessGeneration, useStubAuth, siteId, gxp, lineId || null]);
  // A previous context's available signal cannot authorize a new POST.
  const ready = Boolean(gxp) && readinessContext === context && readiness?.readiness_status === "available";
  const locked = Boolean(intent);
  const trimType = draft.inspection_type.trim();
  const trimStandard = draft.applicable_standard.trim();
  const trimReason = draft.reason.trim();
  const valid = ready && validOwner && lineValid && !locked && !state.recoveryJournalError && !selection.recoveryJournalError && draft.acknowledged
    && Boolean(trimType) && trimType.length <= 255 && trimType.toLocaleLowerCase() !== "tái"
    && trimStandard.length <= 255
    && Boolean(trimReason) && trimReason.length <= 10000;

  useEffect(() => {
    const epoch = ++ownerEpoch.current;
    activeRef.current = open;
    setSite(null); setCompany(null); setLines([]); setOwnerError(null);
    if (!open || !siteId) return () => { ++ownerEpoch.current; activeRef.current = false; };
    void Promise.all([
      getSite(siteId, auth, useStubAuth, bearerToken),
      listSiteProductionLines(siteId, auth, useStubAuth, bearerToken),
    ]).then(async ([canonicalSite, availableLines]) => {
      if (canonicalSite.id !== siteId) throw new Error("Site UUID không khớp.");
      const canonicalCompany = await getCompany(canonicalSite.company_id, auth, useStubAuth, bearerToken);
      if (canonicalCompany.id !== canonicalSite.company_id) throw new Error("Company UUID không khớp.");
      if (ownerEpoch.current !== epoch) return;
      setSite(canonicalSite);
      setCompany(canonicalCompany);
      setLines(availableLines.filter((line) => line.site_id === siteId));
    }).catch((error) => {
      if (ownerEpoch.current === epoch) setOwnerError(errText(error));
    });
    return () => { ++ownerEpoch.current; activeRef.current = false; };
  }, [open, siteId, auth.username, auth.role, useStubAuth, bearerToken, accessGeneration]);

  useEffect(() => {
    const epoch = ++readinessEpoch.current;
    setReadiness(null); setReadinessContext(null); setReadinessError(null);
    if (!open || !siteId || !validOwner || !lineValid || !gxp) return () => { ++readinessEpoch.current; };
    void getFacilityWorkspace(siteId, auth, useStubAuth, gxp, null, bearerToken, lineId || null)
      .then((workspace) => {
        if (readinessEpoch.current !== epoch) return;
        const selected = workspace.summary;
        if (selected.site_id !== siteId || selected.selected_gxp_type !== gxp
          || (selected.selected_production_line_id ?? null) !== (lineId || null)) {
          throw new Error("Backend trả readiness không đúng Site/GxP/ProductionLine UUID.");
        }
        setReadiness(workspace.action_readiness.find((item) => item.action_key === "create_initial_case") ?? null);
        setReadinessContext(context);
      })
      .catch((error) => { if (readinessEpoch.current === epoch) setReadinessError(errText(error)); });
    return () => { ++readinessEpoch.current; };
  }, [open, siteId, validOwner, lineValid, gxp, lineId, auth.username, auth.role, useStubAuth, bearerToken, accessGeneration, readinessRevision]);

  const change = (patch: Partial<typeof draft>) => update((current) => ({
    ...current, initialCaseDraft: { ...current.initialCaseDraft, ...patch },
  }));

  async function verify(original: InitialCaseIntent) {
    try {
      const row = await getCaseDetail(original.payload.case_id, auth, useStubAuth, bearerToken);
      if (!exactInitialCaseReadback(original, row)) {
        throw new Error("Canonical Case GET sai UUID/Site/GxP/ProductionLine/type/standard/trạng thái Draft.");
      }
      update((current) => current.initialCaseIntent?.token !== original.token || current.initialCaseIntent.phase === "verified" ? current : {
        ...current, initialCaseIntent: { ...current.initialCaseIntent, phase: "verified", persisted: row, error: null },
      });
    } catch (error) {
      update((current) => current.initialCaseIntent?.token !== original.token || current.initialCaseIntent.phase === "verified" ? current : {
        ...current, initialCaseIntent: { ...current.initialCaseIntent, phase: "unverified", error: errText(error) },
      });
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!siteId || !valid) return;
    let admitted: InitialCaseIntent | null = null;
    update((current) => {
      if (current.initialCaseIntent || !validOwner || !lineValid || !ready) return current;
      const source = current.initialCaseDraft;
      const type = source.inspection_type.trim();
      const standard = source.applicable_standard.trim();
      const reason = source.reason.trim();
      if (!source.acknowledged || !type || type.length > 255 || type.toLocaleLowerCase() === "tái"
        || standard.length > 255 || !reason || reason.length > 10000) return current;
      admitted = {
        token: {}, siteId, phase: "pending", persisted: null, error: null,
        payload: {
          case_id: crypto.randomUUID(), gxp_type: gxp as Gxp, production_line_id: lineId || null,
          inspection_type: type, applicable_standard: standard || null, reason,
        },
      };
      return { ...current, initialCaseIntent: admitted };
    });
    if (!admitted) return;
    const original = admitted as InitialCaseIntent;
    try {
      await createInitialCase(original.siteId, original.payload, auth, useStubAuth, bearerToken);
    } catch {
      // An unknown POST result never admits a new UUID or repeats POST.
    }
    await verify(original);
  }

  function newIntent() {
    update((current) => current.initialCaseIntent?.phase !== "verified" ? current : {
      ...current, initialCaseIntent: null, initialCaseDraft: emptyInitialCaseDraft(),
    });
    setReadiness(null);
    setReadinessContext(null);
    // The prior successful creation occupies this context; the backend must
    // confirm readiness again before the next separately admitted intent.
    setReadinessRevision((revision) => revision + 1);
  }

  if (!open) return null;
  return <div className="dialog-backdrop" role="presentation">
    <section className="panel reassessment-dialog catalog-create-scroll-dialog" aria-labelledby="initial-case-title" aria-modal="true" role="dialog">
      <header className="panel-header reassessment-dialog-header">
        <h2 id="initial-case-title">Hồ sơ kiểm tra đầu tiên</h2>
      </header>
      <p>Chỉ tạo Case ở trạng thái Draft. Không tiếp nhận hồ sơ, không thực hiện kiểm tra, không cấp GMP/GLP hoặc GCN.</p>
      <p>Site UUID: <code>{siteId ?? "Chưa chọn Site"}</code></p>
      {site && company ? <p>Cơ sở: <strong>{site.site_name}</strong>; công ty: <strong>{company.legal_name}</strong>{company.is_inactive ? " (ngừng hoạt động)" : ""}.</p> : null}
      {state.recoveryJournalError || selection.recoveryJournalError ? <p role="alert" className="form-error">{state.recoveryJournalError || selection.recoveryJournalError}</p> : null}
      {ownerError ? <p role="alert" className="form-error">{ownerError}</p> : null}
      <div className="stack-form">
        <label><span>Loại GxP *</span><select aria-label="Loại GxP cho hồ sơ mới" value={gxp} onChange={(e) => setGxp(e.target.value as Gxp | "")}>
          <option value="">Chọn loại GxP</option>
          {supported.map((value) => <option key={value} value={value}>{value}</option>)}
        </select></label>
        <label><span>Dây chuyền vật lý theo UUID (tùy chọn)</span><select aria-label="ProductionLine UUID" value={lineId} onChange={(e) => setLineId(e.target.value)}>
          <option value="">Toàn cơ sở (không có ProductionLine UUID)</option>
          {lines.map((line) => <option key={line.id} value={line.id}>{line.code} — {line.id}</option>)}
        </select></label>
        <p>Định danh dây chuyền lấy từ canonical GET của Site. Mã dây chuyền legacy không phải UUID.</p>
        {readinessError ? <p role="alert" className="form-error">{readinessError}</p> : null}
        {readiness && readiness.readiness_status !== "available" ? <p role="status">Không thể tạo hồ sơ mới: {readiness.detail}</p> : null}
        {readiness?.readiness_status === "available" ? <p role="status">{readiness.detail}</p> : null}
      </div>
      <form className="stack-form reassessment-form" onSubmit={(event) => void submit(event)}>
        <label><span>Loại kiểm tra *</span><input aria-label="Loại kiểm tra hồ sơ đầu tiên" maxLength={255} value={draft.inspection_type} disabled={locked} required onChange={(e) => change({ inspection_type: e.target.value })} placeholder="Nhập theo loại kiểm tra được phê duyệt" /></label>
        <label><span>Tiêu chuẩn áp dụng (nếu có)</span><input aria-label="Tiêu chuẩn áp dụng" maxLength={255} value={draft.applicable_standard} disabled={locked} onChange={(e) => change({ applicable_standard: e.target.value })} /></label>
        <label><span>Lý do tạo hồ sơ *</span><textarea aria-label="Lý do tạo hồ sơ đầu tiên" maxLength={10000} value={draft.reason} disabled={locked} required onChange={(e) => change({ reason: e.target.value })} /></label>
        <label><input type="checkbox" aria-label="Xác nhận chỉ tạo Case Draft" checked={draft.acknowledged} disabled={locked} onChange={(e) => change({ acknowledged: e.target.checked })} /> Tôi xác nhận chỉ mở Case nháp tại đúng Site/GxP/ProductionLine UUID; không kế thừa hồ sơ hoặc GCN cũ.</label>
        {intent?.phase === "pending" ? <p role="status">Đã POST một lần; đang đọc lại chính UUID của Case.</p> : null}
        {intent?.phase === "unverified" ? <p role="alert" className="form-error">Chưa xác minh: {intent.error}. Giữ nguyên UUID/payload và recovery lock; không POST lại.</p> : null}
        {intent?.phase === "verified" && intent.persisted ? <p role="status">Case nháp canonical đã xác minh: <code>{intent.persisted.id}</code>. Chưa chuyển trạng thái, ghi đơn đăng ký hoặc cấp GCN.</p> : null}
        <div className="panel-actions reassessment-dialog-actions">
          <button type="submit" disabled={!valid}>{locked ? "Đã khóa intent" : "Tạo hồ sơ Draft"}</button>
          {intent?.phase === "unverified" ? <button type="button" onClick={() => void verify(intent)}>Đọc lại Case canonical</button> : null}
          {intent?.phase === "verified" ? <button type="button" onClick={() => { if (activeRef.current && visibleOwnerRef.current === owner) onVerifiedOpen(intent.payload.case_id); }}>Mở Case workspace</button> : null}
          {intent?.phase === "verified" ? <button type="button" onClick={newIntent}>Tạo intent mới</button> : null}
          <button type="button" disabled={intent?.phase === "pending" || intent?.phase === "unverified"} onClick={onClose}>Đóng</button>
        </div>
      </form>
    </section>
  </div>;
}
