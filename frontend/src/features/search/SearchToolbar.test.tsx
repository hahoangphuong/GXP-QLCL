import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SearchToolbar } from "./SearchToolbar";

const filters = {
  query: "",
  province: "",
  caseState: "",
  certificateState: "",
  certificateExpiringWithinDays: "",
  changeRequestStates: [],
};

describe("SearchToolbar", () => {
  it("keeps advanced filters collapsed while retaining a visible count and GxP context", () => {
    render(<SearchToolbar filters={filters} gxpType="GMP" loadedCount={100} totalCount={142} onChange={vi.fn()} onClear={vi.fn()} />);

    expect(screen.getByText("Đã tải 100 / 142")).toBeInTheDocument();
    expect(screen.getByLabelText("Nhóm GxP đang chọn: GMP")).toHaveTextContent("GMP / GLP / GMPbb · GMP");
    expect(screen.queryByLabelText("Tỉnh/thành")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Xóa lọc" })).toBeDisabled();
  });

  it("expands supported advanced filters and sends only their existing filter keys", () => {
    const onChange = vi.fn();
    render(<SearchToolbar filters={filters} gxpType="GLP" loadedCount={2} totalCount={2} onChange={onChange} onClear={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Bộ lọc" }));
    fireEvent.change(screen.getByLabelText("Tỉnh/thành"), { target: { value: "Hà Nội" } });
    fireEvent.change(screen.getByLabelText("Trạng thái hồ sơ"), { target: { value: "planned" } });

    expect(onChange).toHaveBeenNthCalledWith(1, "province", "Hà Nội");
    expect(onChange).toHaveBeenNthCalledWith(2, "caseState", "planned");
  });

  it("shows active advanced predicates after the controls are collapsed", () => {
    render(<SearchToolbar
      filters={{ ...filters, province: "Hà Nội", certificateState: "active" }}
      gxpType="GMPbb"
      loadedCount={1}
      totalCount={1}
      onChange={vi.fn()}
      onClear={vi.fn()}
    />);

    expect(screen.getByLabelText("Bộ lọc đang áp dụng")).toHaveTextContent("Tỉnh/thành: Hà Nội");
    expect(screen.getByLabelText("Bộ lọc đang áp dụng")).toHaveTextContent("Chứng nhận: Còn hiệu lực");
    expect(screen.getByRole("button", { name: "Xóa lọc" })).toBeEnabled();
  });
});
