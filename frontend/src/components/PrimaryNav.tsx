import { NavLink } from "react-router-dom";

export function PrimaryNav({ canAccessAdmin }: { canAccessAdmin: boolean }) {
  return (
    <nav className="primary-nav" aria-label="Điều hướng chính">
      <NavLink className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")} to="/">
        Tổng quan
      </NavLink>
      <NavLink
        className={({ isActive }) =>
          isActive ? "nav-item nav-item-primary active" : "nav-item nav-item-primary"
        }
        to="/search"
      >
        Tra cứu
      </NavLink>
      <NavLink className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")} to="/workflow">
        Nghiệp vụ
      </NavLink>
      <NavLink className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")} to="/documents">
        Tài liệu
      </NavLink>
      <NavLink className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")} to="/reports">
        Báo cáo
      </NavLink>
      {canAccessAdmin ? (
        <NavLink className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")} to="/admin/system-status">
          Quản trị
        </NavLink>
      ) : null}
    </nav>
  );
}
