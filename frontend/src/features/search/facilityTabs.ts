export const FACILITY_TABS = [
  "Thông tin chung",
  "Các đợt kiểm tra & thay đổi",
  "Giấy chứng nhận GxP",
  "Giấy chứng nhận đủ điều kiện",
] as const;

export type FacilityTab = (typeof FACILITY_TABS)[number];
// Preserve URL/state keys while displaying MainForm's actual page captions.
export const FACILITY_TAB_LABELS: Record<FacilityTab, string> = {
  "Thông tin chung": "Thông tin chung",
  "Các đợt kiểm tra & thay đổi": "Các đợt kiểm tra & Thay đổi",
  "Giấy chứng nhận GxP": "Giấy chứng nhận GPs",
  "Giấy chứng nhận đủ điều kiện": "Giấy chứng nhận ĐĐK",
};
export const DEFAULT_FACILITY_TAB: FacilityTab = "Các đợt kiểm tra & thay đổi";

export function resolveFacilityTab(value: string | null): FacilityTab {
  return FACILITY_TABS.find((tab) => tab === value) ?? DEFAULT_FACILITY_TAB;
}
