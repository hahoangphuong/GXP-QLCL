import type { ReactNode } from "react";

import { LegalLinksNav } from "./LegalLinksNav";
import { PrimaryNav } from "./PrimaryNav";

export function AppShell({
  header,
  children,
  canAccessAdmin,
  showPublicLegalNav,
}: {
  header: ReactNode;
  children: ReactNode;
  canAccessAdmin: boolean;
  showPublicLegalNav: boolean;
}) {
  return (
    <div className="app-shell">
      <div className="shell-chrome">
        {header}
        <PrimaryNav canAccessAdmin={canAccessAdmin} />
        {showPublicLegalNav ? <LegalLinksNav ariaLabel="Liên kết pháp lý công khai" className="legal-links legal-links-shell" /> : null}
      </div>
      <main className="workspace-root">{children}</main>
    </div>
  );
}
