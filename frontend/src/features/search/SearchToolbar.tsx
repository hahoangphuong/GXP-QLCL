import { useState } from "react";

import { CASE_STATE_OPTIONS, formatStatusLabel } from "../../lib/presentation";

type Filters = {
  query: string;
  province: string;
  caseStates: string[];
  certificateState: string;
  certificateExpiringWithinDays: string;
  changeRequestStates: string[];
};

type FilterChange = Exclude<keyof Filters, "caseStates"> | "caseState";

function buildFilterChips(filters: Filters): string[] {
  const chips: string[] = [];
  if (filters.province.trim()) {
    chips.push(`Tỉnh/thành: ${filters.province.trim()}`);
  }
  if (filters.caseStates.length > 0) {
    chips.push(`Trạng thái hồ sơ: ${filters.caseStates.map((item) => formatStatusLabel(item)).join(", ")}`);
  } else if (filters.changeRequestStates.length > 0) {
    chips.push(`Thay đổi: ${filters.changeRequestStates.map((item) => formatStatusLabel(item)).join(", ")}`);
  }
  if (filters.certificateState === "active") {
    chips.push("Chứng nhận: Còn hiệu lực");
  }
  if (filters.certificateExpiringWithinDays) {
    chips.push(`Sắp hết hạn: ${filters.certificateExpiringWithinDays} ngày`);
  }
  return chips;
}

export function SearchToolbar({
  filters,
  onChange,
  onClear,
  gxpType,
  loadedCount,
  totalCount,
  hasMasterFilters = false,
}: {
  filters: Filters;
  onChange: (field: FilterChange, value: string) => void;
  onClear: () => void;
  gxpType: string;
  loadedCount: number;
  totalCount: number;
  hasMasterFilters?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const chips = buildFilterChips(filters);
  const hasMultipleCaseStates = filters.caseStates.length > 1;

  return (
    <section className="panel panel-tight search-toolbar">
      <div className="toolbar-primary toolbar-primary-compact">
        <div className="toolbar-heading">
          <span className="toolbar-label">Tra cứu</span>
          <span className="toolbar-meta" aria-live="polite">
            {loadedCount < totalCount ? `Đã tải ${loadedCount} / ${totalCount}` : `${totalCount} kết quả`}
          </span>
        </div>
        <span className="toolbar-gxp-context" aria-label={`Nhóm GxP đang chọn: ${gxpType}`}>
          GMP / GLP / GMPbb · {gxpType}
        </span>
        <label className="toolbar-search toolbar-search-primary">
          <span className="sr-only">Tìm nhanh</span>
          <input
            value={filters.query}
            onChange={(event) => onChange("query", event.target.value)}
            placeholder="Tìm mã cơ sở, dây chuyền, cơ sở, công ty, hồ sơ, số GCN"
          />
        </label>
        <button className="secondary" onClick={() => setExpanded((current) => !current)} type="button">
          {expanded ? "Ẩn lọc" : "Bộ lọc"}
        </button>
        <button className="secondary" disabled={!hasMasterFilters && !filters.query && chips.length === 0} onClick={onClear} type="button">
          Xóa lọc
        </button>
      </div>

      {chips.length > 0 ? (
        <div className="active-filter-strip" aria-label="Bộ lọc đang áp dụng">
          {chips.map((chip) => (
            <span className="filter-chip" key={chip}>
              {chip}
            </span>
          ))}
        </div>
      ) : null}

      {expanded ? (
        <div className="toolbar-grid">
          <label>
            <span>Tỉnh/thành</span>
            <input value={filters.province} onChange={(event) => onChange("province", event.target.value)} />
          </label>
          <label>
            <span>Trạng thái hồ sơ</span>
            <select value={filters.caseStates.length === 1 ? filters.caseStates[0] : ""} onChange={(event) => onChange("caseState", event.target.value)}>
              {hasMultipleCaseStates ? <option disabled value="">Nhiều trạng thái (giữ theo liên kết)</option> : null}
              <option value="">Tất cả</option>
              {CASE_STATE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {formatStatusLabel(option)}
                </option>
              ))}
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
      ) : null}
    </section>
  );
}
