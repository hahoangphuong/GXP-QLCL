export const FACILITY_TABS = [
  "Thông tin chung",
  "Các đợt kiểm tra & thay đổi",
  "Giấy chứng nhận GxP",
  "Giấy chứng nhận đủ điều kiện",
] as const;

export type FacilityTab = (typeof FACILITY_TABS)[number];
export const DEFAULT_FACILITY_TAB: FacilityTab = "Các đợt kiểm tra & thay đổi";

export function resolveFacilityTab(value: string | null): FacilityTab {
  return FACILITY_TABS.find((tab) => tab === value) ?? DEFAULT_FACILITY_TAB;
}
