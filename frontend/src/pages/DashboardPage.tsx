import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import type { ApiAccess } from "../App";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { StatusBadge } from "../components/StatusBadge";
import { getDashboardSummary } from "../lib/api";
import type { DashboardSummary } from "../types";

const METRICS = [
  {
    key: "total_facilities",
    label: "Tổng số cơ sở",
    description: "Cơ sở hiện có trong danh mục được phân quyền.",
    to: "/search",
  },
  {
    key: "active_cases",
    label: "Cơ sở có hồ sơ đang xử lý",
    description: "Số cơ sở hiện có ít nhất một hồ sơ chưa đi vào trạng thái kết thúc.",
    to: "/search?case_state=draft&case_state=application_received&case_state=under_assessment&case_state=planned&case_state=decision_issued&case_state=inspection_in_progress&case_state=inspection_completed&case_state=awaiting_certificate_decision",
  },
  {
    key: "waiting_inspection",
    label: "Cơ sở chờ kiểm tra",
    description: "Số cơ sở hiện có hồ sơ ở các trạng thái chuẩn bị hoặc đang kiểm tra.",
    to: "/search?case_state=planned&case_state=decision_issued&case_state=inspection_in_progress",
  },
  {
    key: "waiting_certificate_decision",
    label: "Cơ sở chờ cấp chứng nhận",
    description: "Số cơ sở hiện có hồ sơ đang chờ quyết định chứng nhận.",
    to: "/search?case_state=awaiting_certificate_decision",
  },
  {
    key: "active_certificates",
    label: "Cơ sở có GCN còn hiệu lực",
    description: "Số cơ sở hiện có ít nhất một chứng nhận hiện hành còn hiệu lực.",
    to: "/search?certificate_state=active",
  },
  {
    key: "expiring_certificates_90_days",
    label: "Cơ sở có GCN sắp hết hạn 90 ngày",
    description: "Số cơ sở hiện có ít nhất một chứng nhận hiện hành sẽ hết hạn trong 90 ngày tới.",
    to: "/search?certificate_expiring_within_days=90",
  },
  {
    key: "incomplete_changes",
    label: "Cơ sở có thay đổi chưa hoàn tất",
    description: "Số cơ sở hiện có ít nhất một yêu cầu thay đổi còn đang mở.",
    to: "/search?change_request_state=received&change_request_state=under_review",
  },
] as const;

export function DashboardPage({
  access,
  statusError,
}: {
  access: ApiAccess;
  statusError: string | null;
}) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!access.canLoadSecureApi) {
      setLoading(false);
      setSummary(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void getDashboardSummary(access.auth, access.useStubAuth, access.bearerToken)
      .then((payload) => {
        if (!cancelled) {
          setSummary(payload);
          setError(null);
          setLoading(false);
        }
      })
      .catch((nextError: Error) => {
        if (!cancelled) {
          setError(nextError.message);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [access]);

  if (statusError) {
    return <ErrorState message={statusError} />;
  }
  if (!access.canLoadSecureApi) {
    return (
      <EmptyState
        title="Cần đăng nhập"
        description="Đăng nhập Google Workspace để tải dashboard nghiệp vụ từ API có xác thực."
      />
    );
  }
  if (error) {
    return <ErrorState message={error} />;
  }
  if (loading || !summary) {
    return <EmptyState title="Đang tải dashboard" description="Đang lấy số liệu nghiệp vụ thật từ backend." />;
  }

  return (
    <section className="page-section">
      <header className="section-title">
        <div>
          <p className="eyebrow">Tổng quan</p>
          <h2>Bảng điều phối nghiệp vụ</h2>
        </div>
        <p className="section-copy">
          Dashboard chỉ hiển thị số liệu nghiệp vụ có API thật; trạng thái kỹ thuật được chuyển sang khu vực
          quản trị.
        </p>
      </header>

      <div className="metric-grid">
        {METRICS.map((metric) => (
          <Link className="metric-tile" key={metric.key} to={metric.to}>
            <span>{metric.label}</span>
            <strong>{summary[metric.key]}</strong>
            <small>{metric.description}</small>
          </Link>
        ))}
      </div>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Việc cần xử lý</p>
            <h3>Hồ sơ đang mở</h3>
          </div>
          <Link className="text-link" to="/search">
            Mở Tra cứu
          </Link>
        </div>
        {summary.queue.length === 0 ? (
          <p className="muted-copy">Hiện chưa có hồ sơ đang mở trong dữ liệu được phân quyền.</p>
        ) : (
          <div className="table-scroll">
            <table className="dense-table">
              <thead>
                <tr>
                  <th>Hồ sơ</th>
                  <th>Cơ sở</th>
                  <th>GxP</th>
                  <th>Trạng thái</th>
                  <th>Năm</th>
                </tr>
              </thead>
              <tbody>
                {summary.queue.map((item) => (
                  <tr key={item.case_id}>
                    <td>
                      <Link
                        className="text-link"
                        to={`/search?q=${encodeURIComponent(item.reference_code ?? item.facility_name)}`}
                      >
                        {item.reference_code ?? item.case_id}
                      </Link>
                    </td>
                    <td>
                      <div className="cell-stack">
                        <strong>{item.facility_name}</strong>
                        <span>{item.company_name}</span>
                      </div>
                    </td>
                    <td>{item.gxp_type}</td>
                    <td>
                      <StatusBadge value={item.state} />
                    </td>
                    <td>{item.opened_year ?? "Chưa có"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  );
}
