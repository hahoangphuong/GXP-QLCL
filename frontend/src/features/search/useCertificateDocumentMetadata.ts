import { useEffect, useMemo, useState } from "react";

import {
  getBusinessEligibilityDocumentMetadata,
  getGxpCertificateDocumentMetadata,
} from "../../lib/api";
import type { DocumentOwnerMetadataInventory, StubAuthState } from "../../types";
import { validCertificateDocumentInventory } from "./certificateDocumentInventory";

export type CertificateDocumentKind = "gxp" | "ddk";
export type CertificateDocumentMetadataState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: DocumentOwnerMetadataInventory }
  | { status: "error"; httpStatus: number | null };

// SearchPage owns selection/access context. This hook owns one cancellable metadata read only.
export function useCertificateDocumentMetadata(
  kind: CertificateDocumentKind,
  context: string | null,
  ownerId: string | null,
  auth: StubAuthState,
  useStubAuth: boolean,
  bearerToken: string | null,
): CertificateDocumentMetadataState {
  // Access identity is part of the read owner, not just its effect dependencies.
  // Never retain a previous principal's metadata during a token/role/session switch.
  // A transient object avoids serializing bearer credentials into a state key.
  const owner = useMemo(() => context && ownerId ? {} : null, [
    context, kind, ownerId, auth.username, auth.role, useStubAuth, bearerToken,
  ]);
  const [request, setRequest] = useState<{ owner: object; state: CertificateDocumentMetadataState } | null>(null);

  useEffect(() => {
    if (!owner || !ownerId) return;
    const controller = new AbortController();
    let cancelled = false;
    setRequest({ owner, state: { status: "loading" } });
    const load = kind === "gxp" ? getGxpCertificateDocumentMetadata : getBusinessEligibilityDocumentMetadata;
    void load(ownerId, auth, useStubAuth, bearerToken, controller.signal)
      .then(data => {
        if (cancelled) return;
        setRequest({ owner, state: validCertificateDocumentInventory(data, kind === "gxp" ? "certificate" : "business_eligibility_certificate", ownerId)
          ? { status: "ready", data }
          : { status: "error", httpStatus: null } });
      })
      .catch(error => {
        if (cancelled) return;
        const status = (error as { status?: unknown } | null)?.status;
        setRequest({ owner, state: { status: "error", httpStatus: typeof status === "number" ? status : null } });
      });
    return () => { cancelled = true; controller.abort(); };
  }, [owner, ownerId, kind, auth.role, auth.username, useStubAuth, bearerToken]);

  if (!owner) return { status: "idle" };
  return request?.owner === owner ? request.state : { status: "loading" };
}
