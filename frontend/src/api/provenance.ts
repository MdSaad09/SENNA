// The frontend row of the interpretability contract (5.1 invariant 2): every API
// response — success or failure — lands here, so the dev overlay can trace any
// number on screen back to the response that carried it.

import { PROVENANCE_LOG_CAP } from "../config/constants";

export interface ProvenanceEntry {
  method: string;
  path: string;
  status: number;
  xModelVersion: string | null;
  runId?: number;
  modelVersion?: string;
  envConfigHash?: string;
}

export interface TracedEntry extends ProvenanceEntry {
  traceId: number;
  at: number;
}

let entries: TracedEntry[] = [];
let nextTraceId = 1;
const listeners = new Set<() => void>();

export function recordProvenance(entry: ProvenanceEntry): TracedEntry {
  const traced: TracedEntry = { ...entry, traceId: nextTraceId++, at: Date.now() };
  entries = [...entries.slice(-(PROVENANCE_LOG_CAP - 1)), traced];
  for (const listener of listeners) listener();
  return traced;
}

export function provenanceLog(): readonly TracedEntry[] {
  return entries;
}

export function subscribeProvenance(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function clearProvenance(): void {
  entries = [];
}
