import { useRef } from "react";

import { StatusBadge } from "../../components/StatusBadge";
import { CASE_STATE_OPTIONS, formatCompactDate, formatFacilityNameForGrid, formatStatusLabel } from "../../lib/presentation";
import type { FacilitySearchResult } from "../../types";

type HiddenFilters = {
  province: string;
  changeRequestStates: string[];
  certificateState: string;
  certificateExpiringWithinDays: string;
};

function buildHiddenFilterChips(filters: HiddenFilters): string[] {
  const chips: string[] = [];
  if (filters.province.trim()) {
    chips.push(`Tỉnh/thành: ${filters.province.trim()}`);
  }
  if (filters.changeRequestStates.length > 0) {
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

export function FacilityTable({
  rows,
  selectedResultKey,
  loading,
  hasMore,
  showGxpColumn,
  filters,
  hiddenFilters,
  onFilterChange,
  onGxpTypeChange,
  onReachEnd,
  onSelect,
  selectedGxpType,
}: {
  rows: FacilitySearchResult[];
  selectedResultKey: string | null;
  loading: boolean;
  hasMore: boolean;
  showGxpColumn: boolean;
  filters: {
    facilityName: string;
    certificateScope: string;
    caseState: string;
  };
  hiddenFilters: HiddenFilters;
  onFilterChange: (field: "facilityName" | "certificateScope" | "caseState", value: string) => void;
  onGxpTypeChange: (value: "GMP" | "GLP" | "GMPbb") => void;
  onReachEnd: () => void;
  onSelect: (resultKey: string) => void;
  selectedGxpType: string;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const chips = buildHiddenFilterChips(hiddenFilters);

  function maybeLoadMore() {
    if (!hasMore || loading || !scrollRef.current) {
      return;
    }
    const { scrollTop, clientHeight, scrollHeight } = scrollRef.current;
    if (scrollHeight - (scrollTop + clientHeight) <= 120) {
      onReachEnd();
    }
  }

  return (
    <section className="panel panel-tight results-panel">
      <div className="facility-table-layout">
        <nav aria-label="Bộ lọc GxP" className="facility-gxp-rail" role="tablist">
          {(["GMP", "GLP", "GMPbb"] as const).map((option) => (
            <button
              aria-selected={selectedGxpType === option}
              className={selectedGxpType === option ? "facility-gxp-tab active" : "facility-gxp-tab"}
              key={option}
              onClick={() => onGxpTypeChange(option)}
              role="tab"
              type="button"
            >
              {option}
            </button>
          ))}
        </nav>
        <div className="facility-table-frame">
          {loading && rows.length === 0 ? (
            <div className="panel-inline-loading">
              <span className="panel-subtle-loading">Đang tải danh sách cơ sở...</span>
            </div>
          ) : null}
          <div className="table-scroll table-scroll-fill" data-testid="facility-table-scroll" onScroll={maybeLoadMore} ref={scrollRef}>
            <table className="dense-table facility-table">
          {chips.length > 0 ? (
            <caption>
              <div className="active-filter-strip" aria-label="Bộ lọc đang áp dụng">
                {chips.map((chip) => (
                  <span className="filter-chip" key={chip}>{chip}</span>
                ))}
              </div>
            </caption>
          ) : null}
          <thead>
            <tr className="facility-filter-row">
              <th className="col-code"><span className="table-header-label">#</span></th>
              <th className="col-facility">
                <label className="table-header-filter">
                  <span>Tên cơ sở</span>
                  <input
                    aria-label="Tên cơ sở"
                    onChange={(event) => onFilterChange("facilityName", event.target.value)}
                    placeholder="Lọc theo tên..."
                    value={filters.facilityName}
                  />
                </label>
              </th>
              {showGxpColumn ? <th className="col-gxp"><span className="table-header-label">GxP</span></th> : null}
              <th className="col-scope">
                <label className="table-header-filter">
                  <span>Phạm vi chứng nhận</span>
                  <input
                    aria-label="Phạm vi chứng nhận"
                    onChange={(event) => onFilterChange("certificateScope", event.target.value)}
                    placeholder="Lọc theo phạm vi..."
                    value={filters.certificateScope}
                  />
                </label>
              </th>
              <th className="col-province"><span className="table-header-label">Tỉnh/thành</span></th>
              <th className="col-reference"><span className="table-header-label">Ktra gần nhất</span></th>
              <th className="col-status">
                <label className="table-header-filter">
                  <span>Trạng thái hồ sơ gần nhất</span>
                  <select aria-label="Trạng thái hồ sơ" onChange={(event) => onFilterChange("caseState", event.target.value)} value={filters.caseState}>
                    <option value="">Tất cả trạng thái</option>
                    {CASE_STATE_OPTIONS.map((option) => (
                      <option key={option} value={option}>{formatStatusLabel(option)}</option>
                    ))}
                  </select>
                </label>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                aria-selected={selectedResultKey === row.result_key}
                className={selectedResultKey === row.result_key ? "selected" : ""}
                key={row.result_key}
                onClick={() => onSelect(row.result_key)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(row.result_key);
                  }
                }}
                tabIndex={0}
              >
                <td title={row.context_code ?? row.facility_code ?? ""}>{row.context_code ?? row.facility_code ?? "Chưa có"}</td>
                <td title={row.facility_name}>{formatFacilityNameForGrid(row.facility_name)}</td>
                {showGxpColumn ? <td>{row.gxp_type ?? "Chưa có"}</td> : null}
                <td className="multiline-cell" title={row.certificate_scope_summary ?? ""}>
                  {row.certificate_scope_summary ?? "Chưa có"}
                </td>
                <td>{row.province_name ?? "Chưa có"}</td>
                <td title={row.last_inspection_on ?? ""}>{formatCompactDate(row.last_inspection_on)}</td>
                <td>
                  <StatusBadge value={row.current_state} />
                </td>
              </tr>
            ))}
          </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}
