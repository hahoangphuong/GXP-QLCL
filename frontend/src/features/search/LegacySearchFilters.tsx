import { CASE_STATE_OPTIONS, formatStatusLabel } from "../../lib/presentation";

type Filters = {
  generalQuery: string;
  province: string;
  caseState: string;
  certificateState: string;
  certificateExpiringWithinDays: string;
};

// MainForm.edSearch / FilterForm groups; expose only existing server filters.
export function LegacySearchFilters({ filters, onChange, multipleCaseStates = false }: {
  filters: Filters;
  multipleCaseStates?: boolean;
  onChange: (field: keyof Filters, value: string) => void;
}) {
  return <div className="legacy-search-filters">
    <label className="legacy-quick-filter"><span>Lọc:</span><input aria-label="Tìm nhanh" value={filters.generalQuery} onChange={event => onChange("generalQuery", event.target.value)} /></label>
    <details className="legacy-filter-form">
      <summary>Lọc dữ liệu</summary>
      <div className="legacy-filter-groups">
        <fieldset><legend>Cơ sở</legend><label><span>Tỉnh/thành</span><input value={filters.province} onChange={event => onChange("province", event.target.value)} /></label></fieldset>
        <fieldset><legend>Hồ sơ kiểm tra</legend><label><span>Trạng thái hồ sơ</span><select value={multipleCaseStates ? "__multiple__" : filters.caseState} onChange={event => onChange("caseState", event.target.value)}><option value="">Tất cả</option>{multipleCaseStates ? <option value="__multiple__" disabled>Nhiều trạng thái</option> : null}{CASE_STATE_OPTIONS.map(state => <option key={state} value={state}>{formatStatusLabel(state)}</option>)}</select></label></fieldset>
        <fieldset><legend>Chứng chỉ</legend>
          <label><span>Hiệu lực</span><select value={filters.certificateState} onChange={event => onChange("certificateState", event.target.value)}><option value="">Không lọc</option><option value="active">Còn hiệu lực</option></select></label>
          <label><span>Sắp hết hạn</span><select value={filters.certificateExpiringWithinDays} onChange={event => onChange("certificateExpiringWithinDays", event.target.value)}><option value="">Không lọc</option>{filters.certificateExpiringWithinDays && !["30", "60", "90"].includes(filters.certificateExpiringWithinDays) ? <option value={filters.certificateExpiringWithinDays}>{filters.certificateExpiringWithinDays} ngày</option> : null}{[30, 60, 90].map(days => <option key={days} value={days}>{days} ngày</option>)}</select></label>
        </fieldset>
      </div>
    </details>
  </div>;
}
