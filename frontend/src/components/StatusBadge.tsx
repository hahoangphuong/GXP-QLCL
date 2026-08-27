import { formatStatusLabel, getStatusTone } from "../lib/presentation";

export function StatusBadge({ value }: { value: string | null | undefined }) {
  const normalized = String(value ?? "").trim();
  if (!normalized) {
    return <span className="status-badge muted">Chưa có</span>;
  }
  return <span className={`status-badge ${getStatusTone(normalized)}`}>{formatStatusLabel(normalized)}</span>;
}
