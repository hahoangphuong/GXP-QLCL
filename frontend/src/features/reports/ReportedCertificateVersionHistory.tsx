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
  const context = JSON.stringify([
    access.accessGeneration, detail.site_id, detail.certificate_type, detail.case_id,
  ]);
  const history = usePersistedCertificateHistory("gxp", context, detail.certificate_id,
    detail.row_version, access.canLoadSecureApi, access.auth, access.useStubAuth, access.bearerToken);
  if (history.status === "ready" && (
    history.data.certificate_id !== detail.certificate_id
    || history.data.site_id !== detail.site_id
    || history.data.certificate_type !== detail.certificate_type
    || (detail.case_id !== null && history.data.case_id !== detail.case_id)
  )) {
    return <p role="alert">Lịch sử phiên bản không khớp Certificate, Site, GxP hoặc Case canonical đang xem.</p>;
  }
  return <section aria-label="Lịch sử phiên bản GCN chỉ đọc">
    <h3>Lịch sử phiên bản chứng nhận</h3>
    <p className="muted-copy">Chỉ hiển thị snapshot phiên bản đã lưu theo Certificate UUID; không có thao tác sửa, cấp hoặc đặt chứng nhận hiện hành tại đây.</p>
    <PersistedCertificateHistory kind="gxp" state={history} />
  </section>;
}
