import type { GxpCertificateHistoricalVersion } from "../../types";

// Snapshot comparison is textual evidence only. Version_latest and aggregate
// current are independent server concepts; this component changes neither.
const fields: { label: string; value: (v: GxpCertificateHistoricalVersion) => string | number | boolean | null }[] = [
  { label: "Số GCN", value: v => v.certificate_number },
  { label: "Ngày cấp", value: v => v.issue_date },
  { label: "Ngày hết hạn", value: v => v.expiry_date },
  { label: "Tiêu chuẩn áp dụng", value: v => v.applicable_standard },
  { label: "Cơ quan cấp", value: v => v.issuing_authority },
  { label: "Trạng thái lưu", value: v => v.lifecycle_state },
  { label: "Tóm tắt phạm vi", value: v => v.scope_summary },
];
function readable(value: string | number | boolean | null): string {
  return value === null ? "Chưa có dữ liệu" : String(value);
}
function Scopes({ version }: { version: GxpCertificateHistoricalVersion }) {
  return version.scopes.length ? <ol>
    {[...version.scopes].sort((a, b) => a.sort_order - b.sort_order || a.id.localeCompare(b.id))
      .map(scope => <li key={scope.id}>
        <span>{scope.scope_text}</span>
        <dl className="persisted-version-fields">
          <div><dt>UUID phạm vi</dt><dd>{scope.id}</dd></div>
          <div><dt>Mã phạm vi</dt><dd>{readable(scope.scope_key)}</dd></div>
          <div><dt>Ngôn ngữ</dt><dd>{scope.language_code}</dd></div>
          <div><dt>Thứ tự lưu</dt><dd>{scope.sort_order}</dd></div>
        </dl>
      </li>)}
  </ol> : <p>Không có phạm vi được lưu.</p>;
}

export function GxpVersionComparison({ selected, latest }: {
  selected: GxpCertificateHistoricalVersion;
  latest: GxpCertificateHistoricalVersion;
}) {
  if (selected.certificate_version_id === latest.certificate_version_id) return null;
  const changed = fields.filter(field => field.value(selected) !== field.value(latest));
  return <section aria-label="Đối chiếu phiên bản GxP đã lưu" className="persisted-version-comparison">
    <h4>Đối chiếu snapshot với phiên bản mới nhất đã lưu</h4>
    <p className="workspace-note">Hai phiên bản thuộc cùng Certificate aggregate. “Mới nhất đã lưu” không có nghĩa là Certificate aggregate hiện hành hoặc phiên bản có hiệu lực pháp lý. Các giá trị và phạm vi được hiển thị nguyên theo từng bản ghi; không suy diễn quan hệ tương đương giữa các phạm vi.</p>
    <p>Đang đối chiếu phiên bản {selected.version_no} ({selected.certificate_version_id}) với phiên bản {latest.version_no} ({latest.certificate_version_id}).</p>
    {changed.length ? <div className="table-scroll"><table className="dense-table">
      <caption>Trường có giá trị lưu khác nhau ({changed.length})</caption>
      <thead><tr><th>Trường</th><th>Phiên bản đang xem</th><th>Phiên bản mới nhất đã lưu</th></tr></thead>
      <tbody>{changed.map(field => <tr key={field.label}>
        <th scope="row">{field.label}</th>
        <td>{readable(field.value(selected))}</td>
        <td>{readable(field.value(latest))}</td>
      </tr>)}</tbody>
    </table></div> : <p>Các trường thông tin cơ bản được so sánh có cùng giá trị đã lưu.</p>}
    <div className="persisted-version-scope-comparison">
      <section aria-label="Phạm vi phiên bản đang xem">
        <h5>Phạm vi phiên bản {selected.version_no}</h5>
        <Scopes version={selected} />
      </section>
      <section aria-label="Phạm vi phiên bản mới nhất đã lưu">
        <h5>Phạm vi phiên bản {latest.version_no}</h5>
        <Scopes version={latest} />
      </section>
    </div>
  </section>;
}
