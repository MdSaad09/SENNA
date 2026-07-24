import "@testing-library/jest-dom/vitest";

// react-router's data layer wraps every navigation in a Request; under vitest the
// Request class is Node's undici, which rejects jsdom's AbortSignal as a foreign
// realm. Navigation cancellation means nothing in these tests, so drop the signal.
const NativeRequest = globalThis.Request;
globalThis.Request = class extends NativeRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(input, init?.signal != null ? { ...init, signal: null } : init);
  }
} as typeof Request;

// recharts measures its container through ResizeObserver, which jsdom does not ship.
// The energy view's assertions read the honesty captions and axis labels (real DOM),
// not the SVG paths, so a no-op observer is all the chart needs to mount.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as typeof ResizeObserver;
}
