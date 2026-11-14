import { createContext, useCallback, useContext, useRef, useSyncExternalStore, type ReactNode } from "react";

import type { CompanyDetail, CompanyMasterCreateRequest, SiteDetail, SiteMasterCreateRequest, ProductionLineMasterRead, ProductionLineMasterCreateRequest, CaseDetail, InitialCaseCreateRequest } from "../../types";

export type CatalogCreatePhase = "idle" | "pending" | "unverified" | "verified";
export type CompanyCreateIntent = { payload: CompanyMasterCreateRequest; phase: CatalogCreatePhase; error: string | null; persisted: CompanyDetail | null; token: object };
export type SiteCreateIntent = { companyId: string; payload: SiteMasterCreateRequest; phase: CatalogCreatePhase; error: string | null; persisted: SiteDetail | null; token: object };
export type PhysicalLineCreateIntent = {
  siteId: string;
  payload: ProductionLineMasterCreateRequest;
  phase: CatalogCreatePhase;
  error: string | null;
  persisted: ProductionLineMasterRead | null;
  token: object;
};
export type PhysicalLineDraft = Omit<ProductionLineMasterCreateRequest, "production_line_id"> & { confirmedDistinct: boolean };
export const emptyPhysicalLineDraft = (): PhysicalLineDraft => ({
  code: "", effective_from: "", effective_to: null, physical_identity_evidence_reference: "",
  reason: "", confirmedDistinct: false,
});

export type InitialCaseIntent = {
  siteId: string;
  payload: InitialCaseCreateRequest;
  phase: CatalogCreatePhase;
  error: string | null;
  persisted: CaseDetail | null;
  token: object;
};
export type InitialCaseDraft = {
  inspection_type: string;
  applicable_standard: string;
  reason: string;
  acknowledged: boolean;
};
export const emptyInitialCaseDraft = (): InitialCaseDraft => ({
  inspection_type: "", applicable_standard: "", reason: "", acknowledged: false,
});

export type CatalogCreateState = {
  companyDraft: Omit<CompanyMasterCreateRequest, "company_id">;
  siteDraft: Omit<SiteMasterCreateRequest, "site_id">;
  companyIntent: CompanyCreateIntent | null;
  siteIntent: SiteCreateIntent | null;
  selectedCompanyId: string | null;
  physicalLineDraft: PhysicalLineDraft;
  physicalLineIntent: PhysicalLineCreateIntent | null;
  initialCaseDraft: InitialCaseDraft;
  initialCaseIntent: InitialCaseIntent | null;
  initialCaseSelectedGxp: "" | "GMP" | "GLP" | "GMPbb";
  initialCaseSelectedLineId: string;
  recoveryJournalError: string | null;
};

export const emptyCompanyDraft = (): CatalogCreateState["companyDraft"] => ({ legal_name: "", legal_address: "", english_name: "", short_name: "", legal_address_en: "", reason: "" });
export const emptySiteDraft = (): CatalogCreateState["siteDraft"] => ({ site_name: "", site_address: "", site_name_en: "", site_address_en: "", province_name: "", short_name: "", reason: "" });
const initial = (): CatalogCreateState => ({ companyDraft: emptyCompanyDraft(), siteDraft: emptySiteDraft(), companyIntent: null, siteIntent: null, selectedCompanyId: null, physicalLineDraft: emptyPhysicalLineDraft(), physicalLineIntent: null, initialCaseDraft: emptyInitialCaseDraft(), initialCaseIntent: null, initialCaseSelectedGxp: "", initialCaseSelectedLineId: "", recoveryJournalError: null });

// A tab-scoped recovery journal, never an authority to replay a mutation.
// Persist only after the intent UUID/payload is admitted; restore every intent
// as unverified, requiring an authorized canonical GET before any successor.
// No bearer tokens, passwords or OIDC claims are written. Owners MUST include
// the current authenticated username, access generation and auth mode.
const JOURNAL_PREFIX = "gxp-catalog-recovery-v1:";
const SELECTION_OWNER_PREFIX = '["initial-case-selection",';
const VALID_GXP = new Set(["GMP", "GLP", "GMPbb"]);

function isSelectionOwner(owner: string): boolean {
  return owner.startsWith(SELECTION_OWNER_PREFIX);
}

function hasSelection(value: CatalogCreateState): boolean {
  return Boolean(value.initialCaseSelectedGxp || value.initialCaseSelectedLineId);
}

function validSelection(value: Partial<CatalogCreateState>): boolean {
  const gxp = value.initialCaseSelectedGxp;
  const line = value.initialCaseSelectedLineId;
  return (gxp === "" || (typeof gxp === "string" && VALID_GXP.has(gxp)))
    && typeof line === "string"
    && (line === "" || /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(line))
    && (line === "" || Boolean(gxp));
}

function hasIntent(value: CatalogCreateState): boolean {
  return Boolean(value.companyIntent || value.siteIntent
    || value.physicalLineIntent || value.initialCaseIntent);
}

function journalStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try { return window.sessionStorage; } catch { return null; }
}

function hydrateIntent<T extends { phase: CatalogCreatePhase; persisted: unknown; token: object; error: string | null }>(
  value: T | null,
): T | null {
  return value ? {
    ...value, token: {}, persisted: null, phase: "unverified" as const,
    error: "Đã khôi phục intent trong tab. Chỉ đọc lại canonical theo UUID; không POST lại.",
  } : null;
}

const CORRUPT_JOURNAL = "Recovery journal không hợp lệ. Khóa tạo mới để đối soát mutation chưa rõ kết quả.";
const UNAVAILABLE_JOURNAL = "Không lưu/đọc được recovery journal trong tab; POST bị chặn.";

function blocked(error: string): CatalogCreateState {
  return { ...initial(), recoveryJournalError: error };
}

function validIntentShape(value: unknown, idField: string, ownerField?: string): boolean {
  if (value == null) return true;
  if (typeof value !== "object" || Array.isArray(value)) return false;
  const row = value as Record<string, unknown>;
  const payload = row.payload;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return false;
  const uuid = (payload as Record<string, unknown>)[idField];
  if (typeof uuid !== "string"
    || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(uuid)) return false;
  return !ownerField || typeof row[ownerField] === "string";
}

function restore(owner: string): CatalogCreateState {
  const fallback = initial();
  const store = journalStorage();
  if (!store) return blocked(UNAVAILABLE_JOURNAL);
  try {
    const raw = store.getItem(JOURNAL_PREFIX + owner);
    if (raw === null) return fallback;
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object" || Array.isArray(value)) return blocked(CORRUPT_JOURNAL);
    const prior = value as Partial<CatalogCreateState>;
    // The selection is routing context only, NEVER a persisted readiness
    // grant. Without it the per-GxP/per-line Case intent is unreachable after
    // reload, so recover it before resolving that exact owner.
    if (isSelectionOwner(owner) && !hasIntent({ ...fallback, ...prior })
      && validSelection(prior)) {
      return { ...fallback,
        initialCaseSelectedGxp: prior.initialCaseSelectedGxp ?? "",
        initialCaseSelectedLineId: prior.initialCaseSelectedLineId ?? "" };
    }
    // The journal is an untrusted hint, never a source of authorization or
    // readiness. Reject malformed data rather than admitting a new write.
    if (!hasIntent({ ...fallback, ...prior })
      || !validIntentShape(prior.companyIntent, "company_id")
      || !validIntentShape(prior.siteIntent, "site_id", "companyId")
      || !validIntentShape(prior.physicalLineIntent, "production_line_id", "siteId")
      || !validIntentShape(prior.initialCaseIntent, "case_id", "siteId")) {
      return blocked(CORRUPT_JOURNAL);
    }
    return {
      ...fallback,
      ...prior,
      recoveryJournalError: null,
      companyIntent: hydrateIntent(prior.companyIntent ?? null),
      siteIntent: hydrateIntent(prior.siteIntent ?? null),
      physicalLineIntent: hydrateIntent(prior.physicalLineIntent ?? null),
      initialCaseIntent: hydrateIntent(prior.initialCaseIntent ?? null),
    };
  } catch { return blocked(CORRUPT_JOURNAL); }
}

function persist(owner: string, current: CatalogCreateState, next: CatalogCreateState) {
  const selectionOwner = isSelectionOwner(owner);
  if (!hasIntent(current) && !hasIntent(next)
      && !(selectionOwner && (hasSelection(current) || hasSelection(next)))) return;
  const storage = journalStorage();
  if (!storage) throw new Error("Không thể lưu recovery lock trong tab; không thực hiện mutation.");
  // A failed write must abort admission *before* the caller executes POST.
  // Preserve verified data for UI continuity, but never trust it on hydration.
  if (hasIntent(next)) storage.setItem(JOURNAL_PREFIX + owner, JSON.stringify(next));
  else if (selectionOwner && hasSelection(next)) {
    // Persist minimal navigation context; no backend evidence, readiness, or
    // authenticated claims. The Case intent itself remains under its UUID owner.
    storage.setItem(JOURNAL_PREFIX + owner, JSON.stringify({
      initialCaseSelectedGxp: next.initialCaseSelectedGxp,
      initialCaseSelectedLineId: next.initialCaseSelectedLineId,
    }));
  } else storage.removeItem(JOURNAL_PREFIX + owner);
}

function createStore() {
  const values = new Map<string, CatalogCreateState>();
  const listeners = new Map<string, Set<() => void>>();
  const get = (owner: string) => {
    if (!values.has(owner)) values.set(owner, restore(owner));
    return values.get(owner)!;
  };
  const notify = (owner: string) => listeners.get(owner)?.forEach((listener) => listener());
  return {
    get,
    update(owner: string, update: (current: CatalogCreateState) => CatalogCreateState) {
      const current = get(owner);
      if (current.recoveryJournalError) return current;
      const next = update(current);
      if (next === current) return current;
      try {
        persist(owner, current, next);
      } catch {
        values.set(owner, { ...current, recoveryJournalError: UNAVAILABLE_JOURNAL });
        notify(owner);
        // Must abort submit before POST even if its callback already captured intent.
        throw new Error(UNAVAILABLE_JOURNAL);
      }
      values.set(owner, next); notify(owner);
      return next;
    },
    subscribe(owner: string, listener: () => void) {
      if (!listeners.has(owner)) listeners.set(owner, new Set());
      listeners.get(owner)!.add(listener);
      return () => listeners.get(owner)?.delete(listener);
    },
  };
}

type Store = ReturnType<typeof createStore>;
const CatalogCreateContext = createContext<Store | null>(null);

export function CatalogCreateSessionRoot({ children }: { children: ReactNode }) {
  const store = useRef<Store | null>(null);
  if (!store.current) store.current = createStore();
  return <CatalogCreateContext.Provider value={store.current}>{children}</CatalogCreateContext.Provider>;
}

export function useCatalogCreateSession(owner: string) {
  const context = useContext(CatalogCreateContext);
  const fallback = useRef<Store | null>(null);
  if (!fallback.current) fallback.current = createStore();
  const store = context ?? fallback.current;
  const subscribe = useCallback((listener: () => void) => store.subscribe(owner, listener), [owner, store]);
  const snapshot = useCallback(() => store.get(owner), [owner, store]);
  const state = useSyncExternalStore(subscribe, snapshot, snapshot);
  const update = useCallback((change: (current: CatalogCreateState) => CatalogCreateState) => store.update(owner, change), [owner, store]);
  return { state, update };
}
