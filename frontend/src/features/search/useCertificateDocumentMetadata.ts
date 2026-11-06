import { useEffect, useState } from "react";

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
  const key = context && ownerId ? JSON.stringify([context, kind, ownerId]) : null;
  const [request, setRequest] = useState<{ key: string; state: CertificateDocumentMetadataState } | null>(null);

  useEffect(() => {
    if (!key || !ownerId) return;
    const controller = new AbortController();
    let cancelled = false;
    const owner = { key };
    setRequest({ ...owner, state: { status: "loading" } });
    const load = kind === "gxp" ? getGxpCertificateDocumentMetadata : getBusinessEligibilityDocumentMetadata;
    void load(ownerId, auth, useStubAuth, bearerToken, controller.signal)
      .then(data => {
        if (cancelled) return;
        setRequest({ ...owner, state: validCertificateDocumentInventory(data, kind === "gxp" ? "certificate" : "business_eligibility_certificate", ownerId)
          ? { status: "ready", data }
          : { status: "error", httpStatus: null } });
      })
      .catch(error => {
        if (cancelled) return;
        const status = (error as { status?: unknown } | null)?.status;
        setRequest({ ...owner, state: { status: "error", httpStatus: typeof status === "number" ? status : null } });
      });
    return () => { cancelled = true; controller.abort(); };
  }, [key, ownerId, kind, auth.role, auth.username, useStubAuth, bearerToken]);

  if (!key) return { status: "idle" };
  return request?.key === key ? request.state : { status: "loading" };
}
