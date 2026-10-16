import { useEffect, useState } from "react";

import {
  getBusinessEligibilityDocumentMetadata,
  getGxpCertificateDocumentMetadata,
} from "../../lib/api";
import type { DocumentOwnerMetadataInventory, StubAuthState } from "../../types";

export type CertificateDocumentKind = "gxp" | "ddk";
export type CertificateDocumentMetadataState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: DocumentOwnerMetadataInventory }
  | { status: "error"; httpStatus: number | null };

function validInventory(data: DocumentOwnerMetadataInventory, kind: CertificateDocumentKind, ownerId: string): boolean {
  const expectedOwnerKind = kind === "gxp" ? "certificate" : "business_eligibility_certificate";
  if (data.owner_kind !== expectedOwnerKind || data.owner_id !== ownerId) return false;
  if (data.binary_verified !== false || data.original_signed_document_verified !== false) return false;
  if (data.metadata_status !== "no_registered_document_metadata"
    && data.metadata_status !== "registered_metadata_only_unverified") return false;
  if (!Array.isArray(data.documents)) return false;
  if (data.metadata_status === "no_registered_document_metadata" && data.documents.length !== 0) return false;
  if (data.metadata_status === "registered_metadata_only_unverified" && data.documents.length === 0) return false;
  const ids = new Set<string>();
  return data.documents.every(document => {
    if (!document || typeof document.document_id !== "string" || !document.document_id
      || typeof document.family_code !== "string" || typeof document.document_type_code !== "string"
      || (document.title !== null && typeof document.title !== "string")
      || ids.has(document.document_id)) return false;
    ids.add(document.document_id);
    return [document.registered_variant_count, document.registered_version_count, document.registered_current_version_count]
      .every(count => Number.isInteger(count) && count >= 0)
      && document.registered_current_version_count <= document.registered_version_count;
  });
}

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
        setRequest({ ...owner, state: validInventory(data, kind, ownerId)
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
