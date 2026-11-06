import { useId } from "react";
import type { EligibilitySourceState } from "./useBusinessEligibilitySourceEvidence";

const order = ["GMP", "GLP", "GSP", "GDP"] as const;
/** Excel A1 notation is derived only from recorded 1-based row and column indices. */
function excelCellAddress(column: number, row: number | null): string | null {
  if (!Number.isSafeInteger(column) || column < 1 || column > 16384
    || row === null || !Number.isSafeInteger(row) || row < 1 || row > 1048576) return null;
  let remaining = column;
  let letters = "";
  while (remaining > 0) {
    remaining -= 1;
    letters = String.fromCharCode(65 + remaining % 26) + letters;
    remaining = Math.floor(remaining / 26);
  }
  return `${letters}${row}`;
}

function ExcelCellLocator({ column, row }: { column: number; row: number | null }) {
  const cell = excelCellAddress(column, row);
  return <span>{cell ? `${cell} (cột ${column})` : `Không xác định địa chỉ ô (cột ghi nhận: ${column})`}</span>;
}


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
      <details className="ddk-source-provenance">
        <summary>Vị trí và dấu vân tay dữ liệu nguồn Excel</summary>
        <p className="workspace-note">Thông tin xuất xứ được backend ghi nhận; chưa tự đối chiếu tệp workbook hoặc xác minh chữ ký.</p>
        <dl className="persisted-version-fields">
          <div><dt>ID ĐĐK legacy</dt><dd>{state.data.legacy_dkkd_id ?? "Chưa có dữ liệu"}</dd></div>
          <div><dt>Sheet nguồn</dt><dd>{state.data.source_sheet_name ?? "Chưa có dữ liệu"}</dd></div>
          <div><dt>Hàng Excel</dt><dd>{state.data.source_row_number ?? "Chưa có dữ liệu"}</dd></div>
          <div><dt>SHA-256 workbook ghi nhận</dt><dd>{state.data.source_workbook_sha256 ?? "Chưa có dữ liệu"}</dd></div>
        </dl>
      </details>
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
          <details className="ddk-source-cell-provenance">
            <summary>Vị trí ô và dấu vân tay nhóm {name}</summary>
            <p className="workspace-note">Địa chỉ ô A1 được suy ra từ số hàng và cột do backend ghi nhận; chưa kiểm tra workbook, không chứng minh liên kết GxP. SHA-256 là metadata nguồn đã ghi nhận.</p>
            <dl className="persisted-version-fields">
              <div><dt>Ô ID CC gốc (A1)</dt><dd><ExcelCellLocator column={group.id_cc_excel_column} row={state.data.source_row_number} /></dd></div>
              <div><dt>Ô phạm vi chứng nhận (A1)</dt><dd><ExcelCellLocator column={group.certificate_scope_excel_column} row={state.data.source_row_number} /></dd></div>
              <div><dt>Ô tiêu chuẩn áp dụng (A1)</dt><dd><ExcelCellLocator column={group.applicable_standard_excel_column} row={state.data.source_row_number} /></dd></div>
              <div><dt>Ô hoạt động kinh doanh (A1)</dt><dd><ExcelCellLocator column={group.business_activity_excel_column} row={state.data.source_row_number} /></dd></div>
              <div><dt>SHA-256 dữ liệu nhóm ghi nhận</dt><dd>{group.source_values_sha256}</dd></div>
            </dl>
          </details>
          {group.reference_tokens.length ? <div className="ddk-source-tokens">
            <span>Token ID CC gốc</span>
            <ol>{group.reference_tokens.map(token => <li key={token.source_reference_id} value={token.token_index}>{token.raw_token}</li>)}</ol>
          </div> : <p className="workspace-note">Không có token ID CC trong ô nguồn.</p>}
        </details>;
      })}
    </> : null}
  </section>;
}
