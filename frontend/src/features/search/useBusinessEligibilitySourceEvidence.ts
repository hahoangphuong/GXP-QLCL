import { useEffect, useState } from "react";
import { getBusinessEligibilityGxpSourceEvidence } from "../../lib/api";
import type { BusinessEligibilityGxpSourceEvidence, StubAuthState } from "../../types";

export type EligibilitySourceState =
  | { status: "idle" | "loading" }
  | { status: "ready"; data: BusinessEligibilityGxpSourceEvidence }
  | { status: "error"; httpStatus: number | null };

// Selection remains owned by SearchPage. This hook owns only its cancellable read.
export function useBusinessEligibilitySourceEvidence(
  context: string | null,
  certificateId: string | null,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken: string | null,
): EligibilitySourceState {
  const key = context && certificateId ? JSON.stringify([context, certificateId]) : null;
  const [request, setRequest] = useState<{
    key: string; state: EligibilitySourceState;
  } | null>(null);
  useEffect(() => {
    if (!key || !certificateId) return;
    const controller = new AbortController();
    let cancelled = false;
    const owner = { key };
    setRequest({ ...owner, state: { status: "loading" } });
    void getBusinessEligibilityGxpSourceEvidence(certificateId, auth, useStubAuth, bearerToken, controller.signal)
      .then(data => {
        if (cancelled) return;
        // A mismatched response is a contract error, never a display fallback.
        const groupsValid = data.source_status !== "available" || (data.groups.length === 4
          && ["GMP", "GLP", "GSP", "GDP"].every(name => data.groups.filter(group => group.source_group === name).length === 1));
        if (data.business_eligibility_certificate_id !== certificateId || !groupsValid
          || data.evidence_kind !== "original_excel_cells_source_only" || data.canonical_links_included !== false) {
          setRequest({ ...owner, state: { status: "error", httpStatus: null } });
          return;
        }
        setRequest({ ...owner, state: { status: "ready", data } });
      })
      .catch(error => {
        if (cancelled) return;
        const status = (error as { status?: unknown } | null)?.status;
        setRequest({ ...owner, state: { status: "error", httpStatus: typeof status === "number" ? status : null } });
      });
    return () => { cancelled = true; controller.abort(); };
  }, [key, certificateId, auth.role, auth.username, useStubAuth, bearerToken]);
  // Close A's visibility in B's first render, before passive effects/cleanup.
  if (!key) return { status: "idle" };
  return request?.key === key ? request.state : { status: "loading" };
}
