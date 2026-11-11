import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import type { ApiAccess } from "../App";
import { getBusinessEligibilityDocumentMetadata, getGxpCertificateDocumentMetadata } from "../lib/api";
import type { DocumentOwnerMetadataInventory } from "../types";
import { validCertificateDocumentInventory } from "../features/search/certificateDocumentInventory";
import { reportReturnLocation } from "../features/reports/reportReturnLocation";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
type OwnerKind = "certificate" | "business_eligibility_certificate";
type InventoryResult = { owner: object; value: DocumentOwnerMetadataInventory | null; error: string | null };

// Browser history is a return hint, never an identity, permission or file-authority proof.
function certificateDetailReturn(state: unknown, certificateId: string): string | null {
  if (!state || typeof state !== "object" || !("certificateDetailReturn" in state)) return null;
  const target = state.certificateDetailReturn;
  if (typeof target !== "string" || target.length > 2048) return null;
  const prefix = `/reports/certificates/${encodeURIComponent(certificateId)}`;
  if (!target.startsWith(prefix) || (target.length > prefix.length && target[prefix.length] !== "?")) return null;
  const query = target.slice(prefix.length);
  if (!query) return prefix;
  const params = new URLSearchParams(query.slice(1));
  const allowed = ["site_id", "version_id"];
  if (![...params.keys()].every(key => allowed.includes(key))
    || allowed.some(key => params.getAll(key).length > 1)
    || !params.get("site_id")?.trim()
    || params.get("site_id")!.length > 128
    || (params.has("version_id") && (!params.get("version_id")?.trim() || params.get("version_id")!.length > 128))) return null;
  return target;
}

/** Registration metadata only. Do not follow document IDs into generic detail/binary APIs. */
export function CertificateDocumentRegister({ access, kind }: { access: ApiAccess; kind: OwnerKind }) {
  const { certificateId, eligibilityId } = useParams();
  const location = useLocation();
  const [params] = useSearchParams();
  const siteHint = params.get("return_site_id");
  const backLink = kind === "business_eligibility_certificate"
    ? siteHint && UUID.test(siteHint)
      ? `/documents?${new URLSearchParams({ kind: "business_eligibility", site_id: siteHint })}`
      : "/documents?kind=business_eligibility"
    : "/documents?kind=certificates";
  const id = kind === "certificate" ? certificateId : eligibilityId;
  const reportReturn = kind === "certificate" ? reportReturnLocation(location.state, "certificates") : null;
  const detailReturn = kind === "certificate" && id ? certificateDetailReturn(location.state, id) : null;
  const returnTarget = detailReturn ?? reportReturn ?? backLink;
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
      if (!validCertificateDocumentInventory(value, kind, id)) {
        throw new Error("Nguồn metadata không khớp chứng nhận hoặc trạng thái đăng ký/phiên bản không hợp lệ.");
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
    </div><Link className="text-link" to={returnTarget}>{detailReturn ? "Quay lại chi tiết GCN" : reportReturn ? "Quay lại báo cáo GCN" : "Quay lại danh mục"}</Link></header>
    {!current ? <p role="status">Đang tải metadata tài liệu chứng nhận...</p>
      : current.error ? <p role="alert">{current.error}</p>
      : current.value && <>
        <section className="panel">
          <p>UUID chứng nhận: {current.value.owner_id}</p>
          {detailReturn && reportReturn && <p><Link className="text-link" to={reportReturn}>Quay lại báo cáo GCN</Link></p>}
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
