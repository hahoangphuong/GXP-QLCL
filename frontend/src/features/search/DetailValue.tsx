import type { ReactNode } from "react";

export function DetailValue({
  label,
  value,
  multiline = false,
}: {
  label: string;
  value: string | null | undefined | ReactNode;
  multiline?: boolean;
}) {
  return (
    <div className={multiline ? "summary-span" : undefined}>
      <span>{label}</span>
      <strong className={multiline ? "multiline-value" : undefined}>{value || "Chưa có"}</strong>
    </div>
  );
}
