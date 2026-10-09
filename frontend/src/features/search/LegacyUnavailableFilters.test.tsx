import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LegacyUnavailableFilters } from "./LegacyUnavailableFilters";

describe("unsupported legacy conditions", () => {
  it("keeps source-backed groups visible and prevents selection of unsupported conditions", () => {
    const { container } = render(<LegacyUnavailableFilters />);
    expect(screen.getByText("Tình trạng đăng ký")).toBeInTheDocument();
    expect(screen.getByText("Dạng bào chế")).toBeInTheDocument();
    for (const control of container.querySelectorAll("input")) expect(control).toBeDisabled();
    const registration = screen.getByRole("checkbox", { name: "Đăng ký mới" });
    registration.click();
    expect(registration).not.toBeChecked();
    expect(screen.getByLabelText("Thời gian cấp — từ")).toBeDisabled();
  });
});
