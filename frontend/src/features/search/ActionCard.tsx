const ACTIONS = ["Công ty mới", "Cơ sở mới", "D.chuyền mới", "Tái đánh giá", "Thay đổi"] as const;

export function ActionCard() {
  return (
    <section className="panel panel-tight action-panel">
      <div className="action-grid" aria-label="Thao tác theo ngữ cảnh cơ sở">
        {ACTIONS.map((action) => (
          <button disabled key={action} type="button">
            {action}
          </button>
        ))}
      </div>
    </section>
  );
}
