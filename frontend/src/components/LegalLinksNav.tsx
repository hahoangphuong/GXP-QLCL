import { NavLink } from "react-router-dom";

export function LegalLinksNav({
  className = "",
  ariaLabel,
}: {
  className?: string;
  ariaLabel: string;
}) {
  return (
    <nav aria-label={ariaLabel} className={className.trim()}>
      <NavLink className={({ isActive }) => (isActive ? "legal-link active" : "legal-link")} to="/">
        Home
      </NavLink>
      <NavLink className={({ isActive }) => (isActive ? "legal-link active" : "legal-link")} to="/privacy">
        Privacy Policy
      </NavLink>
      <NavLink className={({ isActive }) => (isActive ? "legal-link active" : "legal-link")} to="/terms">
        Terms of Service
      </NavLink>
    </nav>
  );
}
