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
      {canAccessAdmin ? (
        <NavLink className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")} to="/admin/system-status">
          Quản trị
        </NavLink>
      ) : null}
    </nav>
  );
}
