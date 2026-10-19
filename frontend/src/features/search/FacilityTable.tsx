import { useId, useLayoutEffect, useRef, useState } from "react";

import { StatusBadge } from "../../components/StatusBadge";
import { formatCompactDate, formatFacilityNameForGrid, formatStatusLabel } from "../../lib/presentation";
import type { FacilitySearchResult } from "../../types";

type HiddenFilters = {
  generalQuery: string;
  province: string;
  changeRequestStates: string[];
  certificateState: string;
  certificateExpiringWithinDays: string;
};

const GXP_OPTIONS = ["GMP", "GLP", "GMPbb"] as const;

function buildHiddenFilterChips(filters: HiddenFilters): string[] {
  const chips: string[] = [];
  if (filters.generalQuery.trim()) {
    chips.push(`Từ khóa: ${filters.generalQuery.trim()}`);
  }
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
  filters: {
    facilityName: string;
    certificateScope: string;
  };
  hiddenFilters: HiddenFilters;
  onFilterChange: (field: "facilityName" | "certificateScope", value: string) => void;
  onGxpTypeChange: (value: "GMP" | "GLP" | "GMPbb") => void;
  onReachEnd: () => void;
  onSelect: (resultKey: string) => void;
  selectedGxpType: string;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const rowRefs = useRef(new Map<string, HTMLTableRowElement>());
  const gxpTabRefs = useRef(new Map<string, HTMLButtonElement>());
  const previousRowKeysRef = useRef(rows.map((row) => row.result_key));
  const rowFocusOwnedRef = useRef(false);
  const [focusedRowKey, setFocusedRowKey] = useState<string | null>(null);
  const [focusedGxpType, setFocusedGxpType] = useState<string | null>(null);
  const instructionsId = useId();
  const chips = buildHiddenFilterChips(hiddenFilters);
  const rowEntryKey = rows.some((row) => row.result_key === focusedRowKey)
    ? focusedRowKey
    : rows.some((row) => row.result_key === selectedResultKey)
    ? selectedResultKey
    : rows[0]?.result_key;
  const gxpEntry = GXP_OPTIONS.includes(focusedGxpType as (typeof GXP_OPTIONS)[number])
    ? focusedGxpType
    : GXP_OPTIONS.includes(selectedGxpType as (typeof GXP_OPTIONS)[number])
    ? selectedGxpType
    : GXP_OPTIONS[0];

  useLayoutEffect(() => {
    const previousKeys = previousRowKeysRef.current;
    previousRowKeysRef.current = rows.map((row) => row.result_key);
    if (!focusedRowKey || rows.some((row) => row.result_key === focusedRowKey)) {
      return;
    }

    const activeElement = document.activeElement;
    const shouldRestoreFocus = rowFocusOwnedRef.current
      && (activeElement === document.body || activeElement === scrollRef.current);
    if (!shouldRestoreFocus) {
      setFocusedRowKey(null);
      return;
    }

    const previousIndex = Math.max(previousKeys.indexOf(focusedRowKey), 0);
    const nextRow = rows[Math.min(previousIndex, rows.length - 1)];
    if (nextRow) {
      rowRefs.current.get(nextRow.result_key)?.focus();
    } else {
      setFocusedRowKey(null);
      scrollRef.current?.focus();
    }
  }, [focusedRowKey, rows]);

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
          {GXP_OPTIONS.map((option, index) => (
            <button
              aria-selected={selectedGxpType === option}
              className={selectedGxpType === option ? "facility-gxp-tab active" : "facility-gxp-tab"}
              key={option}
              onClick={() => onGxpTypeChange(option)}
              onFocus={() => setFocusedGxpType(option)}
              onKeyDown={(event) => {
                const targetIndex = event.key === "ArrowDown" || event.key === "ArrowRight"
                  ? (index + 1) % GXP_OPTIONS.length
                  : event.key === "ArrowUp" || event.key === "ArrowLeft"
                    ? (index - 1 + GXP_OPTIONS.length) % GXP_OPTIONS.length
                    : event.key === "Home" ? 0
                    : event.key === "End" ? GXP_OPTIONS.length - 1
                    : null;
                if (targetIndex !== null) {
                  event.preventDefault();
                  gxpTabRefs.current.get(GXP_OPTIONS[targetIndex])?.focus();
                }
              }}
              ref={(element) => {
                if (element) gxpTabRefs.current.set(option, element);
                else gxpTabRefs.current.delete(option);
              }}
              role="tab"
              tabIndex={gxpEntry === option ? 0 : -1}
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
          <p className="sr-only" id={instructionsId}>
            Dùng phím mũi tên lên hoặc xuống, Home hoặc End để di chuyển. Nhấn Enter hoặc phím cách để chọn cơ sở.
          </p>
          <div
            aria-label="Danh sách cơ sở"
            className="table-scroll table-scroll-fill"
            data-testid="facility-table-scroll"
            onScroll={maybeLoadMore}
            ref={scrollRef}
            role="region"
            tabIndex={-1}
          >
            <table aria-describedby={instructionsId} className="dense-table facility-table">
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
              <th className="col-scope">
                <label className="table-header-filter">
                  <span>Phạm vi</span>
                  <input
                    aria-label="Phạm vi"
                    onChange={(event) => onFilterChange("certificateScope", event.target.value)}
                    placeholder="Lọc theo phạm vi..."
                    value={filters.certificateScope}
                  />
                </label>
              </th>
              <th className="col-province"><span className="table-header-label">Tỉnh/thành</span></th>
              <th className="col-reference"><span className="table-header-label">Ktra gần nhất</span></th>
              <th className="col-status"><span className="table-header-label">Trạng thái gần nhất</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr
                aria-selected={selectedResultKey === row.result_key}
                className={selectedResultKey === row.result_key ? "selected" : ""}
                key={row.result_key}
                onClick={() => onSelect(row.result_key)}
                onBlur={(event) => {
                  const nextTarget = event.relatedTarget;
                  if (nextTarget && !Array.from(rowRefs.current.values()).some((element) => element.contains(nextTarget))) {
                    rowFocusOwnedRef.current = false;
                  }
                }}
                onFocus={() => {
                  rowFocusOwnedRef.current = true;
                  setFocusedRowKey(row.result_key);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(row.result_key);
                    return;
                  }
                  const targetIndex = event.key === "ArrowDown" ? Math.min(index + 1, rows.length - 1)
                    : event.key === "ArrowUp" ? Math.max(index - 1, 0)
                    : event.key === "Home" ? 0
                    : event.key === "End" ? rows.length - 1
                    : null;
                  if (targetIndex !== null) {
                    event.preventDefault();
                    rowRefs.current.get(rows[targetIndex].result_key)?.focus();
                  }
                }}
                ref={(element) => {
                  if (element) rowRefs.current.set(row.result_key, element);
                  else rowRefs.current.delete(row.result_key);
                }}
                tabIndex={rowEntryKey === row.result_key ? 0 : -1}
              >
                <td title={row.context_code ?? row.facility_code ?? ""}>{row.context_code ?? row.facility_code ?? "Chưa có"}</td>
                <td title={row.facility_name}>{formatFacilityNameForGrid(row.facility_name)}</td>
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
