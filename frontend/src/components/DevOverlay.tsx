// The interpretability contract's frontend row: every figure on screen arrived
// through api/client.ts, so this table is a complete trace of where the numbers
// came from — endpoint, status, run/model/config ids and the X-Model-Version the
// server stamped. Perf rows read the same probe the 5.10.3 budget is asserted by.

import { useSyncExternalStore } from "react";

import { provenanceLog, subscribeProvenance } from "../api/provenance";
import {
  DEV_OVERLAY_KEY,
  FPS_FLOOR,
  MAX_DRAW_CALLS_REPLAY,
} from "../config/constants";
import { useUiStore } from "../stores/uiStore";
import { perfSnapshot, subscribePerf } from "./perfBus";

function simulateContextLoss() {
  const canvas = document.querySelector("canvas");
  const context = canvas?.getContext("webgl2") ?? canvas?.getContext("webgl");
  context?.getExtension("WEBGL_lose_context")?.loseContext();
}

export default function DevOverlay() {
  const open = useUiStore((state) => state.devOverlayOpen);
  const log = useSyncExternalStore(subscribeProvenance, provenanceLog);
  const perf = useSyncExternalStore(subscribePerf, perfSnapshot);

  if (!open) return null;

  const callsOk = perf.calls <= MAX_DRAW_CALLS_REPLAY;
  const fpsOk = perf.fps === 0 || perf.fps >= FPS_FLOOR;

  return (
    <aside className="fixed right-2 top-14 z-30 max-h-[80vh] w-[26rem] overflow-auto rounded border border-neutral-700 bg-neutral-900/95 p-3 text-xs">
      <header className="flex items-baseline justify-between">
        <h2 className="font-semibold text-neutral-200">dev overlay</h2>
        <span className="text-neutral-500">toggle: {DEV_OVERLAY_KEY}</span>
      </header>

      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
        <dt className="text-neutral-400">draw calls</dt>
        <dd className={callsOk ? "text-emerald-400" : "text-red-400"}>
          {perf.calls} / {MAX_DRAW_CALLS_REPLAY}
        </dd>
        <dt className="text-neutral-400">fps</dt>
        <dd className={fpsOk ? "text-emerald-400" : "text-red-400"}>
          {perf.fps.toFixed(0)} (floor {FPS_FLOOR})
        </dd>
        <dt className="text-neutral-400">triangles</dt>
        <dd className="text-neutral-300">{perf.triangles}</dd>
      </dl>

      <button
        type="button"
        onClick={simulateContextLoss}
        className="mt-2 rounded border border-neutral-700 px-2 py-0.5 text-neutral-400 hover:bg-neutral-800"
      >
        simulate context loss (E-18)
      </button>

      <h3 className="mt-3 font-semibold text-neutral-200">API responses</h3>
      <table className="mt-1 w-full text-left">
        <thead className="text-neutral-500">
          <tr>
            <th className="pr-2">#</th>
            <th className="pr-2">request</th>
            <th className="pr-2">ids</th>
          </tr>
        </thead>
        <tbody className="text-neutral-300">
          {[...log].reverse().map((entry) => (
            <tr key={entry.traceId} className="align-top">
              <td className="pr-2 text-neutral-500">{entry.traceId}</td>
              <td className="pr-2">
                {entry.method} {entry.path}
                <span className={entry.status < 400 ? " text-emerald-500" : " text-red-400"}>
                  {" "}
                  {entry.status}
                </span>
              </td>
              <td className="pr-2 text-neutral-400">
                {entry.runId !== undefined && <div>run {entry.runId}</div>}
                {entry.modelVersion !== undefined && <div>{entry.modelVersion}</div>}
                {entry.envConfigHash !== undefined && <div>{entry.envConfigHash}</div>}
                {entry.xModelVersion !== null && <div>hdr {entry.xModelVersion}</div>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </aside>
  );
}
