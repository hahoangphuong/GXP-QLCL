import type { BusinessEligibilityHistoricalVersion } from "../../types";

// Compare canonical persisted DDK snapshots; FK records are stored links only,
// never evidence of legal validity or independently verified GxP lineage.
const fields: { label: string; value: (version: BusinessEligibilityHistoricalVersion) => string | number | null }[] = [
  { label: "Số GCN", value: v => v.certificate_number },
  { label: "Ngày cấp", value: v => v.issued_on },
  { label: "Ngày hết hạn", value: v => v.expires_on },
  { label: "Quyết định cấp", value: v => v.decision_reference },
  { label: "Thông tin cấp lần", value: v => v.issuance_sequence_text },
  { label: "Lịch sử cấp/điều chỉnh đã lưu", value: v => v.issuance_history_text },
  { label: "Người chịu trách nhiệm chuyên môn", value: v => v.professional_responsible_person_name },
  { label: "Người đảm bảo chất lượng", value: v => v.quality_assurance_person_name },
  { label: "Trình độ chuyên môn", value: v => v.professional_qualification_text },
  { label: "Số CCHN", value: v => v.professional_license_number },
  { label: "Hoạt động kinh doanh", value: v => v.business_activity_text },
  { label: "Tình trạng GCN đã lưu", value: v => v.current_status_text },
  { label: "Cán bộ xử lý", value: v => v.handled_by_name },
  { label: "Hồ sơ đề nghị", value: v => v.application_dossier_reference },
  { label: "Ghi chú", value: v => v.notes },
];
const format = (v: string | number | null) => v === null ? "Chưa có dữ liệu" : String(v);

function StoredLinks({ version }: { version: BusinessEligibilityHistoricalVersion }) {
  return version.stored_link_records.length ? <ul>
    {version.stored_link_records.map(link => <li key={link.link_id}>
      <dl className="persisted-version-fields">
        <div><dt>UUID liên kết</dt><dd>{link.link_id}</dd></div>
        <div><dt>Certificate UUID</dt><dd>{link.certificate_id}</dd></div>
        <div><dt>Vai trò liên kết đã lưu</dt><dd>{link.link_role}</dd></div>
      </dl>
    </li>)}
  </ul> : <p>Không có bản ghi liên kết FK đã lưu.</p>;
}

export function DdkVersionComparison({ selected, latest }: {
  selected: BusinessEligibilityHistoricalVersion;
  latest: BusinessEligibilityHistoricalVersion;
}) {
  if (selected.business_eligibility_version_id === latest.business_eligibility_version_id) return null;
  const changed = fields.filter(field => field.value(selected) !== field.value(latest));
  return <section aria-label="Đối chiếu phiên bản ĐĐK đã lưu" className="persisted-version-comparison">
    <h4>Đối chiếu snapshot ĐĐK với phiên bản mới nhất đã lưu</h4>
    <p className="workspace-note">Đây là các giá trị và liên kết FK đã lưu, không xác nhận hiệu lực, quyết định phê duyệt hoặc quan hệ nguồn GxP. Phiên bản mới nhất đã lưu không đồng nghĩa với Certificate aggregate hiện hành.</p>
    <p>Phiên bản {selected.version_no} ({selected.business_eligibility_version_id}) so với phiên bản {latest.version_no} ({latest.business_eligibility_version_id}).</p>
    {changed.length ? <div className="table-scroll"><table className="dense-table">
      <caption>Trường ĐĐK có giá trị lưu khác nhau ({changed.length})</caption>
      <thead><tr><th>Trường</th><th>Phiên bản đang xem</th><th>Phiên bản mới nhất đã lưu</th></tr></thead>
      <tbody>{changed.map(field => <tr key={field.label}><th scope="row">{field.label}</th><td>{format(field.value(selected))}</td><td>{format(field.value(latest))}</td></tr>)}</tbody>
    </table></div> : <p>Các trường thông tin cơ bản được so sánh có cùng giá trị đã lưu.</p>}
    <section aria-label="Liên kết FK phiên bản đang xem">
      <h5>Liên kết FK của phiên bản {selected.version_no}</h5>
      <StoredLinks version={selected} />
    </section>
    <section aria-label="Liên kết FK phiên bản mới nhất đã lưu">
      <h5>Liên kết FK của phiên bản {latest.version_no}</h5>
      <StoredLinks version={latest} />
    </section>
  </section>;
}
