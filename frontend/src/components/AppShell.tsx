import type { ReactNode } from "react";

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
      </div>
      <main className="workspace-root">{children}</main>
    </div>
  );
}
