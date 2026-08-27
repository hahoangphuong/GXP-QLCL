export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <section className="page-section">
      <header className="section-title">
        <div>
          <p className="eyebrow">Đang giữ chỗ</p>
          <h2>{title}</h2>
        </div>
      </header>
      <div className="panel">
        <p>{description}</p>
      </div>
    </section>
  );
}
