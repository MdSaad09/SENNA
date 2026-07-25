// The other end of liveSocket.ts. jsdom's WebSocket cannot be pointed at a fixture
// server, so tests install this fake: client traffic lands parsed in `sent`, and the
// server side is driven explicitly through serverOpen/serverMessage/serverClose — the
// test owns the timeline. Install/restore mirrors installFetchStub's shape.

type Listener = (event: Event) => void;

export class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  /** every socket constructed since the last install, in creation order */
  static instances: FakeWebSocket[] = [];

  url: string;
  readyState = FakeWebSocket.CONNECTING;
  /** JSON payloads the client sent, parsed */
  sent: Record<string, unknown>[] = [];

  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  private listeners = new Map<string, Set<Listener>>();

  constructor(url: string | URL) {
    this.url = String(url);
    FakeWebSocket.instances.push(this);
  }

  send(payload: string): void {
    this.sent.push(JSON.parse(payload) as Record<string, unknown>);
  }

  close(_code?: number, _reason?: string): void {
    // the client hanging up; a close *event* only ever comes from serverClose, so a
    // test can stage "the network noticed late" against an already-disposed client
    this.readyState = FakeWebSocket.CLOSED;
  }

  addEventListener(type: string, listener: Listener): void {
    const bucket = this.listeners.get(type) ?? new Set<Listener>();
    bucket.add(listener);
    this.listeners.set(type, bucket);
  }

  removeEventListener(type: string, listener: Listener): void {
    this.listeners.get(type)?.delete(listener);
  }

  serverOpen(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.dispatch("open", new Event("open"), this.onopen);
  }

  serverMessage(payload: unknown): void {
    const event = new MessageEvent("message", { data: JSON.stringify(payload) });
    this.dispatch("message", event, this.onmessage as Listener | null);
  }

  serverClose(code = 1000): void {
    this.readyState = FakeWebSocket.CLOSED;
    const event = new CloseEvent("close", { code });
    this.dispatch("close", event, this.onclose as Listener | null);
  }

  private dispatch(type: string, event: Event, handler: Listener | null): void {
    handler?.(event);
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }
}

/** Point globalThis.WebSocket at the fake; returns the teardown that restores it. */
export function installFakeWebSocket(): () => void {
  const holder = globalThis as { WebSocket?: unknown };
  const real = holder.WebSocket;
  FakeWebSocket.instances = [];
  holder.WebSocket = FakeWebSocket;
  return () => {
    if (real === undefined) delete holder.WebSocket;
    else holder.WebSocket = real;
  };
}
