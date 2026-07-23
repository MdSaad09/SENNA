// The one door to the API. Requests resolve against VITE_API_BASE — "/api" behind
// the vite proxy locally, the public API origin in production builds (F-27, never
// a Docker hostname) — and every response is recorded before the caller sees it.

import { recordProvenance } from "./provenance";

const base: string = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
  }
}

function bodyIds(body: unknown): { runId?: number; modelVersion?: string; envConfigHash?: string } {
  if (typeof body !== "object" || body === null || Array.isArray(body)) return {};
  const record = body as Record<string, unknown>;
  return {
    ...(typeof record.run_id === "number" ? { runId: record.run_id } : {}),
    ...(typeof record.model_version === "string" ? { modelVersion: record.model_version } : {}),
    ...(typeof record.env_config_hash === "string"
      ? { envConfigHash: record.env_config_hash }
      : {}),
  };
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    method,
    ...(body !== undefined
      ? { headers: { "content-type": "application/json" }, body: JSON.stringify(body) }
      : {}),
  });

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // a non-JSON body (proxy error page, empty 502) still gets traced below
  }

  recordProvenance({
    method,
    path,
    status: response.status,
    xModelVersion: response.headers.get("X-Model-Version"),
    ...bodyIds(payload),
  });

  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `${method} ${path} failed with ${response.status}`;
    throw new ApiError(response.status, detail);
  }
  return payload as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>("GET", path);
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>("POST", path, body);
}
