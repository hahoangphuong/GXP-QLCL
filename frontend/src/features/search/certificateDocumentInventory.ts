import type { DocumentOwnerMetadataInventory } from "../../types";

/**
 * Single owner-layer contract for the two certificate document-metadata read surfaces:
 * Search workspace and /documents/:certificateId.
 *
 * This inventory is registration metadata ONLY. No binary, signature, certificate
 * issuance, ownership escalation or document-detail authority follows from it.
 */
export function validCertificateDocumentInventory(
  data: DocumentOwnerMetadataInventory,
  expectedOwnerKind: "certificate" | "business_eligibility_certificate",
  ownerId: string,
): boolean {
  if (!data || data.owner_kind !== expectedOwnerKind || data.owner_id !== ownerId) return false;
  if (data.binary_verified !== false || data.original_signed_document_verified !== false) return false;
  if (!["no_registered_document_metadata", "registered_metadata_only_unverified"].includes(data.metadata_status)) return false;
  if (!Array.isArray(data.documents)) return false;
  if (data.metadata_status === "no_registered_document_metadata" && data.documents.length !== 0) return false;
  if (data.metadata_status === "registered_metadata_only_unverified" && data.documents.length === 0) return false;
  const seen = new Set<string>();
  return data.documents.every(document => {
    if (!document || typeof document.document_id !== "string" || !document.document_id.trim()
      || document.document_id !== document.document_id.trim()
      || typeof document.family_code !== "string" || !document.family_code.trim()
      || typeof document.document_type_code !== "string" || !document.document_type_code.trim()
      || (document.title !== null && typeof document.title !== "string")
      || seen.has(document.document_id)) return false;
    seen.add(document.document_id);
    const counts = [document.registered_variant_count, document.registered_version_count, document.registered_current_version_count];
    return counts.every(count => Number.isSafeInteger(count) && count >= 0)
      && document.registered_current_version_count <= document.registered_version_count;
  });
}
