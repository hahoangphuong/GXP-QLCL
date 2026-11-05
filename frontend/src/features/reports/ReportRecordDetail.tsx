import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import type { ApiAccess } from "../../App";
import { getChangeRequestWorkspace, getGxpCertificateDetail } from "../../lib/api";
import type { ChangeRequestWorkspace, GxpCertificateDetail } from "../../types";

export function ReportRecordDetail({ access, kind }: { access: ApiAccess; kind: "certificates" | "change_requests" }) {
  const params = useParams();
  const id = kind === "certificates" ? params.certificateId : params.changeRequestId;
  const { auth, useStubAuth, bearerToken, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [accessGeneration, auth, bearerToken, useStubAuth, canLoadSecureApi, kind, id]);
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
          if (live) setResult({ owner, certificate: value });
        })
      : getChangeRequestWorkspace(id, auth, useStubAuth, bearerToken).then(value => {
          if (value.id !== id) throw new Error("Change Request UUID không khớp phản hồi.");
          if (live) setResult({ owner, change: value });
        });
    void request.catch((error: Error) => { if (live) setResult({ owner, error: error.message }); });
    return () => { live = false; };
  }, [auth, bearerToken, canLoadSecureApi, id, kind, owner, useStubAuth]);

  if (!canLoadSecureApi) return <p>Cần đăng nhập để xem chi tiết.</p>;
  if (!id) return <p>Đường dẫn thiếu UUID.</p>;
  const current = result?.owner === owner ? result : null;
  const item = current?.certificate;
  const change = current?.change;
  if (item) {
    if (!["GMP", "GLP", "GMPbb"].includes(item.certificate_type)) {
      return <section className="page-section"><p role="alert">Chưa hỗ trợ mở trực tiếp GCN loại {item.certificate_type}.</p><Link to="/reports">Quay lại Báo cáo</Link></section>;
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
    </div><Link to="/reports" className="text-link">Quay lại Báo cáo</Link></header>
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
