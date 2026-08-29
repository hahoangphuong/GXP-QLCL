import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { StatusBadge } from "../../components/StatusBadge";
import { formatCompactDate } from "../../lib/presentation";
import type { GxpCertificateDetail, GxpCertificateListItem } from "../../types";

function DetailValue({
  label,
  value,
  multiline = false,
}: {
  label: string;
  value: string | null | undefined;
  multiline?: boolean;
}) {
  return (
    <div className={multiline ? "summary-span" : undefined}>
      <span>{label}</span>
      <strong className={multiline ? "multiline-value" : undefined}>{value || "Chưa có"}</strong>
    </div>
  );
}

export function GxpCertificateWorkspace({
  items,
  listLoading,
  listError,
  selectedCertificateId,
  onSelectCertificate,
  detail,
  detailLoading,
  detailError,
}: {
  items: GxpCertificateListItem[];
  listLoading: boolean;
  listError: string | null;
  selectedCertificateId: string | null;
  onSelectCertificate: (certificateId: string) => void;
  detail: GxpCertificateDetail | null;
  detailLoading: boolean;
  detailError: string | null;
}) {
  if (listError) {
    return <ErrorState message={listError} />;
  }

  if (listLoading && items.length === 0) {
    return <EmptyState title="Đang tải giấy chứng nhận GxP" description="Đang đồng bộ danh mục chứng nhận và chi tiết theo ngữ cảnh đang chọn." />;
  }

  if (!listLoading && items.length === 0) {
    return <EmptyState title="Chưa có giấy chứng nhận GxP" description="Cơ sở hoặc dây chuyền đang chọn chưa có chứng nhận GxP trong dữ liệu hiện hành." />;
  }

  return (
    <div className="certificate-workspace-split">
      <section className="panel panel-tight certificate-list-panel">
        <div className="panel-header">
          <h3>Danh mục GCN GxP</h3>
          <span className="panel-meta">{items.length} giấy</span>
        </div>
        <div className="table-scroll table-scroll-history">
          <table className="dense-table certificate-history-table">
            <thead>
              <tr>
                <th className="col-gxp">GxP</th>
                <th className="col-line">Dây chuyền</th>
                <th className="col-cert-number">Số GCN</th>
                <th className="col-date">Ngày cấp</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  aria-selected={selectedCertificateId === item.certificate_id}
                  className={selectedCertificateId === item.certificate_id ? "selected" : ""}
                  key={item.certificate_id}
                  onClick={() => onSelectCertificate(item.certificate_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelectCertificate(item.certificate_id);
                    }
                  }}
                  tabIndex={0}
                >
                  <td>{item.certificate_type}</td>
                  <td title={item.line_code ?? "Toàn cơ sở"}>
                    {item.line_code ?? (item.context_match_kind === "site_wide" ? "Toàn cơ sở" : "Cơ sở")}
                  </td>
                  <td title={item.certificate_number ?? ""}>
                    <div className="cell-stack">
                      <strong>{item.certificate_number ?? "Chưa có"}</strong>
                      {item.latest_flag ? <span>Hiện hành</span> : null}
                    </div>
                  </td>
                  <td>{formatCompactDate(item.issue_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel panel-tight certificate-detail-panel">
        {detailError ? (
          <ErrorState message={detailError} />
        ) : detailLoading || !detail ? (
          <EmptyState title="Đang tải chi tiết GxP" description="Đang lấy chi tiết giấy chứng nhận đang chọn." />
        ) : (
          <>
            <div className="detail-grid compact-grid certificate-detail-grid">
              <DetailValue label="Số GCN" value={detail.certificate_number} />
              <DetailValue label="Ngày cấp" value={formatCompactDate(detail.issue_date)} />
              <DetailValue label="Hết hạn" value={formatCompactDate(detail.expiry_date)} />
              <DetailValue label="Tiêu chuẩn" value={detail.applicable_standard} />
              <DetailValue label="Tên cơ sở" value={detail.facility_name} />
              <DetailValue label="Địa chỉ cơ sở" multiline value={detail.address} />
              <DetailValue label="Tên công ty" value={detail.company_name} />
              <DetailValue label="Trụ sở" multiline value={detail.company_legal_address} />
              <DetailValue label="Phạm vi chứng nhận" multiline value={detail.scope_summary} />
              <DetailValue label="Giới hạn" multiline value={detail.limitation_text} />
              <DetailValue label="Cơ quan cấp" value={detail.issuing_authority} />
              <div>
                <span>Tình trạng</span>
                <strong>{detail.status ? <StatusBadge value={detail.status} /> : "Chưa có"}</strong>
              </div>
              <DetailValue label="Nguồn gốc" multiline value={detail.source_description} />
            </div>
          </>
        )}
      </section>
    </div>
  );
}
