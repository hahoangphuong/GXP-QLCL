type Filters = {
  query: string;
  gxpType: string;
  province: string;
  caseState: string;
  certificateState: string;
  certificateExpiringWithinDays: string;
};

export function SearchToolbar({
  filters,
  onChange,
  onClear,
}: {
  filters: Filters;
  onChange: (field: keyof Filters, value: string) => void;
  onClear: () => void;
}) {
  return (
    <section className="panel search-toolbar">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Tra cứu</p>
          <h3>Facility master list</h3>
        </div>
        <button className="secondary" onClick={onClear} type="button">
          Xóa lọc
        </button>
      </div>
      <div className="gxp-toggle" role="tablist" aria-label="Bộ lọc GxP">
        {["ALL", "GMP", "GLP", "GMPbd"].map((option) => (
          <button
            className={filters.gxpType === option ? "toggle-chip active" : "toggle-chip"}
            key={option}
            onClick={() => onChange("gxpType", option)}
            type="button"
          >
            {option === "ALL" ? "Tất cả" : option}
          </button>
        ))}
      </div>
      <div className="toolbar-grid">
        <label className="toolbar-search">
          <span>Tìm nhanh</span>
          <input
            value={filters.query}
            onChange={(event) => onChange("query", event.target.value)}
            placeholder="Mã cơ sở, tên cơ sở, công ty, địa chỉ, tỉnh, mã hồ sơ, tiêu chuẩn, số GCN"
          />
        </label>
        <label>
          <span>Tỉnh/thành</span>
          <input value={filters.province} onChange={(event) => onChange("province", event.target.value)} />
        </label>
        <label>
          <span>Trạng thái hồ sơ</span>
          <select value={filters.caseState} onChange={(event) => onChange("caseState", event.target.value)}>
            <option value="">Tất cả</option>
            <option value="application_received">application_received</option>
            <option value="under_assessment">under_assessment</option>
            <option value="planned">planned</option>
            <option value="decision_issued">decision_issued</option>
            <option value="inspection_in_progress">inspection_in_progress</option>
            <option value="inspection_completed">inspection_completed</option>
            <option value="awaiting_certificate_decision">awaiting_certificate_decision</option>
            <option value="certified">certified</option>
          </select>
        </label>
        <label>
          <span>Chứng nhận</span>
          <select value={filters.certificateState} onChange={(event) => onChange("certificateState", event.target.value)}>
            <option value="">Tất cả</option>
            <option value="active">Còn hiệu lực</option>
          </select>
        </label>
        <label>
          <span>Sắp hết hạn</span>
          <select
            value={filters.certificateExpiringWithinDays}
            onChange={(event) => onChange("certificateExpiringWithinDays", event.target.value)}
          >
            <option value="">Không lọc</option>
            <option value="30">30 ngày</option>
            <option value="60">60 ngày</option>
            <option value="90">90 ngày</option>
          </select>
        </label>
      </div>
    </section>
  );
}
