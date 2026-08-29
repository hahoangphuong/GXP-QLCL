import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { formatCompactDate } from "../../lib/presentation";
import type { BusinessEligibilityDetail, BusinessEligibilityListItem } from "../../types";
import { BusinessEligibilityDetailFields } from "./BusinessEligibilityDetailFields";

export function BusinessEligibilityWorkspace({
  items,
  listLoading,
  listError,
  selectedCertificateId,
  onSelectCertificate,
  detail,
  detailLoading,
  detailError,
}: {
  items: BusinessEligibilityListItem[];
  listLoading: boolean;
  listError: string | null;
  selectedCertificateId: string | null;
  onSelectCertificate: (certificateId: string) => void;
  detail: BusinessEligibilityDetail | null;
  detailLoading: boolean;
  detailError: string | null;
}) {
  if (listError) {
    return <ErrorState message={listError} />;
  }

  if (listLoading && items.length === 0) {
    return <EmptyState title="Đang tải giấy chứng nhận đủ điều kiện" description="Đang đồng bộ danh mục giấy chứng nhận đủ điều kiện của cơ sở đang chọn." />;
  }

  if (!listLoading && items.length === 0) {
    return <EmptyState title="Chưa có giấy chứng nhận đủ điều kiện" description="Cơ sở đang chọn chưa có giấy chứng nhận đủ điều kiện trong dữ liệu hiện có." />;
  }

  return (
    <div className="certificate-workspace-split">
      <section className="panel panel-tight certificate-list-panel">
        <div className="panel-header">
          <h3>Danh mục GCN đủ điều kiện</h3>
          <span className="panel-meta">{items.length} giấy</span>
        </div>
        <div className="table-scroll table-scroll-history">
          <table className="dense-table eligibility-history-table">
            <thead>
              <tr>
                <th className="col-cert-number">Số GCN</th>
                <th className="col-date">Ngày cấp</th>
                <th className="col-sequence">Lần</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  aria-selected={selectedCertificateId === item.business_eligibility_certificate_id}
                  className={selectedCertificateId === item.business_eligibility_certificate_id ? "selected" : ""}
                  key={item.business_eligibility_certificate_id}
                  onClick={() => onSelectCertificate(item.business_eligibility_certificate_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelectCertificate(item.business_eligibility_certificate_id);
                    }
                  }}
                  tabIndex={0}
                >
                  <td title={item.certificate_number ?? ""}>
                    <div className="cell-stack">
                      <strong>{item.certificate_number ?? "Chưa có"}</strong>
                      {item.latest_flag ? <span>Hiện hành</span> : null}
                    </div>
                  </td>
                  <td>{formatCompactDate(item.issued_on)}</td>
                  <td>{item.issuance_sequence_text ? `Lần ${item.issuance_sequence_text}` : "Chưa có"}</td>
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
          <EmptyState title="Đang tải chi tiết ĐĐK" description="Đang lấy chi tiết giấy chứng nhận đủ điều kiện đang chọn." />
        ) : (
          <>
            <BusinessEligibilityDetailFields detail={detail} />
          </>
        )}
      </section>
    </div>
  );
}
