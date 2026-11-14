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
};

export const emptyCompanyDraft = (): CatalogCreateState["companyDraft"] => ({ legal_name: "", legal_address: "", english_name: "", short_name: "", legal_address_en: "", reason: "" });
export const emptySiteDraft = (): CatalogCreateState["siteDraft"] => ({ site_name: "", site_address: "", site_name_en: "", site_address_en: "", province_name: "", short_name: "", reason: "" });
const initial = (): CatalogCreateState => ({ companyDraft: emptyCompanyDraft(), siteDraft: emptySiteDraft(), companyIntent: null, siteIntent: null, selectedCompanyId: null, physicalLineDraft: emptyPhysicalLineDraft(), physicalLineIntent: null, initialCaseDraft: emptyInitialCaseDraft(), initialCaseIntent: null });

function createStore() {
  const values = new Map<string, CatalogCreateState>();
  const listeners = new Map<string, Set<() => void>>();
  const get = (owner: string) => {
    if (!values.has(owner)) values.set(owner, initial());
    return values.get(owner)!;
  };
  const notify = (owner: string) => listeners.get(owner)?.forEach((listener) => listener());
  return {
    get,
    update(owner: string, update: (current: CatalogCreateState) => CatalogCreateState) {
      const next = update(get(owner));
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
