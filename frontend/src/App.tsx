export default function App() {
  return (
    <main className="grid min-h-screen place-items-center bg-neutral-950 text-neutral-100">
      <div className="text-center">
        <h1 className="text-5xl font-semibold tracking-[0.3em]">SENNA</h1>
        <p className="mt-4 text-sm text-neutral-400">
          2026 race strategy, explained lap by lap
        </p>
      </div>
      {/* R-07: the unofficial-project footer stays on every view */}
      <footer className="fixed bottom-4 text-xs text-neutral-600">
        Unofficial student project — not affiliated with F1, the FIA or any team
      </footer>
    </main>
  );
}
