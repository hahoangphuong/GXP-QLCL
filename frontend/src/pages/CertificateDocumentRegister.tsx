import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { ApiAccess } from "../App";
import { getBusinessEligibilityDocumentMetadata, getGxpCertificateDocumentMetadata } from "../lib/api";
import type { DocumentOwnerMetadataInventory } from "../types";

type OwnerKind = "certificate" | "business_eligibility_certificate";
type InventoryResult = { owner: object; value: DocumentOwnerMetadataInventory | null; error: string | null };

/** Registration metadata only. Do not follow document IDs into generic detail/binary APIs. */
export function CertificateDocumentRegister({ access, kind }: { access: ApiAccess; kind: OwnerKind }) {
  const { certificateId, eligibilityId } = useParams();
  const id = kind === "certificate" ? certificateId : eligibilityId;
  const { auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [kind, id, auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration]);
  const [inventory, setInventory] = useState<InventoryResult | null>(null);
  const current = inventory?.owner === owner ? inventory : null;

  useEffect(() => {
    if (!canLoadSecureApi || !id) return;
    let live = true;
    const read = kind === "certificate"
      ? getGxpCertificateDocumentMetadata(id, auth, useStubAuth, bearerToken)
      : getBusinessEligibilityDocumentMetadata(id, auth, useStubAuth, bearerToken);
    void read.then(value => {
      if (value.owner_id !== id || value.owner_kind !== kind
        || value.binary_verified !== false || value.original_signed_document_verified !== false
        || !["no_registered_document_metadata", "registered_metadata_only_unverified"].includes(value.metadata_status)) {
        throw new Error("Nguồn metadata không khớp chứng nhận hoặc trạng thái xác minh.");
      }
      if (value.metadata_status === "no_registered_document_metadata" && value.documents.length !== 0) {
        throw new Error("Trạng thái metadata không khớp danh mục tài liệu.");
      }
      if (new Set(value.documents.map(item => item.document_id)).size !== value.documents.length) {
        throw new Error("Danh mục tài liệu chứa định danh trùng lặp.");
      }
      if (live) setInventory({ owner, value, error: null });
    }).catch((error: Error) => {
      if (live) setInventory({ owner, value: null, error: error.message });
    });
    return () => { live = false; };
  }, [owner, id, kind, auth, useStubAuth, bearerToken, canLoadSecureApi]);

  if (!canLoadSecureApi) return <section className="page-section"><h2>Cần đăng nhập</h2><p>Đăng nhập để đọc metadata tài liệu chứng nhận.</p></section>;
  if (!id) return <p role="alert">Thiếu UUID chứng nhận.</p>;
  return <section className="page-section">
    <header className="section-title"><div>
      <p className="eyebrow">Tài liệu / Chứng nhận</p>
      <h2>{kind === "certificate" ? "Tài liệu GCN GxP" : "Tài liệu giấy đủ điều kiện kinh doanh dược"}</h2>
    </div><Link className="text-link" to="/documents">Quay lại danh mục</Link></header>
    {!current ? <p role="status">Đang tải metadata tài liệu chứng nhận...</p>
      : current.error ? <p role="alert">{current.error}</p>
      : current.value && <>
        <section className="panel">
          <p>UUID chứng nhận: {current.value.owner_id}</p>
          <p className="muted-copy">Chỉ có metadata tài liệu đăng ký; chưa xác minh tệp binary hoặc bản gốc đã ký.
            Không cung cấp phiên bản tệp, tải xuống, tạo hoặc ban hành chứng nhận tại đây.</p>
          {current.value.metadata_status === "no_registered_document_metadata"
            ? <p>Chưa có metadata tài liệu đăng ký cho chứng nhận này.</p>
            : <p>{current.value.documents.length} tài liệu có metadata đăng ký chưa xác minh.</p>}
        </section>
        {current.value.documents.length > 0 && <section className="panel">
          <h3>Danh mục metadata</h3>
          <div className="table-scroll"><table className="dense-table">
            <thead><tr><th>Tài liệu</th><th>Nhóm</th><th>Biến thể đăng ký</th><th>Phiên bản đăng ký</th><th>Phiên bản đánh dấu hiện hành</th></tr></thead>
            <tbody>{current.value.documents.map(item => <tr key={item.document_id}>
              <td>{item.title ?? item.document_type_code}</td>
              <td>{item.family_code}</td>
              <td>{item.registered_variant_count}</td>
              <td>{item.registered_version_count}</td>
              <td>{item.registered_current_version_count}</td>
            </tr>)}</tbody>
          </table></div>
        </section>}
      </>}
  </section>;
}
