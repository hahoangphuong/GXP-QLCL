import type { ReactNode } from "react";

import { LegalLinksNav } from "./LegalLinksNav";
import { PrimaryNav } from "./PrimaryNav";

export function AppShell({
  header,
  children,
  canAccessAdmin,
}: {
  header: ReactNode;
  children: ReactNode;
  canAccessAdmin: boolean;
}) {
  return (
    <div className="app-shell">
      <div className="shell-chrome">
        {header}
        <PrimaryNav canAccessAdmin={canAccessAdmin} />
        <LegalLinksNav ariaLabel="Liên kết pháp lý công khai" className="legal-links legal-links-shell" />
      </div>
      <main className="workspace-root">{children}</main>
    </div>
  );
}
