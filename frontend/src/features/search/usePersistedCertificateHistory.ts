import { useEffect, useState } from "react";
import { getBusinessEligibilityVersionHistory, getGxpCertificateVersionHistory } from "../../lib/api";
import type { BusinessEligibilityVersionHistory, GxpCertificateVersionHistory, StubAuthState } from "../../types";

export type HistoryState<T> = { status: "idle" | "loading" } | { status: "ready"; data: T; selectedVersionId?: string; onSelectVersion?: (id: string) => void } | { status: "error"; httpStatus: number | null };
type Histories = { gxp: GxpCertificateVersionHistory; ddk: BusinessEligibilityVersionHistory };

// Only read ownership lives here. Aggregate selection and current edits stay in SearchPage.
export function usePersistedCertificateHistory<K extends keyof Histories>(kind: K, context: string | null, id: string | null,
  revision: number | undefined, enabled: boolean, auth: StubAuthState, useStubAuth: boolean, bearerToken: string | null): HistoryState<Histories[K]> {
  const [snapshot, setSnapshot] = useState<{ key: string; id: string } | null>(null);
  const key = context && id ? JSON.stringify([kind, context, id]) : null;
  const [request, setRequest] = useState<{
    key: string; revision: number | undefined; auth: StubAuthState; useStubAuth: boolean; bearerToken: string | null; state: HistoryState<Histories[K]>;
  } | null>(null);
  const owned = request?.key === key && request.auth === auth && request.useStubAuth === useStubAuth && request.bearerToken === bearerToken;
  const settled = owned && (revision === undefined || request.revision === revision) && (request.state.status === "ready" || request.state.status === "error");
  useEffect(() => {
    if (!key || !id || !enabled || settled) return;
    const controller = new AbortController();
    let cancelled = false;
    const owner = { key, revision, auth, useStubAuth, bearerToken };
    setRequest({ ...owner, state: { status: "loading" } });
    const load = kind === "gxp" ? getGxpCertificateVersionHistory : getBusinessEligibilityVersionHistory;
    void load(id, auth, useStubAuth, bearerToken, controller.signal).then(data => {
      if (cancelled) return;
      const aggregateId = "certificate_id" in data ? data.certificate_id : data.business_eligibility_certificate_id;
      if (aggregateId !== id || ("gxp_source_tokens_included" in data && (data.gxp_source_tokens_included !== false
        || data.canonical_link_status !== "stored_fk_only_not_validated" || data.latest_selection_method !== "max_persisted_version_no"))) {
        setRequest({ ...owner, state: { status: "error", httpStatus: null } });
        return;
      }
      setRequest({ ...owner, state: { status: "ready", data: data as Histories[K] } });
    }).catch(error => {
      if (cancelled) return;
      const status = (error as { status?: unknown } | null)?.status;
      setRequest({ ...owner, state: { status: "error", httpStatus: typeof status === "number" ? status : null } });
    });
    return () => { cancelled = true; controller.abort(); };
  }, [kind, key, id, enabled, auth, useStubAuth, bearerToken, settled, revision]);
  if (key && owned && request.state.status === "ready" && (revision === undefined || request.revision === revision)) {
    return { ...request.state, selectedVersionId: snapshot?.key === key ? snapshot.id : undefined,
      onSelectVersion: id => setSnapshot({ key, id }) };
  }
  return !key ? { status: "idle" } : owned && (revision === undefined || request.revision === revision) ? request.state : { status: "loading" };
}
