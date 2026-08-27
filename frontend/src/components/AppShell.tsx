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
      {header}
      <PrimaryNav canAccessAdmin={canAccessAdmin} />
      <main className="workspace-root">{children}</main>
    </div>
  );
}
