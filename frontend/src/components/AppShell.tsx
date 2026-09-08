import type { ReactNode } from "react";

import { LegalLinksNav } from "./LegalLinksNav";

export function AppShell({
  header,
  children,
  showPublicLegalNav,
}: {
  header: ReactNode;
  children: ReactNode;
  showPublicLegalNav: boolean;
}) {
  return (
    <div className="app-shell">
      <div className="shell-chrome">
        {header}
        {showPublicLegalNav ? <LegalLinksNav ariaLabel="Liên kết pháp lý công khai" className="legal-links legal-links-shell" /> : null}
      </div>
      <main className="workspace-root">{children}</main>
    </div>
  );
}
