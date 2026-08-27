import { useState } from "react";

import { CASE_STATE_OPTIONS, formatStatusLabel } from "../../lib/presentation";

type Filters = {
  query: string;
  gxpType: string;
  province: string;
  caseState: string;
  certificateState: string;
  certificateExpiringWithinDays: string;
  changeRequestStates: string[];
};

function buildFilterChips(filters: Filters): string[] {
  const chips: string[] = [];
  if (filters.province.trim()) {
    chips.push(`Tỉnh/thành: ${filters.province.trim()}`);
  }
  if (filters.caseState) {
    chips.push(`Trạng thái hồ sơ: ${formatStatusLabel(filters.caseState)}`);
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
}: {
  filters: Filters;
  onChange: (field: keyof Filters, value: string) => void;
  onClear: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const chips = buildFilterChips(filters);

  return (
    <section className="panel panel-tight search-toolbar">
      <div className="toolbar-primary toolbar-primary-compact">
        <div className="toolbar-heading">
          <span className="toolbar-label">Tra cứu</span>
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
        <button className="secondary" onClick={onClear} type="button">
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
            <select value={filters.caseState} onChange={(event) => onChange("caseState", event.target.value)}>
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
