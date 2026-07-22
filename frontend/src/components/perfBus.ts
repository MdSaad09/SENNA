// A plain subscribe/snapshot pair, deliberately not zustand: perf samples arrive at
// 2 Hz and belong nowhere near app state that components re-render on.

export interface PerfSnapshot {
  calls: number;
  triangles: number;
  fps: number;
}

let snapshot: PerfSnapshot = { calls: 0, triangles: 0, fps: 0 };
const listeners = new Set<() => void>();

export function publishPerf(next: PerfSnapshot): void {
  snapshot = next;
  for (const listener of listeners) listener();
}

export function perfSnapshot(): PerfSnapshot {
  return snapshot;
}

export function subscribePerf(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
