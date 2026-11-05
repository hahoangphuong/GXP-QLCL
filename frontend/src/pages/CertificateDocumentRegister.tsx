import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { ApiAccess } from "../App";
import { getBusinessEligibilityDocumentMetadata, getDocumentDetail, getGxpCertificateDocumentMetadata } from "../lib/api";
import type { DocumentDetail, DocumentOwnerMetadataInventory } from "../types";

type OwnerKind = "certificate" | "business_eligibility_certificate";
type InventoryResult = { owner: object; value: DocumentOwnerMetadataInventory | null; error: string | null };
type DetailResult = { owner: object; id: string; value: DocumentDetail | null; error: string | null };

export function CertificateDocumentRegister({
  access, kind,
}: { access: ApiAccess; kind: OwnerKind }) {
  const { certificateId, eligibilityId } = useParams();
  const id = kind === "certificate" ? certificateId : eligibilityId;
  const { auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [kind, id, auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration]);
  const [inventory, setInventory] = useState<InventoryResult | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DetailResult | null>(null);
  const current = inventory?.owner === owner ? inventory : null;
  const currentDocument = current?.value?.documents.find(item => item.document_id === selectedId) ?? null;
  const currentDetail = detail?.owner === owner && detail.id === selectedId ? detail : null;

  useEffect(() => {
    if (!canLoadSecureApi || !id) return;
    let live = true;
    const read = kind === "certificate"
      ? getGxpCertificateDocumentMetadata(id, auth, useStubAuth, bearerToken)
      : getBusinessEligibilityDocumentMetadata(id, auth, useStubAuth, bearerToken);
    void read.then(value => {
      if (value.owner_id !== id || value.owner_kind !== kind
        || value.binary_verified !== false || value.original_signed_document_verified !== false) {
        throw new Error("Nguồn metadata không khớp chứng nhận hoặc trạng thái xác minh.");
      }
      if (live) setInventory({ owner, value, error: null });
    }).catch((error: Error) => {
      if (live) setInventory({ owner, value: null, error: error.message });
    });
    return () => { live = false; };
  }, [owner, id, kind, auth, useStubAuth, bearerToken, canLoadSecureApi]);

  useEffect(() => {
    if (!canLoadSecureApi || !id || !currentDocument) return;
    let live = true;
    const documentId = currentDocument.document_id;
    void getDocumentDetail(documentId, auth, useStubAuth, bearerToken).then(value => {
      if (value.document_id !== documentId || value.case_id || value.capa_cycle_id || value.change_request_id
        || (kind === "certificate"
          ? value.certificate_id !== id || Boolean(value.business_eligibility_certificate_id)
          : value.business_eligibility_certificate_id !== id || Boolean(value.certificate_id))) {
        throw new Error("Tài liệu không thuộc chứng nhận đã chọn.");
      }
      if (live) setDetail({ owner, id: documentId, value, error: null });
    }).catch((error: Error) => {
      if (live) setDetail({ owner, id: documentId, value: null, error: error.message });
    });
    return () => { live = false; };
  }, [owner, id, kind, currentDocument, auth, bearerToken, useStubAuth, canLoadSecureApi]);

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
          <p className="muted-copy">Chỉ có thông tin đăng ký tài liệu. Chưa xác minh tệp binary hoặc bản gốc đã ký.
            Không cung cấp tải, tạo hoặc ban hành chứng nhận tại đây.</p>
          {current.value.metadata_status === "no_registered_document_metadata"
            ? <p>Chưa có metadata tài liệu đăng ký cho chứng nhận này.</p>
            : <p>{current.value.documents.length} tài liệu có metadata đăng ký.</p>}
        </section>
        {current.value.documents.length > 0 && <section className="panel">
          <h3>Danh mục metadata</h3>
          <div className="table-scroll"><table className="dense-table">
            <thead><tr><th>Tài liệu</th><th>Nhóm</th><th>Biến thể</th><th>Phiên bản</th><th>Phiên bản hiện hành đăng ký</th><th>Chi tiết</th></tr></thead>
            <tbody>{current.value.documents.map(item => <tr key={item.document_id}>
              <td>{item.title ?? item.document_type_code}</td>
              <td>{item.family_code}</td>
              <td>{item.registered_variant_count}</td>
              <td>{item.registered_version_count}</td>
              <td>{item.registered_current_version_count}</td>
              <td><button className="secondary" type="button" aria-pressed={selectedId === item.document_id}
                onClick={() => setSelectedId(item.document_id)}>Xem chi tiết</button></td>
            </tr>)}</tbody>
          </table></div>
        </section>}
        {currentDocument && <section className="panel">
          <div className="panel-header"><h3>Chi tiết: {currentDocument.title ?? currentDocument.document_type_code}</h3>
            <button type="button" className="secondary" onClick={() => setSelectedId(null)}>Đóng</button></div>
          {!currentDetail ? <p role="status">Đang tải chi tiết tài liệu...</p>
            : currentDetail.error ? <p role="alert">{currentDetail.error}</p>
            : currentDetail.value && <>
              <p>Document UUID: {currentDetail.value.document_id}</p>
              {currentDetail.value.variants.length === 0 ? <p>Chưa có biến thể đăng ký.</p> :
                <ul>{currentDetail.value.variants.map(variant => <li key={variant.id}>
                  {variant.variant_type} ({variant.language_code}) — {variant.is_active ? "Đang sử dụng" : "Không hoạt động"}
                  <ul>{variant.versions.map(version => <li key={version.id}>
                    Phiên bản {version.version_no}: {version.original_filename ?? "Không có tên tệp"}
                    {version.is_current ? " (Đánh dấu hiện hành)" : " (Lịch sử)"}
                    {version.issued_on ? ` — ${version.issued_on}` : ""}
                  </li>)}</ul>
                </li>)}</ul>}
              <p className="muted-copy">Phiên bản chỉ là metadata; chưa xác minh binary, chữ ký hoặc giá trị pháp lý.</p>
            </>}
        </section>}
      </>}
  </section>;
}
