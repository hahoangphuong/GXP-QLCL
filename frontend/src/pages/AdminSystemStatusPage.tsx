import { useEffect, useMemo, useState } from "react";

import type { ApiAccess } from "../App";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { getAdminSystemStatus } from "../lib/api";
import type { AppStatus } from "../types";

export function AdminSystemStatusPage({ access }: { access: ApiAccess }) {
  const { auth, bearerToken, canLoadSecureApi, useStubAuth, accessGeneration } = access;
  const owner = useMemo(() => ({}), [accessGeneration, auth, bearerToken, canLoadSecureApi, useStubAuth]);
  const [result, setResult] = useState<{ owner: object; status: AppStatus | null; error: string | null } | null>(null);
  const current = canLoadSecureApi && result?.owner === owner ? result : null;
  const status = current?.status ?? null;
  const error = current?.error ?? null;

  useEffect(() => {
    if (!canLoadSecureApi) {
      setResult(null);
      return;
    }
    let cancelled = false;
    void getAdminSystemStatus(auth, useStubAuth, bearerToken)
      .then((payload) => {
        if (!cancelled) setResult({ owner, status: payload, error: null });
      })
      .catch((nextError: Error) => {
        if (!cancelled) setResult({ owner, status: null, error: nextError.message });
      });
    return () => { cancelled = true; };
  }, [auth, bearerToken, canLoadSecureApi, owner, useStubAuth]);

  if (!canLoadSecureApi) {
    return <EmptyState title="Cần đăng nhập" description="Đăng nhập để xem trạng thái hệ thống được phân quyền." />;
  }
  if (error) {
    return <ErrorState message={error} />;
  }
  if (!status) {
    return <EmptyState title="Đang tải trạng thái hệ thống" description="Đang kiểm tra runtime đang hoạt động." />;
  }

  return (
    <section className="page-section">
      <header className="section-title">
        <div>
          <p className="eyebrow">Quản trị</p>
          <h2>Trạng thái hệ thống</h2>
        </div>
        <p className="section-copy">Thông tin runtime chỉ đọc, được backend kiểm soát bằng quyền quản trị.</p>
      </header>
      <section className="panel detail-panel">
        <dl className="detail-grid">
          <div className="detail-field"><dt className="detail-label">Triển khai</dt><dd className="detail-value-slot"><strong>{status.deployment.git_short_sha ?? "Chưa có metadata"}</strong></dd></div>
          <div className="detail-field"><dt className="detail-label">Nhánh</dt><dd className="detail-value-slot"><strong>{status.deployment.branch ?? "Chưa có metadata"}</strong></dd></div>
          <div className="detail-field"><dt className="detail-label">Nền tảng</dt><dd className="detail-value-slot"><strong>{status.deployment_platform}</strong></dd></div>
          <div className="detail-field"><dt className="detail-label">Topology frontend</dt><dd className="detail-value-slot"><strong>{status.frontend_topology}</strong></dd></div>
          <div className="detail-field"><dt className="detail-label">Xác thực</dt><dd className="detail-value-slot"><strong>{status.auth_mode}</strong></dd></div>
          <div className="detail-field"><dt className="detail-label">Database runtime</dt><dd className="detail-value-slot"><strong>{status.deployment.db_name ?? "Chưa xác định"}</strong></dd></div>
        </dl>
      </section>
    </section>
  );
}
