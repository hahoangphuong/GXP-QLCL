import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useLocation, useParams, useSearchParams } from "react-router-dom";
import type { ApiAccess } from "../../App";
import { getChangeRequestWorkspace, getGxpCertificateDetail } from "../../lib/api";
import { formatStatusLabel } from "../../lib/presentation";
import type { ChangeRequestWorkspace, GxpCertificateDetail } from "../../types";
import { reportReturnLocation } from "./reportReturnLocation";

export function ReportRecordDetail({ access, kind }: { access: ApiAccess; kind: "certificates" | "change_requests" }) {
  const params = useParams();
  const location = useLocation();
  const reportReturn = reportReturnLocation(location.state, kind);
  const [searchParams] = useSearchParams();
  const expectedSite = searchParams.get("site_id");
  const id = kind === "certificates" ? params.certificateId : params.changeRequestId;
  const { auth, useStubAuth, bearerToken, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [accessGeneration, auth, bearerToken, useStubAuth, canLoadSecureApi, kind, id, expectedSite]);
  const [result, setResult] = useState<{
    owner: object;
    certificate?: GxpCertificateDetail;
    change?: ChangeRequestWorkspace;
    error?: string;
  } | null>(null);

  useEffect(() => {
    if (!canLoadSecureApi || !id) return;
    let live = true;
    const request = kind === "certificates"
      ? getGxpCertificateDetail(id, auth, useStubAuth, bearerToken).then(value => {
          if (value.certificate_id !== id) throw new Error("Certificate UUID không khớp phản hồi.");
          if (typeof value.site_id !== "string" || !value.site_id.trim() || value.site_id !== value.site_id.trim()
            || (expectedSite !== null && (!expectedSite || value.site_id !== expectedSite))) {
            throw new Error("Site UUID không hợp lệ hoặc không khớp chứng nhận.");
          }
          if (typeof value.certificate_type !== "string" || !value.certificate_type.trim()
            || value.certificate_type !== value.certificate_type.trim()) {
            throw new Error("Loại chứng nhận không hợp lệ.");
          }
          if (live) setResult({ owner, certificate: value });
        })
      : getChangeRequestWorkspace(id, auth, useStubAuth, bearerToken).then(value => {
          if (value.id !== id) throw new Error("Change Request UUID không khớp phản hồi.");
          if (live) setResult({ owner, change: value });
        });
    void request.catch((error: Error) => { if (live) setResult({ owner, error: error.message }); });
    return () => { live = false; };
  }, [auth, bearerToken, canLoadSecureApi, id, kind, owner, useStubAuth, expectedSite]);

  if (!canLoadSecureApi) return <p>Cần đăng nhập để xem chi tiết.</p>;
  if (!id) return <p>Đường dẫn thiếu UUID.</p>;
  const current = result?.owner === owner ? result : null;
  const item = current?.certificate;
  const change = current?.change;
  if (item) {
    if (!["GMP", "GLP", "GMPbb"].includes(item.certificate_type)) {
      return <section className="page-section">
        <header className="section-title"><div><p className="eyebrow">Báo cáo / Chứng nhận</p><h2>Chi tiết GCN {item.certificate_type}</h2></div><Link className="text-link" to={reportReturn ?? "/reports?report=certificates"}>Quay lại Báo cáo</Link></header>
        <section className="panel">
          <p>Chỉ xem thông tin canonical; chưa hỗ trợ chỉnh sửa hoặc cấp GCN loại {item.certificate_type} tại đây.</p>
          <dl className="persisted-version-fields">
            <div><dt>Certificate UUID</dt><dd>{item.certificate_id}</dd></div>
            <div><dt>Site UUID</dt><dd>{item.site_id}</dd></div>
            <div><dt>Loại GxP</dt><dd>{item.certificate_type}</dd></div>
            <div><dt>Số GCN</dt><dd>{item.certificate_number ?? "Chưa có"}</dd></div>
            <div><dt>Cơ sở</dt><dd>{item.facility_name || "Chưa có"}</dd></div>
            <div><dt>Địa chỉ cơ sở</dt><dd>{item.address ?? "Chưa có"}</dd></div>
            <div><dt>Công ty</dt><dd>{item.company_name || "Chưa có"}</dd></div>
            <div><dt>Ngày cấp</dt><dd>{item.issue_date ?? "Chưa có"}</dd></div>
            <div><dt>Ngày hết hạn</dt><dd>{item.expiry_date ?? "Chưa có"}</dd></div>
            <div><dt>Tình trạng</dt><dd>{formatStatusLabel(item.status)}</dd></div>
            <div><dt>Cơ quan cấp</dt><dd>{item.issuing_authority ?? "Chưa có"}</dd></div>
            <div><dt>Tiêu chuẩn</dt><dd>{item.applicable_standard ?? "Chưa có"}</dd></div>
            <div><dt>Giới hạn</dt><dd>{item.limitation_text ?? "Chưa có"}</dd></div>
            <div><dt>Nguồn thông tin</dt><dd>{item.source_description ?? "Chưa có"}</dd></div>
            <div><dt>Case UUID</dt><dd>{item.case_id ?? "Chưa có"}</dd></div>
          </dl>
          <h3>Phạm vi chứng nhận</h3>
          {Array.isArray(item.scopes) && item.scopes.length > 0 ? <ul>{item.scopes.map(scope => <li className="persisted-version-text" key={scope.id}>{scope.scope_text}</li>)}</ul> : <p>Chưa có phạm vi chứng nhận.</p>}
          <p><Link className="text-link" to={`/documents/certificates/${encodeURIComponent(item.certificate_id)}`}>Xem metadata tài liệu</Link></p>
          <p className="muted-copy">Danh mục tài liệu chỉ chứa metadata; chưa xác minh tệp gốc hoặc chữ ký.</p>
        </section>
      </section>;
    }
    const target = new URLSearchParams({ site_id: item.site_id, gxp_type: item.certificate_type,
      context_gxp: item.certificate_type, certificate_id: item.certificate_id, facility_tab: "Giấy chứng nhận GxP" });
    if (item.production_line_id) target.set("production_line_id", item.production_line_id);
    if (item.line_code) target.set("line_code", item.line_code);
    return <Navigate to={`/search?${target}`} replace />;
  }
  return <section className="page-section">
    <header className="section-title"><div><p className="eyebrow">Báo cáo / Chi tiết</p>
      <h2>{kind === "certificates" ? "Chi tiết GCN" : "Chi tiết yêu cầu thay đổi"}</h2>
    </div><Link to={reportReturn ?? (kind === "certificates" ? "/reports?report=certificates" : "/reports")} className="text-link">Quay lại Báo cáo</Link></header>
    {!current ? <p role="status">Đang tải dữ liệu canonical...</p> : current.error ? <p role="alert">{current.error}</p>
      : change ? <section className="panel">
        <h3>{change.scope_label ?? "Yêu cầu thay đổi"}</h3>
        <dl className="persisted-version-fields">
          <div><dt>Change Request UUID</dt><dd>{change.id}</dd></div>
          <div><dt>Cơ sở</dt><dd>{change.facility_name}</dd></div>
          <div><dt>Công ty</dt><dd>{change.company_name}</dd></div>
          <div><dt>Trạng thái</dt><dd>{change.state}</dd></div>
          <div><dt>Ngày gửi</dt><dd>{change.submitted_on ?? "Chưa có"}</dd></div>
          <div><dt>Người đề nghị</dt><dd>{change.requester_name ?? "Chưa có"}</dd></div>
          <div><dt>Nội dung</dt><dd>{change.description ?? "Chưa có"}</dd></div>
        </dl>
      </section> : null}
  </section>;
}
