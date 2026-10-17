import type { CertificateDocumentMetadataState } from "./useCertificateDocumentMetadata";

function errorMessage(httpStatus: number | null): string {
  if (httpStatus === 401) return "Phiên đăng nhập không còn hợp lệ để xem metadata tài liệu.";
  if (httpStatus === 403) return "Không có quyền xem metadata tài liệu.";
  if (httpStatus === 404) return "Không tìm thấy chủ sở hữu tài liệu trong phạm vi truy cập.";
  if (httpStatus === 409) return "Metadata tài liệu có quan hệ chủ sở hữu không nhất quán.";
  return "Chưa tải được metadata tài liệu.";
}

export function CertificateDocumentMetadata({ state }: { state: CertificateDocumentMetadataState }) {
  return <section aria-label="Tài liệu đã đăng ký" className="certificate-document-metadata">
    <h4>Tài liệu đã đăng ký</h4>
    {state.status === "idle" ? null : state.status === "loading" ? (
      <p className="workspace-note" role="status">Đang tải metadata tài liệu…</p>
    ) : state.status === "error" ? (
      <p className="form-error" role="alert">{errorMessage(state.httpStatus)}</p>
    ) : state.data.metadata_status === "no_registered_document_metadata" ? (
      <p className="workspace-note" role="status">Chưa có metadata tài liệu được đăng ký. Trạng thái này không xác nhận tài liệu gốc có hay không.</p>
    ) : <>
      <div className="table-scroll certificate-document-metadata-scroll">
        <table aria-label="Metadata tài liệu chứng nhận" className="dense-table certificate-document-metadata-table">
          <thead><tr><th>Nhóm / loại</th><th>Tiêu đề</th><th>Biến thể</th><th>Phiên bản</th><th>Hiện hành</th></tr></thead>
          <tbody>{state.data.documents.map(document => <tr key={document.document_id}>
            <td><strong>{document.family_code}</strong><span>{document.document_type_code}</span></td>
            <td>{document.title ?? "—"}</td>
            <td>{document.registered_variant_count}</td>
            <td>{document.registered_version_count}</td>
            <td>{document.registered_current_version_count}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <p className="workspace-note">Chỉ có metadata đăng ký; chưa xác minh tệp nhị phân hoặc bản gốc có chữ ký.</p>
    </>}
  </section>;
}
