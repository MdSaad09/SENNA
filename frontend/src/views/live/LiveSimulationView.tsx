// View 5: the agent racing in the simulator, streamed live (R-05 — this is never
// live timing). The socket ferries stored frames into the live buffer; scrub,
// pause and reconnect all read that one buffer, so what you rewind to is exactly
// what arrived (E-16). The card panel follows the playhead: scrubbing back shows
// that lap's card, and a run whose model has no stored explanations says so
// honestly instead of erroring (E-15).

import { OrbitControls } from "@react-three/drei";
import { Suspense, useEffect, useRef, useState } from "react";

import { apiPost } from "../../api/client";
import { LiveSocket } from "../../api/liveSocket";
import { useCircuit, useSimulation } from "../../api/queries";
import type { JobAccepted } from "../../api/types";
import CanvasHost from "../../components/CanvasHost";
import RunPicker from "../../components/RunPicker";
import TransportControls, {
  ILLUSTRATIVE_MOTION_CAPTION,
} from "../../components/TransportControls";
import { DEFAULT_GRID_POSITION } from "../../config/constants";
import { useLiveStore } from "../../stores/liveStore";
import ReplayScene from "../replay/ReplayScene";
import DecisionCardPanel from "./DecisionCardPanel";

function positiveIntParam(query: URLSearchParams, name: string): number | null {
  const raw = query.get(name);
  if (raw === null) return null;
  const parsed = Number(raw);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function writeRunBack(runId: number): void {
  // keep circuit and seed visible: the deep link stays shareable after it resolves
  const query = new URLSearchParams(window.location.search);
  query.set("run", String(runId));
  window.history.replaceState(null, "", `${window.location.pathname}?${query}`);
}

export default function LiveSimulationView() {
  const [runId, setRunId] = useState<number | null>(() =>
    positiveIntParam(new URLSearchParams(window.location.search), "run"),
  );
  const [deepLinkError, setDeepLinkError] = useState<string | null>(null);
  const posted = useRef(false); // refs survive StrictMode's double effect — one POST
  const socketRef = useRef<LiveSocket | null>(null);

  useEffect(() => {
    if (runId !== null || posted.current) return;
    const query = new URLSearchParams(window.location.search);
    const circuit = query.get("circuit");
    if (circuit === null) return;
    posted.current = true;
    const seed = positiveIntParam(query, "seed");
    apiPost<JobAccepted>("/v1/simulations", {
      circuit_id: circuit,
      grid_position: positiveIntParam(query, "grid") ?? DEFAULT_GRID_POSITION,
      ...(seed !== null ? { seed } : {}),
    })
      .then((accepted) => {
        writeRunBack(accepted.run_id);
        setRunId(accepted.run_id);
      })
      .catch((thrown) => {
        setDeepLinkError(thrown instanceof Error ? thrown.message : String(thrown));
      });
  }, [runId]);

  useEffect(() => {
    if (runId === null) return;
    useLiveStore.getState().reset();
    const socket = new LiveSocket(runId);
    socketRef.current = socket;
    return () => {
      socketRef.current = null;
      socket.dispose();
    };
  }, [runId]);

  const run = useSimulation(runId);
  const detail = useCircuit(run.data?.circuit_id ?? null);

  const playing = useLiveStore((state) => state.playing);
  const speed = useLiveStore((state) => state.speed);
  const following = useLiveStore((state) => state.following);
  const streamFailed = useLiveStore((state) => state.failed);
  const headLap = useLiveStore((state) =>
    state.frames.length === 0 ? 0 : state.frames[state.frames.length - 1].lap,
  );
  const cardLap = useLiveStore((state) => Math.max(1, Math.ceil(state.playheadLap)));
  const cards = useLiveStore((state) => state.cards);
  const frames = useLiveStore((state) => state.frames);

  const setPlaying = useLiveStore((state) => state.setPlaying);
  const setSpeed = useLiveStore((state) => state.setSpeed);
  const scrubTo = useLiveStore((state) => state.scrubTo);

  const nominalLapS = run.data?.summary?.nominal_lap_s;
  const sceneReady =
    frames.length > 0 && detail.data?.gltf_url != null && typeof nominalLapS === "number";

  const card = cards.get(cardLap) ?? null;
  const allCardsNull = cards.size > 0 && [...cards.values()].every((held) => held === null);

  function handlePlayPause(next: boolean): void {
    setPlaying(next);
    if (next) {
      // resume is a seek: only the server's seek branch clears its paused flag
      // (api/ws.py:125, plan divergence 4) — a speed message would not restart it
      socketRef.current?.sendSeek(headLap + 1);
    } else {
      socketRef.current?.sendPause();
    }
  }

  function handleSpeed(option: number): void {
    setSpeed(option);
    socketRef.current?.sendSpeed(option);
  }

  function goLive(): void {
    scrubTo(headLap);
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-baseline gap-x-6 gap-y-1 border-b border-neutral-800 px-4 py-2 text-xs text-neutral-400">
        <span className="text-neutral-200">
          live simulation — the trained agent racing in the simulator, not live timing
        </span>
        {run.data !== undefined && (
          <>
            <span>run {run.data.run_id}</span>
            <span>{run.data.circuit_id?.replace(/_/g, " ")}</span>
            {run.data.seed !== null && <span>seed {run.data.seed}</span>}
            {run.data.model_version !== null && <span>{run.data.model_version}</span>}
          </>
        )}
      </header>

      <div className="flex min-h-0 flex-1">
        <section className="relative min-h-0 flex-1">
          <CanvasHost>
            {sceneReady && (
              <Suspense fallback={null}>
                <ReplayScene
                  detail={detail.data!}
                  gltfUrl={detail.data!.gltf_url!}
                  frames={frames}
                  nominalLapS={nominalLapS!}
                  store={useLiveStore}
                />
              </Suspense>
            )}
            <OrbitControls makeDefault />
          </CanvasHost>

          {runId === null && deepLinkError === null && (
            <div className="absolute inset-0 flex">
              <RunPicker onRun={setRunId} heading="new live simulation" fullMatrix />
            </div>
          )}
          {deepLinkError !== null && (
            <div className="absolute inset-0 grid place-items-center px-8 text-sm text-neutral-400">
              {deepLinkError}
            </div>
          )}
          {runId !== null && frames.length === 0 && (
            <div className="absolute inset-0 grid place-items-center text-sm text-neutral-400">
              {streamFailed
                ? `run ${runId} failed mid-simulation — check the worker logs`
                : `run ${runId}: waiting for the stream…`}
            </div>
          )}
        </section>

        {runId !== null && frames.length > 0 && (
          <aside className="w-80 shrink-0 overflow-y-auto border-l border-neutral-800 p-3">
            {card !== null && <DecisionCardPanel card={card} />}
            {card === null && allCardsNull && (
              <p className="text-xs text-neutral-500">
                no stored explanations for model version{" "}
                {run.data?.model_version ?? "unknown"} — this run streams without cards
                (a retrained model explains only its own runs, E-15)
              </p>
            )}
            {card === null && !allCardsNull && cards.size > 0 && (
              <p className="text-xs text-neutral-500">no stored card for lap {cardLap}</p>
            )}
          </aside>
        )}
      </div>

      {frames.length > 0 && (
        <TransportControls
          playing={playing}
          speed={speed}
          maxLap={headLap}
          onPlayPause={handlePlayPause}
          onSpeed={handleSpeed}
          onScrub={scrubTo}
          subscribePlayhead={(listener) =>
            useLiveStore.subscribe((state) => state.playheadLap, listener)
          }
          caption={ILLUSTRATIVE_MOTION_CAPTION}
        >
          {following ? (
            <span className="rounded bg-neutral-800 px-2 py-0.5 text-xs text-neutral-300">
              live
            </span>
          ) : (
            <button
              type="button"
              onClick={goLive}
              className="rounded border border-neutral-700 px-2 py-0.5 text-xs text-neutral-300 hover:bg-neutral-800"
            >
              go live
            </button>
          )}
        </TransportControls>
      )}
    </div>
  );
}
