// Placeholder routes for views 3-6: the route table is complete from F11 so the
// one-canvas rule is testable across all six paths, but the content lands in
// F12/F13. No canvas mounts here — that is the point.

export default function StubView({ title, arrives }: { title: string; arrives: string }) {
  return (
    <section className="grid h-full place-items-center">
      <div className="text-center">
        <h2 className="text-2xl font-semibold text-senna-muted">{title}</h2>
        <p className="mt-2 text-sm text-senna-faint">arrives in {arrives}</p>
      </div>
    </section>
  );
}
