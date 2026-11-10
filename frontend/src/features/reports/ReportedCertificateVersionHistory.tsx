import { useSearchParams } from "react-router-dom";
import type { ApiAccess } from "../../App";
import type { GxpCertificateDetail } from "../../types";
import { PersistedCertificateHistory } from "../search/PersistedCertificateHistory";
import { usePersistedCertificateHistory } from "../search/usePersistedCertificateHistory";

// This rail mounts only after the parent verified canonical Certificate detail.
// Never cross its Site/GxP/Case identity boundary using a separate history GET.
export function ReportedCertificateVersionHistory({ detail, access }: {
  detail: GxpCertificateDetail;
  access: ApiAccess;
}) {
  const [params, setParams] = useSearchParams();
  const selectedValues = params.getAll("version_id");
  const requestedVersionId = selectedValues.length === 1 ? selectedValues[0] : null;
  const invalidVersionHint = selectedValues.length > 1 || (selectedValues.length === 1 && !requestedVersionId?.trim());
  const context = JSON.stringify([
    access.accessGeneration, detail.site_id, detail.certificate_type, detail.case_id,
  ]);
  const history = usePersistedCertificateHistory("gxp", context, detail.certificate_id,
    detail.row_version, access.canLoadSecureApi, access.auth, access.useStubAuth, access.bearerToken);
  if (history.status === "ready" && (
    history.data.certificate_id !== detail.certificate_id
    || history.data.site_id !== detail.site_id
    || history.data.certificate_type !== detail.certificate_type
    || (detail.case_id !== undefined && history.data.case_id !== detail.case_id)
  )) {
    return <p role="alert">Lịch sử phiên bản không khớp Certificate, Site, GxP hoặc Case canonical đang xem.</p>;
  }
  if (invalidVersionHint) return <p role="alert">Tham số phiên bản chứng nhận không hợp lệ.</p>;
  if (history.status === "ready" && requestedVersionId
    && !history.data.versions.some(version => version.certificate_version_id === requestedVersionId)) {
    return <p role="alert">Không tìm thấy UUID phiên bản trong lịch sử Certificate canonical này.</p>;
  }
  const urlHistory = history.status === "ready" ? {
    ...history,
    selectedVersionId: requestedVersionId ?? undefined,
    onSelectVersion: (id: string) => {
      if (!history.data.versions.some(version => version.certificate_version_id === id)) return;
      const next = new URLSearchParams(params);
      next.set("version_id", id);
      setParams(next);
    },
  } : history;
  return <section aria-label="Lịch sử phiên bản GCN chỉ đọc">
    <h3>Lịch sử phiên bản chứng nhận</h3>
    <p className="muted-copy">Chỉ hiển thị snapshot phiên bản đã lưu theo Certificate UUID; không có thao tác sửa, cấp hoặc đặt chứng nhận hiện hành tại đây.</p>
    <PersistedCertificateHistory kind="gxp" state={urlHistory} />
  </section>;
}
