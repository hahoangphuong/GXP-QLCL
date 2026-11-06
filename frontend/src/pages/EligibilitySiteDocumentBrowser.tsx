import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { ApiAccess } from "../App";
import { listSiteBusinessEligibilityCertificates } from "../lib/api";
import type { BusinessEligibilityList, BusinessEligibilityListItem } from "../types";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function verifiedInventory(value: BusinessEligibilityList, siteId: string): BusinessEligibilityListItem[] {
  if (!value || !Array.isArray(value.items)) throw new Error("Danh sách giấy đủ điều kiện không hợp lệ.");
  const seen = new Set<string>();
  for (const item of value.items) {
    if (!item || !UUID.test(item.business_eligibility_certificate_id)
      || !UUID.test(item.site_id) || item.site_id.toLowerCase() !== siteId.toLowerCase()
      || !UUID.test(item.company_id) || typeof item.latest_flag !== "boolean"
      || seen.has(item.business_eligibility_certificate_id.toLowerCase())) {
      throw new Error("Giấy đủ điều kiện không khớp Site canonical hoặc có định danh không hợp lệ.");
    }
    seen.add(item.business_eligibility_certificate_id.toLowerCase());
  }
  return value.items;
}

/** Read-only site-scoped discovery: never promotes a legacy number to a Certificate UUID. */
export function EligibilitySiteDocumentBrowser({ access }: { access: ApiAccess }) {
  const { auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration } = access;
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedSite = searchParams.get("site_id");
  const siteId = requestedSite && UUID.test(requestedSite) ? requestedSite : "";
  const [draftSite, setDraftSite] = useState(siteId);
  const [inputError, setInputError] = useState<string | null>(null);
  useEffect(() => { setDraftSite(siteId); setInputError(null); }, [siteId]);
  const owner = useMemo(() => ({}), [siteId, auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration]);
  const [result, setResult] = useState<{
    owner: object; rows: BusinessEligibilityListItem[] | null; error: string | null;
  } | null>(null);
  const current = result?.owner === owner ? result : null;

  useEffect(() => {
    if (!canLoadSecureApi || !siteId) return;
    let live = true;
    void listSiteBusinessEligibilityCertificates(siteId, auth, useStubAuth, bearerToken)
      .then(value => {
        const rows = verifiedInventory(value, siteId);
        if (live) setResult({ owner, rows, error: null });
      })
      .catch((error: Error) => {
        if (live) setResult({ owner, rows: null, error: error.message });
      });
    return () => { live = false; };
  }, [siteId, owner, auth, useStubAuth, bearerToken, canLoadSecureApi]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextSite = draftSite.trim();
    if (!UUID.test(nextSite)) {
      setInputError("Nhập Site UUID hợp lệ để tra cứu giấy đủ điều kiện.");
      return;
    }
    setInputError(null);
    setSearchParams(previous => {
      const next = new URLSearchParams(previous);
      next.set("kind", "business_eligibility");
      next.set("site_id", nextSite);
      return next;
    });
  }

  if (!canLoadSecureApi) return <p>Cần đăng nhập để tra cứu chứng nhận của Site.</p>;
  return <section className="panel">
    <h3>Tra cứu giấy đủ điều kiện kinh doanh dược theo Site</h3>
    <p className="muted-copy">Danh sách chỉ đọc từ Site UUID canonical. Chọn giấy để xem metadata đã đăng ký; không xác minh bản gốc, chữ ký hoặc mở tải binary.</p>
    <form onSubmit={submit}>
      <label htmlFor="eligibility-document-site-id">Site UUID</label>
      <div className="report-actions">
        <input id="eligibility-document-site-id" value={draftSite}
          onChange={event => { setDraftSite(event.target.value); setInputError(null); }}
          aria-invalid={Boolean(inputError)} placeholder="UUID cơ sở" />
        <button type="submit">Tra cứu theo Site</button>
      </div>
      {(inputError || (requestedSite && !siteId ? "Site UUID trong đường dẫn không hợp lệ." : null)) && <p role="alert">{inputError || "Site UUID trong đường dẫn không hợp lệ."}</p>}
    </form>
    {siteId && (!current ? <p role="status">Đang tải giấy đủ điều kiện của Site...</p>
      : current.error ? <p role="alert">{current.error}</p>
      : current.rows?.length === 0 ? <p>Site chưa có giấy đủ điều kiện được đăng ký trong hệ thống.</p>
      : current.rows && <div className="table-scroll"><table className="dense-table">
        <thead><tr><th>Số giấy</th><th>Ngày cấp</th><th>Trạng thái ghi nhận</th><th>Chi tiết giấy</th><th>Metadata tài liệu</th></tr></thead>
        <tbody>{current.rows.map(item => <tr key={item.business_eligibility_certificate_id}>
          <td>{item.certificate_number ?? "Chưa có số giấy"}</td>
          <td>{item.issued_on ?? "—"}</td>
          <td>{item.current_status_text ?? "Chưa ghi nhận"}</td>
          <td><Link className="text-link" to={`/certificates/business-eligibility/${encodeURIComponent(item.business_eligibility_certificate_id)}?${new URLSearchParams({ site_id: siteId })}`}>Xem chi tiết GCN</Link></td>
          <td><Link className="text-link" to={`/documents/business-eligibility-certificates/${encodeURIComponent(item.business_eligibility_certificate_id)}?${new URLSearchParams({ return_site_id: siteId })}`}>Xem metadata</Link></td>
        </tr>)}</tbody>
      </table></div>)}
  </section>;
}
