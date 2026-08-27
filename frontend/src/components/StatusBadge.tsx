export function StatusBadge({ value }: { value: string | null | undefined }) {
  const normalized = String(value ?? "").trim();
  if (!normalized) {
    return <span className="status-badge muted">Chưa có</span>;
  }
  const tone =
    normalized.includes("reject") || normalized.includes("cancel") || normalized.includes("closed")
      ? "danger"
      : normalized.includes("awaiting") || normalized.includes("under") || normalized.includes("planned")
        ? "warning"
        : normalized.includes("certified") || normalized.includes("accept") || normalized.includes("active")
          ? "success"
          : "info";
  return <span className={`status-badge ${tone}`}>{normalized}</span>;
}
