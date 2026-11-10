import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import type { ApiAccess } from "../App";
import { getBusinessEligibilityDetail, getBusinessEligibilityVersionHistory, getBusinessEligibilityGxpSourceEvidence } from "../lib/api";
import type { BusinessEligibilityDetail, BusinessEligibilityVersionHistory, BusinessEligibilityGxpSourceEvidence } from "../types";
import { BusinessEligibilitySourceEvidence } from "../features/search/BusinessEligibilitySourceEvidence";
import type { EligibilitySourceState } from "../features/search/useBusinessEligibilitySourceEvidence";
import { PersistedCertificateHistory } from "../features/search/PersistedCertificateHistory";
import type { HistoryState } from "../features/search/usePersistedCertificateHistory";
import { BusinessEligibilityDetailFields } from "../features/search/BusinessEligibilityDetailFields";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
type Result = { owner: object; detail: BusinessEligibilityDetail | null; error: string | null };
type HistoryResult = { owner: object; state: HistoryState<BusinessEligibilityVersionHistory> };
type SourceResult = { owner: object; state: EligibilitySourceState };

// A source-return hint is navigation metadata, never evidence of ownership.
// Only an independently verified canonical Certificate Site can enable it.
function relatedChangeRequestPath(state: unknown, certificateSiteId: string): string | null {
  if (!state || typeof state !== "object" || !("relatedChangeRequest" in state)) return null;
  const related = state.relatedChangeRequest;
  if (!related || typeof related !== "object" || !("id" in related) || !("siteId" in related)) return null;
  if (typeof related.id !== "string" || !UUID.test(related.id)
    || typeof related.siteId !== "string" || related.siteId.toLowerCase() !== certificateSiteId.toLowerCase()) return null;
  return `/reports/change-requests/${encodeURIComponent(related.id)}`;
}

function validateOriginalExcelEvidence(value: BusinessEligibilityGxpSourceEvidence, certificateId: string): void {
  if (!value || value.business_eligibility_certificate_id !== certificateId
    || value.evidence_kind !== "original_excel_cells_source_only"
    || value.canonical_links_included !== false
    || !["available", "legacy_identity_missing", "not_in_imported_source"].includes(value.source_status)
    || !Array.isArray(value.groups)
    || (value.source_status === "available" && (value.groups.length !== 4
      || ["GMP", "GLP", "GSP", "GDP"].some(name => value.groups.filter(group => group.source_group === name).length !== 1)))
    || (value.source_status !== "available" && value.groups.length !== 0)) {
    throw new Error("Dữ liệu Excel gốc không khớp chứng nhận hoặc hợp đồng đối chiếu.");
  }
}

function validateHistory(value: BusinessEligibilityVersionHistory, detail: BusinessEligibilityDetail): void {
  const ids = new Set<string>();
  if (!value || value.business_eligibility_certificate_id !== detail.business_eligibility_certificate_id
    || value.site_id !== detail.site_id || value.company_id !== detail.company_id
    || value.gxp_source_tokens_included !== false
    || value.canonical_link_status !== "stored_fk_only_not_validated"
    || value.latest_selection_method !== "max_persisted_version_no"
    || typeof value.aggregate_latest_flag !== "boolean"
    || !Array.isArray(value.versions)) {
    throw new Error("Lịch sử phiên bản không khớp chứng nhận hoặc nguồn dữ liệu canonical.");
  }
  for (const version of value.versions) {
    if (!version || !UUID.test(version.business_eligibility_version_id)
      || !Number.isSafeInteger(version.version_no) || version.version_no < 1
      || !Number.isSafeInteger(version.row_version) || version.row_version < 1
      || ids.has(version.business_eligibility_version_id)
      || !Array.isArray(version.stored_link_records)) {
      throw new Error("Lịch sử phiên bản có định danh hoặc thứ tự không hợp lệ.");
    }
    ids.add(version.business_eligibility_version_id);
    const links = new Set<string>();
    for (const link of version.stored_link_records) {
      if (!link || !UUID.test(link.link_id) || !UUID.test(link.certificate_id) || links.has(link.link_id)) {
        throw new Error("Lịch sử phiên bản có liên kết FK không hợp lệ.");
      }
      links.add(link.link_id);
    }
  }
  if (value.latest_version_id !== null && !ids.has(value.latest_version_id)) {
    throw new Error("Lịch sử phiên bản không chứa phiên bản hiện hành đã chỉ định.");
  }
}

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
  const location = useLocation();
  const [params] = useSearchParams();
  const siteHint = params.get("site_id");
  const invalidId = !eligibilityId || !UUID.test(eligibilityId);
  const invalidSite = siteHint !== null && !UUID.test(siteHint);
  const { auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [eligibilityId, siteHint, auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration]);
  const [response, setResponse] = useState<Result | null>(null);
  const current = response?.owner === owner ? response : null;
  const [historyResult, setHistoryResult] = useState<HistoryResult | null>(null);
  const history = historyResult?.owner === owner
    ? historyResult.state
    : { status: "loading" as const };
  const detail = current?.detail;
  const relatedReturn = detail ? relatedChangeRequestPath(location.state, detail.site_id) : null;
  const [sourceResult, setSourceResult] = useState<SourceResult | null>(null);
  const sourceEvidence: EligibilitySourceState = sourceResult?.owner === owner
    ? sourceResult.state : { status: "loading" };
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

  useEffect(() => {
    if (!canLoadSecureApi || !detail || !eligibilityId || invalidId || invalidSite) return;
    let live = true;
    const controller = new AbortController();
    void getBusinessEligibilityVersionHistory(eligibilityId, auth, useStubAuth, bearerToken, controller.signal)
      .then(value => {
        validateHistory(value, detail);
        if (live) setHistoryResult({ owner, state: { status: "ready", data: value } });
      })
      .catch((error: Error & { status?: number }) => {
        if (live) setHistoryResult({ owner, state: {
          status: "error", httpStatus: typeof error.status === "number" ? error.status : null,
        } });
      });
    return () => { live = false; controller.abort(); };
  }, [owner, detail, eligibilityId, invalidId, invalidSite, auth, useStubAuth, bearerToken, canLoadSecureApi]);

  useEffect(() => {
    if (!canLoadSecureApi || !detail || !eligibilityId || invalidId || invalidSite) return;
    let live = true;
    const controller = new AbortController();
    void getBusinessEligibilityGxpSourceEvidence(eligibilityId, auth, useStubAuth, bearerToken, controller.signal)
      .then(value => {
        validateOriginalExcelEvidence(value, eligibilityId);
        if (live) setSourceResult({ owner, state: { status: "ready", data: value } });
      })
      .catch((error: Error & { status?: number }) => {
        if (live) setSourceResult({ owner, state: {
          status: "error", httpStatus: typeof error.status === "number" ? error.status : null,
        } });
      });
    return () => { live = false; controller.abort(); };
  }, [owner, detail, eligibilityId, invalidId, invalidSite, auth, useStubAuth, bearerToken, canLoadSecureApi]);

  if (!canLoadSecureApi) return <section className="page-section"><h2>Cần đăng nhập</h2><p>Đăng nhập để xem chi tiết giấy đủ điều kiện.</p></section>;
  return <section className="page-section">
    <header className="section-title"><div><p className="eyebrow">Chứng nhận / Chỉ đọc</p>
      <h2>Giấy chứng nhận đủ điều kiện kinh doanh dược</h2></div>
      <Link className="text-link" to={relatedReturn ?? backLink}>{relatedReturn ? "Quay lại yêu cầu thay đổi" : "Quay lại danh sách Site"}</Link>
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
        <PersistedCertificateHistory kind="ddk" state={history} />
        <BusinessEligibilitySourceEvidence state={sourceEvidence} />
        <p><Link className="text-link" to={`/documents/business-eligibility-certificates/${encodeURIComponent(current.detail.business_eligibility_certificate_id)}${siteHint ? `?return_site_id=${encodeURIComponent(siteHint)}` : ""}`}>Xem metadata tài liệu đã đăng ký</Link></p>
        <p className="muted-copy">Metadata tài liệu không đồng nghĩa tệp binary hay bản gốc đã ký được xác minh.</p>
      </section>}
  </section>;
}
