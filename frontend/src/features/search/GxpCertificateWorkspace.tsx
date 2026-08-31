import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { formatCompactDate } from "../../lib/presentation";
import type { GxpCertificateDetail, GxpCertificateListItem } from "../../types";
import { GxpCertificateDetailFields } from "./GxpCertificateDetailFields";

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
    <div className="certificate-workspace-split master-detail-split master-detail-split-certificate">
      <section className="panel panel-tight certificate-list-panel master-list-pane">
        <div className="panel-header">
          <h3>Danh mục GCN GxP</h3>
          <span className="panel-meta">{items.length} giấy</span>
        </div>
        <div className="table-scroll table-scroll-history">
          <table className="dense-table certificate-history-table">
            <colgroup>
              <col className="col-line" />
              <col className="col-cert-number" />
              <col className="col-date" />
            </colgroup>
            <thead>
              <tr>
                <th className="col-line">DC</th>
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

      <section className="panel panel-tight certificate-detail-panel detail-pane">
        {detailError ? (
          <ErrorState message={detailError} />
        ) : detailLoading || !detail ? (
          <EmptyState title="Đang tải chi tiết GxP" description="Đang lấy chi tiết giấy chứng nhận đang chọn." />
        ) : (
          <>
            <GxpCertificateDetailFields detail={detail} />
          </>
        )}
      </section>
    </div>
  );
}
