import { useEffect, useMemo, useState } from "react";
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
    to: "/workflow?queue=active",
  },
  {
    key: "waiting_inspection",
    label: "Cơ sở chờ kiểm tra",
    description: "Số cơ sở hiện có hồ sơ ở các trạng thái chuẩn bị hoặc đang kiểm tra.",
    to: "/workflow?queue=inspection",
  },
  {
    key: "waiting_certificate_decision",
    label: "Cơ sở chờ cấp chứng nhận",
    description: "Số cơ sở hiện có hồ sơ đang chờ quyết định chứng nhận.",
    to: "/workflow?queue=certificate_decision",
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
    to: "/workflow?queue=expiring",
  },
  {
    key: "incomplete_changes",
    label: "Cơ sở có thay đổi chưa hoàn tất",
    description: "Số cơ sở hiện có ít nhất một yêu cầu thay đổi còn đang mở.",
    to: "/workflow?queue=change_requests",
  },
] as const;

const COUNT_KEYS: (keyof Omit<DashboardSummary, "queue">)[] = [
  "total_facilities", "total_cases", "active_cases", "waiting_inspection",
  "waiting_certificate_decision", "active_certificates",
  "expiring_certificates_90_days", "incomplete_changes",
];

// The Dashboard API is an aggregate of distinct Site counts plus a bounded
// Case queue. Validate its read contract before exposing any Site/Case links.
// Multiple queue Cases may legitimately share a Site or result_key.
function validateDashboardSummary(summary: DashboardSummary): DashboardSummary {
  if (!summary || COUNT_KEYS.some(key => !Number.isSafeInteger(summary[key]) || summary[key] < 0)
    || !Array.isArray(summary.queue)
    || summary.queue.length > summary.total_cases
    || COUNT_KEYS.some(key => key !== "total_cases" && key !== "total_facilities"
      && summary[key] > summary.total_facilities)) {
    throw new Error("API trả về thống kê Dashboard không nhất quán.");
  }
  const ids = new Set<string>();
  for (const item of summary.queue) {
    if (!item || typeof item.case_id !== "string" || !item.case_id.trim()
      || typeof item.site_id !== "string" || !item.site_id.trim()
      || typeof item.state !== "string" || !item.state.trim()
      || typeof item.gxp_type !== "string" || !item.gxp_type.trim()
      || ids.has(item.case_id)) {
      throw new Error("Hàng đợi Dashboard thiếu hoặc trùng định danh hồ sơ.");
    }
    ids.add(item.case_id);
  }
  return summary;
}

export function DashboardPage({
  access,
  statusError,
}: {
  access: ApiAccess;
  statusError: string | null;
}) {
  const { auth, bearerToken, canLoadSecureApi, useStubAuth, accessGeneration } = access;
  const owner = useMemo(() => ({}), [accessGeneration, auth, bearerToken, canLoadSecureApi, useStubAuth]);
  const [result, setResult] = useState<{ owner: object; summary: DashboardSummary | null; error: string | null } | null>(null);
  const current = canLoadSecureApi && result?.owner === owner ? result : null;
  const summary = current?.summary ?? null;
  const error = current?.error ?? null;
  const loading = current === null;

  useEffect(() => {
    if (!canLoadSecureApi) {
      setResult(null);
      return;
    }
    let cancelled = false;
    void getDashboardSummary(auth, useStubAuth, bearerToken)
      .then((payload) => {
        if (cancelled) return;
        try {
          setResult({ owner, summary: validateDashboardSummary(payload), error: null });
        } catch (error) {
          setResult({ owner, summary: null, error: error instanceof Error ? error.message : "Dashboard không hợp lệ." });
        }
      })
      .catch((nextError: Error) => {
        if (!cancelled) setResult({ owner, summary: null, error: nextError.message });
      });
    return () => { cancelled = true; };
  }, [auth, bearerToken, canLoadSecureApi, owner, useStubAuth]);

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

  function queueCaseTarget(item: DashboardSummary["queue"][number]) {
    // Canonical CaseDirectOpen checks the UUID and resolves current Site/GxP/line.
    return `/cases/${encodeURIComponent(item.case_id)}`;
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
          quản trị. Thẻ thống kê đếm cơ sở, còn Bàn công việc liệt kê từng hồ sơ hoặc chứng nhận nên số dòng có thể khác.
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
          <Link className="text-link" to="/workflow">
            Mở Bàn công việc
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
                  <th>Tài liệu</th>
                </tr>
              </thead>
              <tbody>
                {summary.queue.map((item) => (
                  <tr key={item.case_id}>
                    <td>
                      <Link
                        className="text-link"
                        to={queueCaseTarget(item)}
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
                    <td><Link className="text-link" to={`/documents/cases/${encodeURIComponent(item.case_id)}`}>Xem tài liệu</Link></td>
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
