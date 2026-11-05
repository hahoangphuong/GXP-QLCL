import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
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
  return <section className="page-section">
    <header className="section-title"><div><p className="eyebrow">Báo cáo / Chi tiết</p>
      <h2>{kind === "certificates" ? "Chi tiết GCN" : "Chi tiết yêu cầu thay đổi"}</h2>
    </div><Link to="/reports" className="text-link">Quay lại Báo cáo</Link></header>
    {!current ? <p role="status">Đang tải dữ liệu canonical...</p> : current.error ? <p role="alert">{current.error}</p>
      : item ? <section className="panel">
        <h3>{item.certificate_number ?? item.certificate_id}</h3>
        <dl className="persisted-version-fields">
          <div><dt>Certificate UUID</dt><dd>{item.certificate_id}</dd></div>
          <div><dt>Cơ sở</dt><dd>{item.facility_name}</dd></div>
          <div><dt>Công ty</dt><dd>{item.company_name}</dd></div>
          <div><dt>GxP</dt><dd>{item.certificate_type}</dd></div>
          <div><dt>Ngày cấp</dt><dd>{item.issue_date ?? "Chưa có"}</dd></div>
          <div><dt>Ngày hết hạn</dt><dd>{item.expiry_date ?? "Chưa có"}</dd></div>
          <div><dt>Current</dt><dd>{item.latest_flag ? "Có" : "Không"}</dd></div>
          <div><dt>Trạng thái</dt><dd>{item.status ?? "Chưa xác minh"}</dd></div>
          <div><dt>Phạm vi</dt><dd>{item.scope_summary ?? "Chưa có"}</dd></div>
        </dl>
      </section> : change ? <section className="panel">
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
