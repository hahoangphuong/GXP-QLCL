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
  totalCount,
  loading,
  hasMore,
  showGxpColumn,
  filters,
  hiddenFilters,
  onFilterChange,
  onClear,
  onReachEnd,
  onSelect,
}: {
  rows: FacilitySearchResult[];
  selectedResultKey: string | null;
  totalCount: number;
  loading: boolean;
  hasMore: boolean;
  showGxpColumn: boolean;
  filters: {
    facilityName: string;
    certificateScope: string;
    caseState: string;
    gxpType: string;
  };
  hiddenFilters: HiddenFilters;
  onFilterChange: (field: "facilityName" | "certificateScope" | "caseState" | "gxpType", value: string) => void;
  onClear: () => void;
  onReachEnd: () => void;
  onSelect: (resultKey: string) => void;
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
      <div className="results-toolbar">
        <div className="panel-header results-toolbar-head">
          <div className="panel-heading-inline panel-heading-inline-wrap">
            <h3>Cơ sở/dây chuyền</h3>
            <div className="gxp-toggle" role="tablist" aria-label="Bộ lọc GxP">
              {["ALL", "GMP", "GLP", "GMPbb"].map((option) => (
                <button
                  aria-selected={filters.gxpType === option}
                  className={filters.gxpType === option ? "toggle-chip active" : "toggle-chip"}
                  key={option}
                  onClick={() => onFilterChange("gxpType", option)}
                  type="button"
                >
                  {option === "ALL" ? "Tất cả" : option}
                </button>
              ))}
            </div>
          </div>
          <div className="panel-actions panel-actions-tight">
            <span className="panel-meta">{rows.length >= totalCount ? `${totalCount} dòng` : `Đã tải ${rows.length} / ${totalCount}`}</span>
            {loading && rows.length > 0 ? <span className="panel-subtle-loading">Đang tải...</span> : null}
            <button className="secondary" onClick={onClear} type="button">
              Xóa lọc
            </button>
          </div>
        </div>
        <div className="inline-filter-row" aria-label="Bộ lọc tra cứu trực tiếp">
          <label className="inline-filter-field">
            <span className="sr-only">Tên cơ sở</span>
            <input
              aria-label="Tên cơ sở"
              onChange={(event) => onFilterChange("facilityName", event.target.value)}
              placeholder="Tên cơ sở"
              value={filters.facilityName}
            />
          </label>
          <label className="inline-filter-field">
            <span className="sr-only">Phạm vi chứng nhận</span>
            <input
              aria-label="Phạm vi chứng nhận"
              onChange={(event) => onFilterChange("certificateScope", event.target.value)}
              placeholder="Phạm vi chứng nhận"
              value={filters.certificateScope}
            />
          </label>
          <label className="inline-filter-field inline-filter-select">
            <span className="sr-only">Trạng thái hồ sơ</span>
            <select aria-label="Trạng thái hồ sơ" onChange={(event) => onFilterChange("caseState", event.target.value)} value={filters.caseState}>
              <option value="">Trạng thái hồ sơ</option>
              {CASE_STATE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {formatStatusLabel(option)}
                </option>
              ))}
            </select>
          </label>
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
      </div>
      {loading && rows.length === 0 ? (
        <div className="panel-inline-loading">
          <span className="panel-subtle-loading">Đang tải danh sách cơ sở...</span>
        </div>
      ) : null}
      <div className="table-scroll table-scroll-fill" data-testid="facility-table-scroll" onScroll={maybeLoadMore} ref={scrollRef}>
        <table className="dense-table facility-table">
          <thead>
            <tr>
              <th className="col-code">#</th>
              <th className="col-facility">Tên cơ sở</th>
              {showGxpColumn ? <th className="col-gxp">GxP</th> : null}
              <th className="col-scope">Phạm vi chứng nhận</th>
              <th className="col-province">Tỉnh/thành</th>
              <th className="col-reference">Ktra gần nhất</th>
              <th className="col-status">Trạng thái hồ sơ gần nhất</th>
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
    </section>
  );
}
