import { useId } from "react";
import type { EligibilitySourceState } from "./useBusinessEligibilitySourceEvidence";

const order = ["GMP", "GLP", "GSP", "GDP"] as const;

function failure(status: number | null): string {
  if (status === 401) return "Cần đăng nhập để xem dữ liệu nguồn ĐĐK.";
  if (status === 403) return "Bạn không có quyền xem dữ liệu nguồn ĐĐK.";
  if (status === 409) return "Dữ liệu nguồn ĐĐK vật lý không nhất quán. Cần kiểm tra nguồn; không tự tải lại.";
  if (status === 404) return "Không tìm thấy bản ghi ĐĐK cho yêu cầu dữ liệu nguồn.";
  return "Không thể tải dữ liệu nguồn ĐĐK. Kiểm tra kết nối hoặc dịch vụ backend.";
}

export function BusinessEligibilitySourceEvidence({ state }: { state: EligibilitySourceState }) {
  const titleId = useId();
  return <section aria-labelledby={titleId} className="ddk-source-evidence" aria-busy={state.status === "loading"}>
    <h4 id={titleId}>Dữ liệu GxP từ hồ sơ ĐĐK gốc</h4>
    <p className="workspace-note">Dữ liệu đối chiếu Excel, chưa phải liên kết GxP được xác nhận.</p>
    {state.status === "idle" ? <p role="status">Chọn giấy ĐĐK để xem dữ liệu nguồn.</p> : null}
    {state.status === "loading" ? <p role="status">Đang tải dữ liệu nguồn ĐĐK…</p> : null}
    {state.status === "error" ? <p role="alert">{failure(state.httpStatus)}</p> : null}
    {state.status === "ready" && state.data.source_status === "legacy_identity_missing"
      ? <p role="status">Bản ghi ĐĐK chưa có định danh legacy để đối chiếu nguồn Excel.</p> : null}
    {state.status === "ready" && state.data.source_status === "not_in_imported_source"
      ? <p role="status">Bản ghi ĐĐK không nằm trong nguồn Excel đã import.</p> : null}
    {state.status === "ready" && state.data.source_status === "available" ? <>
      {order.map(name => {
        const group = state.data.groups.find(item => item.source_group === name);
        if (!group) return null; // No invented source group or values.
        return <details className="ddk-source-group" key={group.source_group_id} open>
          <summary>{name}</summary>
          <dl>
            {([
              ["ID CC gốc", group.id_cc_raw],
              ["Phạm vi chứng nhận", group.certificate_scope_raw],
              ["Tiêu chuẩn áp dụng", group.applicable_standard_raw],
              ["Hoạt động kinh doanh", group.business_activity_raw],
            ] as const).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>
              {value === "" ? <span className="source-empty">Ô nguồn trống</span> : value}
            </dd></div>)}
          </dl>
          {group.reference_tokens.length ? <div className="ddk-source-tokens">
            <span>Token ID CC gốc</span>
            <ol>{group.reference_tokens.map(token => <li key={token.source_reference_id} value={token.token_index}>{token.raw_token}</li>)}</ol>
          </div> : <p className="workspace-note">Không có token ID CC trong ô nguồn.</p>}
        </details>;
      })}
    </> : null}
  </section>;
}
