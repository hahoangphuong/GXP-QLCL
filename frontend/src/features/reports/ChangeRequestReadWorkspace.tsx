import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { ApiAccess } from "../../App";
import { getChangeRequestWorkspace } from "../../lib/api";
import { formatCompactDate, formatStatusLabel } from "../../lib/presentation";
import type { ChangeRequestArtifact, ChangeRequestWorkspace } from "../../types";

type Section = "request" | "details" | "processing" | "documents";
const SECTIONS: Array<{ key: Section; label: string }> = [
  { key: "request", label: "Đề nghị" },
  { key: "details", label: "Chi tiết thay đổi" },
  { key: "processing", label: "Xử lý và chứng nhận" },
  { key: "documents", label: "Tài liệu" },
];

function Field({ label, value }: { label: string; value: string | number | null | undefined }) {
  return <div><dt>{label}</dt><dd>{value === null || value === undefined || value === "" ? "Chưa có" : value}</dd></div>;
}

function ArtifactTable({ title, items }: { title: string; items: ChangeRequestArtifact[] }) {
  return <section className="workspace-section">
    <h4>{title} ({items.length})</h4>
    {!items.length ? <p>Chưa có chứng nhận liên kết.</p> :
      <div className="table-scroll"><table className="dense-table">
        <thead><tr><th>Loại</th><th>Định danh đối tượng</th><th>Nguồn thay đổi</th></tr></thead>
        <tbody>{items.map(item => <tr key={item.link_id}>
          <td>{item.artifact_kind === "certificate" ? "GCN GxP" : "GCN đủ điều kiện"}</td>
          <td>{item.artifact_kind === "certificate" ?
            <Link className="text-link" to={"/reports/certificates/" + encodeURIComponent(item.artifact_id)}>{item.artifact_id}</Link>
            : item.artifact_id}</td>
          <td>{item.source_affected_artifact_id ?? "Chưa có"}</td>
        </tr>)}</tbody>
      </table></div>}
  </section>;
}

export function ChangeRequestReadWorkspace({ access }: { access: ApiAccess }) {
  const { changeRequestId } = useParams();
  const { auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [changeRequestId, accessGeneration, auth, bearerToken, useStubAuth, canLoadSecureApi]);
  const [section, setSection] = useState<Section>("request");
  const [resource, setResource] = useState<{
    owner: object; value: ChangeRequestWorkspace | null; error: string | null;
  } | null>(null);
  const current = resource?.owner === owner ? resource : null;
  const item = current?.value;

  useEffect(() => {
    if (!canLoadSecureApi || !changeRequestId) return;
    let live = true;
    void getChangeRequestWorkspace(changeRequestId, auth, useStubAuth, bearerToken)
      .then(value => {
        if (value.id !== changeRequestId || !value.site_id) {
          throw new Error("Yêu cầu thay đổi không khớp UUID hoặc thiếu Site canonical.");
        }
        if (live) setResource({ owner, value, error: null });
      })
      .catch((error: Error) => {
        if (live) setResource({ owner, value: null, error: error.message });
      });
    return () => { live = false; };
  }, [auth, bearerToken, canLoadSecureApi, changeRequestId, owner, useStubAuth]);

  if (!canLoadSecureApi) return <section className="page-section">
    <h2>Cần đăng nhập</h2><p>Đăng nhập để xem yêu cầu thay đổi được phân quyền.</p>
  </section>;
  if (!changeRequestId) return <p role="alert">Đường dẫn thiếu Change Request UUID.</p>;
  return <section className="page-section">
    <header className="section-title">
      <div><p className="eyebrow">Nghiệp vụ / Thay đổi cơ sở</p><h2>Hồ sơ yêu cầu thay đổi</h2></div>
      <Link className="text-link" to="/reports">Quay lại Báo cáo</Link>
    </header>
    {!current ? <p role="status">Đang tải yêu cầu thay đổi theo UUID...</p>
      : current.error ? <p role="alert">{current.error}</p>
      : item ? <>
        <section className="panel">
          <div className="panel-header"><h3>{item.scope_label ?? "Yêu cầu thay đổi"}</h3>
            <span>{formatStatusLabel(item.state)}</span></div>
          <p className="muted-copy">Mỗi yêu cầu thay đổi thuộc một Site; không tự suy diễn GxP từ Case hay chứng nhận khác của cơ sở.</p>
          <dl className="persisted-version-fields">
            <Field label="Change Request UUID" value={item.id} />
            <Field label="Cơ sở" value={item.facility_name} />
            <Field label="Công ty" value={item.company_name} />
            <Field label="Site UUID" value={item.site_id} />
            <Field label="Mã legacy" value={item.legacy_change_request_id} />
          </dl>
        </section>
        <nav className="report-actions" aria-label="Các phần yêu cầu thay đổi">
          {SECTIONS.map(tab => <button type="button" key={tab.key}
            className={section === tab.key ? "" : "secondary"}
            aria-pressed={section === tab.key}
            onClick={() => setSection(tab.key)}>{tab.label}</button>)}
        </nav>
        {section === "request" && <section className="panel">
          <h3>Thông tin đề nghị</h3>
          <dl className="persisted-version-fields">
            <Field label="Phạm vi thay đổi" value={item.scope_label} />
            <Field label="Nội dung đề nghị" value={item.description} />
            <Field label="Ngày gửi" value={formatCompactDate(item.submitted_on)} />
            <Field label="Người đề nghị" value={item.requester_name} />
            <Field label="Trạng thái" value={formatStatusLabel(item.state)} />
          </dl>
        </section>}
        {section === "details" && <section className="panel">
          <h3>Các mục thay đổi ({item.details.length})</h3>
          {!item.details.length ? <p>Chưa có mục thay đổi chi tiết.</p> :
            <div className="table-scroll"><table className="dense-table">
              <thead><tr><th>Phân loại</th><th>Giá trị cũ</th><th>Giá trị mới</th><th>Đánh giá</th><th>Ghi chú</th></tr></thead>
              <tbody>{item.details.map(detail => <tr key={detail.change_detail_id}>
                <td>{detail.classification_label ?? detail.classification_id ?? "Chưa có"}</td>
                <td>{detail.old_value ?? "Chưa có"}</td><td>{detail.new_value ?? "Chưa có"}</td>
                <td>{detail.approval_status ?? "Chưa có"}</td><td>{detail.note ?? "—"}</td>
              </tr>)}</tbody>
            </table></div>}
        </section>}
        {section === "processing" && <>
          <section className="panel"><h3>Kết quả xử lý</h3>
            <dl className="persisted-version-fields">
              <Field label="Trạng thái hiện hành" value={formatStatusLabel(item.state)} />
              <Field label="Ngày xử lý" value={formatCompactDate(item.handled_on)} />
              <Field label="Người xử lý" value={item.handled_by_name} />
              <Field label="Kết quả" value={item.result_label} />
              <Field label="Ngày hiệu lực" value={formatCompactDate(item.effective_on)} />
              <Field label="Số văn bản chấp thuận" value={item.approval_reference} />
            </dl>
          </section>
          <section className="panel"><h3>Chứng nhận liên quan</h3>
            <ArtifactTable title="Chứng nhận chịu ảnh hưởng" items={item.affected_artifacts} />
            <ArtifactTable title="Chứng nhận được cấp sau thay đổi" items={item.issued_artifacts} />
          </section>
        </>}
        {section === "documents" && <section className="panel">
          <div className="panel-header"><h3>Danh mục tài liệu ({item.documents.items.length})</h3>
            <Link className="text-link" to={"/documents/change-requests/" + encodeURIComponent(item.id)}>
              Xem checklist và phiên bản
            </Link></div>
          {item.documents.items.length === 0 ? <p>Chưa có mục tài liệu được liên kết.</p> :
            <div className="table-scroll"><table className="dense-table">
              <thead><tr><th>Tài liệu</th><th>Trạng thái</th><th>Tệp hiện có</th></tr></thead>
              <tbody>{item.documents.items.map(doc => <tr key={doc.checklist_key}>
                <td>{doc.label}</td><td>{doc.status === "available" ? "Đã có" : "Chưa có"}</td>
                <td>{doc.original_filename ?? "—"}</td>
              </tr>)}</tbody>
            </table></div>}
        </section>}
        <p className="muted-copy">Chế độ xem xét chỉ đọc. Sửa hồ sơ, phê duyệt, chuyển trạng thái và cấp chứng nhận chỉ thực hiện trong workspace đã có kiểm tra quyền và readiness. Trang này không ghi dữ liệu hoặc tự chọn GxP.</p>
      </> : null}
  </section>;
}
