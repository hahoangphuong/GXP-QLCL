import { useId, useState } from "react";
import type { BusinessEligibilityHistoricalVersion, BusinessEligibilityVersionHistory, GxpCertificateHistoricalVersion, GxpCertificateVersionHistory } from "../../types";
import type { HistoryState } from "./usePersistedCertificateHistory";

type Props = { kind: "gxp"; state: HistoryState<GxpCertificateVersionHistory> } | { kind: "ddk"; state: HistoryState<BusinessEligibilityVersionHistory> };
function Field({ label, value }: { label: string; value: string | number | boolean | null }) {
  return <div><dt>{label}</dt><dd>{value === null ? "Chưa có dữ liệu" : typeof value === "boolean" ? String(value) : value}</dd></div>;
}
function GxpSnapshot({ version }: { version: GxpCertificateHistoricalVersion }) {
  return <>
    <dl className="persisted-version-fields">
      <Field label="UUID phiên bản" value={version.certificate_version_id} />
      <Field label="Cờ phiên bản mới nhất (is_latest_version)" value={version.is_latest_version} />
      <Field label="Ngày cấp" value={version.issue_date} /><Field label="Hết hạn" value={version.expiry_date} />
      <Field label="Tiêu chuẩn" value={version.applicable_standard} /><Field label="Cơ quan cấp" value={version.issuing_authority} />
      <Field label="Trạng thái bản ghi" value={version.lifecycle_state ?? "Chưa có trạng thái được xác nhận trong bản ghi"} />
      <Field label="Tóm tắt phạm vi" value={version.scope_summary} />
    </dl>
    <h4>Phạm vi của phiên bản</h4>
    {version.scopes.length ? <ol>{version.scopes.map(scope => <li key={scope.id}>
      <p className="persisted-version-text">{scope.scope_text}</p>
      <dl className="persisted-version-fields"><Field label="UUID phạm vi" value={scope.id} /><Field label="Mã phạm vi" value={scope.scope_key} />
        <Field label="Ngôn ngữ" value={scope.language_code} /><Field label="Thứ tự" value={scope.sort_order} /></dl>
    </li>)}</ol> : <p>Phiên bản chưa có bản ghi phạm vi.</p>}
  </>;
}
const ddkFields: [keyof Omit<BusinessEligibilityHistoricalVersion, "stored_link_records">, string][] = [
  ["business_eligibility_version_id", "UUID phiên bản"], ["issued_on", "Ngày cấp"], ["expires_on", "Hết hạn"],
  ["decision_reference", "QĐ cấp"], ["issuance_sequence_text", "Cấp lần"], ["issuance_history_text", "Thông tin cấp/điều chỉnh đã lưu"],
  ["professional_responsible_person_name", "PT chuyên môn"], ["quality_assurance_person_name", "ĐBCL"],
  ["professional_qualification_text", "Trình độ chuyên môn"], ["professional_license_number", "CCHN"],
  ["professional_license_issued_on", "Ngày cấp CCHN"], ["professional_license_issuer", "Nơi cấp CCHN"],
  ["responsible_license_issued_on", "Ngày cấp giấy phép phụ trách"], ["responsible_license_issuer", "Nơi cấp giấy phép phụ trách"],
  ["business_activity_text", "Hoạt động kinh doanh"], ["current_status_text", "Tình trạng giấy"],
  ["handled_by_name", "Người xử lý"], ["application_dossier_reference", "HS đề nghị"], ["notes", "Ghi chú"],
];
function DdkSnapshot({ version }: { version: BusinessEligibilityHistoricalVersion }) {
  return <><dl className="persisted-version-fields">{ddkFields.map(([key, label]) => <Field key={key} label={label} value={version[key]} />)}</dl>
    <h4>Các bản ghi liên kết FK của phiên bản</h4>
    <p>Chỉ là FK đã lưu; chưa xác nhận hiệu lực hoặc phê duyệt lịch sử. Không bao gồm token GxP nguồn Excel.</p>
    {version.stored_link_records.length ? <ul>{version.stored_link_records.map(link => <li key={link.link_id}><dl className="persisted-version-fields">
      <Field label="UUID liên kết" value={link.link_id} /><Field label="UUID Certificate" value={link.certificate_id} /><Field label="Vai trò" value={link.link_role} />
    </dl></li>)}</ul> : <p>Không có bản ghi liên kết canonical được lưu cho phiên bản.</p>}
  </>;
}
export function PersistedCertificateHistory({ kind, state }: Props) {
  const labelId = useId();
  const [selection, setSelection] = useState<{ data: object; id: string } | null>(null);
  const data = state.status === "ready" ? state.data : null;
  const versions = data?.versions ?? [];
  const idOf = (v: GxpCertificateHistoricalVersion | BusinessEligibilityHistoricalVersion) => "certificate_version_id" in v ? v.certificate_version_id : v.business_eligibility_version_id;
  const selectedId = state.status === "ready" && state.onSelectVersion ? state.selectedVersionId : selection?.data === data ? selection.id : undefined;
  const selected = versions.find(v => idOf(v) === selectedId) ?? versions[0];
  const error = state.status === "error" ? state.httpStatus : null;
  const errorMessage = state.status !== "error" ? null : error === 401 ? "Cần đăng nhập để xem phiên bản." : error === 403 ? "Không có quyền xem phiên bản." : error === 404 ? "Không tìm thấy giấy chứng nhận theo UUID." : error === 409 ? "Xung đột toàn vẹn dữ liệu phiên bản; cần kiểm tra dữ liệu." : "Không thể tải phiên bản đã lưu.";
  const stateAnnouncement = state.status === "idle" || state.status === "loading" ? "Đang tải phiên bản đã lưu…"
    : errorMessage ?? (data && !selected ? "Giấy chứng nhận chưa có phiên bản được lưu." : null);
  return <>
    {stateAnnouncement ? <p className="sr-only" role={errorMessage ? "alert" : "status"}>{stateAnnouncement}</p> : null}
    <details className="persisted-certificate-history">
    <summary>{kind === "gxp" ? "Các phiên bản GPs đã lưu" : "Các phiên bản ĐĐK đã lưu"}</summary>
    <section aria-labelledby={labelId}>
      <h3 id={labelId}>Snapshot phiên bản — chỉ đọc</h3>
      {state.status === "idle" || state.status === "loading" ? <p>Đang tải phiên bản đã lưu…</p> : null}
      {errorMessage ? <p>{errorMessage}</p> : null}
      {data ? <>
        <p>{versions.length} phiên bản đã lưu</p>
        <dl className="persisted-version-fields">
          <Field label="UUID Certificate aggregate" value={"certificate_id" in data ? data.certificate_id : data.business_eligibility_certificate_id} />
          <Field label="Cờ aggregate hiện hành (aggregate_latest_flag)" value={data.aggregate_latest_flag} />
          <Field label="UUID phiên bản mới nhất đã lưu" value={data.latest_version_id} />
          {"latest_selection_method" in data ? <Field label="Cách chọn phiên bản mới nhất" value={data.latest_selection_method} /> : null}
        </dl>
        {!selected ? <p>Giấy chứng nhận chưa có phiên bản được lưu.</p> : <>
          <label>Phiên bản đã lưu<select value={idOf(selected)} onChange={event => { if (state.status === "ready" && state.onSelectVersion) state.onSelectVersion(event.target.value); else setSelection({ data, id: event.target.value }); }}>
            {versions.map(v => <option key={idOf(v)} value={idOf(v)}>Phiên bản {v.version_no} · {v.certificate_number ?? "Chưa có số"} · {idOf(v)}</option>)}
          </select></label>
          <p aria-atomic="true" aria-live="polite" className="sr-only" role="status">
            Đang hiển thị phiên bản {selected.version_no} của {versions.length} phiên bản đã lưu.
          </p>
          <dl className="persisted-version-fields"><Field label="Số thứ tự phiên bản (version_no)" value={selected.version_no} /><Field label="Concurrency token (row_version)" value={selected.row_version} /><Field label="Số GCN" value={selected.certificate_number} /></dl>
          {"certificate_version_id" in selected ? <GxpSnapshot version={selected} /> : <DdkSnapshot version={selected} />}
        </>}
      </> : null}
    </section>
  </details>
  </>;
}
