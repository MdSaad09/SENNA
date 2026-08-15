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
import { useCircuit, useEnergyProfile, useSimulation } from "../../api/queries";
import type { JobAccepted } from "../../api/types";
import CanvasHost from "../../components/CanvasHost";
import RunPicker from "../../components/RunPicker";
import TransportControls, {
  ILLUSTRATIVE_MOTION_CAPTION,
} from "../../components/TransportControls";
import {
  DEFAULT_GRID_POSITION,
  EGO_CAR_ID,
  PLAYBACK_SPEEDS,
} from "../../config/constants";
import { useLiveStore } from "../../stores/liveStore";
import ReplayScene from "../replay/ReplayScene";
import JumpLink from "../../components/ui/JumpLink";
import DecisionCardPanel from "./DecisionCardPanel";
import SocBar from "./SocBar";
import { positiveIntParam, seedParam, useWriteRunBack } from "../../lib/queryParams";
import ViewHeader from "../../components/ui/ViewHeader";
import TimingTower from "../../components/TimingTower";

// ?speed= is only honoured from the 5.9.3 set — the server would reject anything
// else, and a silent drop beats surfacing an error over a shareable link
function speedParam(query: URLSearchParams): number | null {
  const raw = query.get("speed");
  if (raw === null) return null;
  const parsed = Number(raw);
  return PLAYBACK_SPEEDS.includes(parsed) ? parsed : null;
}

const subscribeLivePlayhead = (listener: (playheadLap: number) => void) =>
  useLiveStore.subscribe((state) => state.playheadLap, listener);

export default function LiveSimulationView() {
  const writeRunBack = useWriteRunBack();
  const [runId, setRunId] = useState<number | null>(() =>
    positiveIntParam("run"),
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
    const seed = seedParam(query);
    apiPost<JobAccepted>("/v1/simulations", {
      circuit_id: circuit,
      grid_position: positiveIntParam("grid", query) ?? DEFAULT_GRID_POSITION,
      ...(seed !== null ? { seed } : {}),
    })
      .then((accepted) => {
        writeRunBack(accepted.run_id);
        setRunId(accepted.run_id);
      })
      .catch((thrown) => {
        setDeepLinkError(thrown instanceof Error ? thrown.message : String(thrown));
      });
  }, [runId, writeRunBack]);

  useEffect(() => {
    if (runId === null) return;
    useLiveStore.getState().reset();
    // ?lap= and ?speed= ride the socket, never the POST body: the E-15 cache key is
    // circuit + grid + seed alone, so a pre-warmed demo run stays a hit whatever
    // lap or speed the link opens at
    const query = new URLSearchParams(window.location.search);
    const startLap = positiveIntParam("lap", query);
    const startSpeed = speedParam(query);
    if (startSpeed !== null) useLiveStore.getState().setSpeed(startSpeed);
    const socket = new LiveSocket(runId, {
      ...(startLap !== null ? { startLap } : {}),
      ...(startSpeed !== null ? { speed: startSpeed } : {}),
    });
    socketRef.current = socket;
    return () => {
      socketRef.current = null;
      socket.dispose();
    };
  }, [runId]);

  const run = useSimulation(runId);
  const detail = useCircuit(run.data?.circuit_id ?? null);
  // the SOC bar's ceiling is the served usable store (E-01) — the same ledger the
  // energy view reads, never a client-side 4 MJ
  const energy = useEnergyProfile(runId, run.data?.status === "complete");

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
  // the frame at the playhead, quantised to the lap so the tower re-renders once a lap
  // the playhead can sit a lap ahead of what has streamed; clamp to the newest frame
  // rather than blanking the tower at exactly the moment the race is most interesting
  const carsNow = useLiveStore(
    (state) =>
      state.frames[
        Math.min(Math.max(0, Math.ceil(state.playheadLap) - 1), state.frames.length - 1)
      ]?.cars,
  );
  const selectedCarId = useLiveStore((state) => state.selectedCarId);
  const selectCar = useLiveStore((state) => state.selectCar);

  const setPlaying = useLiveStore((state) => state.setPlaying);
  const setSpeed = useLiveStore((state) => state.setSpeed);
  const scrubTo = useLiveStore((state) => state.scrubTo);

  // nominal_lap_s rides the 1 s status poll; the plan's refetch-on-first-frame was
  // dropped as redundant — the poll converges within one frame even at 1x
  const nominalLapS = run.data?.summary?.nominal_lap_s;
  const sceneReady =
    frames.length > 0 && detail.data?.gltf_url != null && typeof nominalLapS === "number";

  const card = cards.get(cardLap) ?? null;
  const allCardsNull = cards.size > 0 && [...cards.values()].every((held) => held === null);
  // scrubbing must move the bar with the card: both read the lap under the playhead,
  // not the head of the stream
  const playheadFrame = frames.find((frame) => frame.lap === cardLap);

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
      <ViewHeader>
        <span className="text-senna-text">
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
      </ViewHeader>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <section className="relative min-h-0 min-w-0 flex-1">
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
            <div className="absolute inset-0 grid place-items-center px-8 text-sm text-senna-faint">
              {deepLinkError}
            </div>
          )}
          {runId !== null && frames.length === 0 && (
            <div className="absolute inset-0 grid place-items-center px-8 text-sm text-senna-faint">
              {run.isError
                ? // a stale deep link after a data reset: the 404 detail is the
                  // honest answer, not an eternal "waiting"
                  run.error instanceof Error
                  ? run.error.message
                  : String(run.error)
                : streamFailed
                  ? `run ${runId} failed mid-simulation — check the worker logs`
                  : `run ${runId}: waiting for the stream…`}
            </div>
          )}
        </section>

        {runId !== null && frames.length > 0 && (
          <aside className="w-80 shrink-0 space-y-3 overflow-y-auto border-l border-senna-line p-3">
            {energy.data !== undefined && playheadFrame !== undefined && (
              <SocBar
                socMj={playheadFrame.agent.soc_mj}
                usableSocMj={energy.data.usable_soc_mj}
              />
            )}
            {carsNow !== undefined && (
              <div className="rounded-panel border border-senna-line">
                <div className="border-b border-senna-line bg-senna-raised px-2 py-1.5 text-micro uppercase text-senna-muted">
                  lap {cardLap} of {headLap}
                </div>
                <TimingTower
                  cars={carsNow}
                  egoId={EGO_CAR_ID}
                  selectedId={selectedCarId}
                  onSelect={selectCar}
                />
              </div>
            )}
            {card !== null && <DecisionCardPanel card={card} />}
            {/* 5.13's 0:45 beat: one click from the card to the same race against the
                real one. The query rides along, so the pair is already configured */}
            {card !== null && (
              <JumpLink to="/analysis/counterfactual">compare with the real race</JumpLink>
            )}
            {card === null && allCardsNull && (
              <p className="text-xs text-senna-faint">
                no stored explanations for model version{" "}
                {run.data?.model_version ?? "unknown"} — this run streams without cards
                (a retrained model explains only its own runs, E-15)
              </p>
            )}
            {card === null && !allCardsNull && cards.size > 0 && (
              <p className="text-xs text-senna-faint">no stored card for lap {cardLap}</p>
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
          subscribePlayhead={subscribeLivePlayhead}
          caption={ILLUSTRATIVE_MOTION_CAPTION}
        >
          {following ? (
            <span className="rounded bg-senna-raised px-2 py-0.5 text-xs text-senna-muted">
              live
            </span>
          ) : (
            <button
              type="button"
              onClick={goLive}
              className="rounded border border-senna-line px-2 py-0.5 text-xs text-senna-muted hover:bg-senna-raised"
            >
              go live
            </button>
          )}
        </TransportControls>
      )}
    </div>
  );
}
