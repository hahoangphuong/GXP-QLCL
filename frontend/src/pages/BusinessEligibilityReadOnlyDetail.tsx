import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import type { ApiAccess } from "../App";
import { getBusinessEligibilityDetail } from "../lib/api";
import type { BusinessEligibilityDetail } from "../types";
import { BusinessEligibilityDetailFields } from "../features/search/BusinessEligibilityDetailFields";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
type Result = { owner: object; detail: BusinessEligibilityDetail | null; error: string | null };

function validateDetail(detail: BusinessEligibilityDetail, id: string, expectedSite: string | null): void {
  if (!detail || detail.business_eligibility_certificate_id !== id
    || !UUID.test(detail.site_id) || !UUID.test(detail.company_id)
    || (expectedSite !== null && detail.site_id.toLowerCase() !== expectedSite.toLowerCase())
    || !Number.isSafeInteger(detail.row_version) || detail.row_version < 1
    || typeof detail.latest_flag !== "boolean"
    || !Array.isArray(detail.linked_gxp_certificates)
    || new Set(detail.linked_gxp_certificates.map(item => item.certificate_id)).size !== detail.linked_gxp_certificates.length
    || detail.linked_gxp_certificates.some(item => !UUID.test(item.certificate_id))) {
    throw new Error("Chi tiết giấy đủ điều kiện không khớp chứng nhận, Site hoặc dữ liệu canonical.");
  }
}

/** Authorized, metadata-only business record detail. Never renders mutation actions. */
export function BusinessEligibilityReadOnlyDetail({ access }: { access: ApiAccess }) {
  const { eligibilityId } = useParams();
  const [params] = useSearchParams();
  const siteHint = params.get("site_id");
  const invalidId = !eligibilityId || !UUID.test(eligibilityId);
  const invalidSite = siteHint !== null && !UUID.test(siteHint);
  const { auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [eligibilityId, siteHint, auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration]);
  const [response, setResponse] = useState<Result | null>(null);
  const current = response?.owner === owner ? response : null;
  const backLink = !invalidSite && siteHint
    ? `/documents?${new URLSearchParams({ kind: "business_eligibility", site_id: siteHint })}`
    : "/documents?kind=business_eligibility";

  useEffect(() => {
    if (!canLoadSecureApi || invalidId || invalidSite || !eligibilityId) return;
    let live = true;
    void getBusinessEligibilityDetail(eligibilityId, auth, useStubAuth, bearerToken)
      .then(value => {
        validateDetail(value, eligibilityId, siteHint);
        if (live) setResponse({ owner, detail: value, error: null });
      })
      .catch((error: Error) => {
        if (live) setResponse({ owner, detail: null, error: error.message });
      });
    return () => { live = false; };
  }, [owner, eligibilityId, siteHint, auth, bearerToken, useStubAuth, canLoadSecureApi, invalidId, invalidSite]);

  if (!canLoadSecureApi) return <section className="page-section"><h2>Cần đăng nhập</h2><p>Đăng nhập để xem chi tiết giấy đủ điều kiện.</p></section>;
  return <section className="page-section">
    <header className="section-title"><div><p className="eyebrow">Chứng nhận / Chỉ đọc</p>
      <h2>Giấy chứng nhận đủ điều kiện kinh doanh dược</h2></div>
      <Link className="text-link" to={backLink}>Quay lại danh sách Site</Link>
    </header>
    {invalidId || invalidSite ? <p role="alert">UUID chứng nhận hoặc Site trong đường dẫn không hợp lệ.</p>
      : !current ? <p role="status">Đang xác minh chi tiết giấy đủ điều kiện...</p>
      : current.error ? <p role="alert">{current.error}</p>
      : current.detail && <section className="panel">
        <p className="muted-copy">Bản ghi nghiệp vụ chỉ đọc. Không xác minh bản gốc có chữ ký, không tạo, cập nhật hoặc ban hành GCN tại đây.</p>
        <dl className="persisted-version-fields">
          <div><dt>Certificate UUID</dt><dd>{current.detail.business_eligibility_certificate_id}</dd></div>
          <div><dt>Site UUID</dt><dd>{current.detail.site_id}</dd></div>
          <div><dt>Company UUID</dt><dd>{current.detail.company_id}</dd></div>
          <div><dt>Phiên bản bản ghi</dt><dd>{current.detail.row_version}</dd></div>
          <div><dt>Tình trạng bản ghi</dt><dd>{current.detail.latest_flag ? "Được đánh dấu hiện hành" : "Không còn đánh dấu hiện hành"}</dd></div>
        </dl>
        <BusinessEligibilityDetailFields detail={current.detail} />
        <p><Link className="text-link" to={`/documents/business-eligibility-certificates/${encodeURIComponent(current.detail.business_eligibility_certificate_id)}${siteHint ? `?return_site_id=${encodeURIComponent(siteHint)}` : ""}`}>Xem metadata tài liệu đã đăng ký</Link></p>
        <p className="muted-copy">Metadata tài liệu không đồng nghĩa tệp binary hay bản gốc đã ký được xác minh.</p>
      </section>}
  </section>;
}
