export function ErrorState({ message }: { message: string }) {
  return (
    <section className="state-panel state-panel-error" role="alert">
      <h3>Yêu cầu thất bại</h3>
      <p>{message}</p>
    </section>
  );
}
