export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <section className="state-panel">
      <h3>{title}</h3>
      <p>{description}</p>
    </section>
  );
}
